"""Abstract base class for Internshala scrapers."""

from __future__ import annotations

import random
import time
from typing import Any, Literal

from jobscraper.exception import InternshalaException
from jobscraper.internshala.constant import BASE_URL, INTERNSHALA_HEADERS, JOB_TYPE_MAP
from jobscraper.internshala.util import parse_compensation, parse_listing_html, parse_location
from jobscraper.model import JobPost, JobResponse, JobType, Scraper, ScraperInput, Site
from jobscraper.util import create_logger, create_session, markdown_converter

logger = create_logger("internshala")

_MAX_RETRIES = 3
_BACKOFF_BASE = 2


class InternshalaScraper(Scraper):
    """Abstract base for Internshala job and internship scrapers.

    Subclasses must define ``_endpoint``, ``_mode``, and ``_site``.
    The base class handles session warmup, pagination, retry logic, and
    JobPost construction.
    """

    _endpoint: str
    _mode: Literal["jobs", "internships"]
    _site: Site
    _search_suffix: str  # appended to slug: 'jobs' or 'internship'

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Paginate Internshala listings and return a JobResponse.

        Args:
            scraper_input: Validated scraper configuration.

        Returns:
            JobResponse containing collected JobPost objects.

        Raises:
            InternshalaException: After 3 failed retries on 429/403.
        """
        # Internshala redirects TLS fingerprinted sessions — use plain requests
        session = create_session(
            proxies=scraper_input.proxies,
            ca_cert=scraper_input.ca_cert,
            is_tls=False,
        )
        headers = dict(INTERNSHALA_HEADERS)
        if scraper_input.user_agent:
            headers["User-Agent"] = scraper_input.user_agent

        try:
            session.get(BASE_URL, headers=headers)
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as exc:
            logger.warning("Internshala warmup failed: %s", exc)

        jobs: list[JobPost] = []
        page = 1

        # Build path-based search URL: /jobs/python-developer-jobs/ or /internships/machine-learning-internship
        search_url = self._build_search_url(scraper_input.search_term)

        while len(jobs) < scraper_input.results_wanted:
            params: dict[str, Any] = {}
            if page > 1:
                params["page"] = page

            resp = self._get_with_retry(session, search_url, headers, params or None)
            if resp is None:
                break

            cards = parse_listing_html(resp.text, self._mode)
            if not cards:
                break

            for card in cards:
                if len(jobs) >= scraper_input.results_wanted:
                    break
                job_post = self._build_job_post(card, session, headers, scraper_input)
                if job_post:
                    jobs.append(job_post)

            page += 1
            time.sleep(random.uniform(0.5, 2.5))

        return JobResponse(jobs=jobs)

    def _build_search_url(self, search_term: str | None) -> str:
        """Build a path-based Internshala search URL.

        Internshala uses path segments rather than query params for keyword search.
        Example: /jobs/python-developer-jobs or /internships/machine-learning-internship

        Args:
            search_term: Raw search string from ScraperInput.

        Returns:
            Full URL string; falls back to base endpoint if no search term.
        """
        if not search_term:
            return self._endpoint + "/"
        slug = search_term.strip().lower().replace(" ", "-")
        return f"{self._endpoint}/{slug}-{self._search_suffix}"

    def _get_with_retry(
        self, session: Any, url: str, headers: dict, params: dict | None = None
    ) -> Any | None:
        """GET with exponential backoff on 429/403."""
        for attempt in range(_MAX_RETRIES):
            try:
                resp = session.get(url, headers=headers, params=params)
                if resp.status_code in (429, 403):
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning("HTTP %s; retrying in %ss", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                return resp
            except Exception as exc:
                logger.warning("Request error attempt %s: %s", attempt + 1, exc)
                if attempt == _MAX_RETRIES - 1:
                    raise InternshalaException(
                        f"Request failed after {_MAX_RETRIES} retries: {exc}"
                    ) from exc
                time.sleep(_BACKOFF_BASE ** (attempt + 1))

        raise InternshalaException(f"Rate limited or bot check after {_MAX_RETRIES} retries")

    def _build_job_post(
        self, card: dict, session: Any, headers: dict, scraper_input: ScraperInput
    ) -> JobPost | None:
        """Construct a JobPost from a parsed listing card dict."""
        try:
            job_id = card.get("id") or ""
            job_url = card.get("job_url") or ""
            duration = card.get("duration")

            description: str | None = None
            if scraper_input.fetch_full_description and job_url:
                try:
                    from bs4 import BeautifulSoup as _BS

                    detail_resp = self._get_with_retry(session, job_url, headers)
                    if detail_resp and detail_resp.status_code == 200:
                        soup = _BS(detail_resp.text, "lxml")
                        desc_div = soup.find(
                            "div", class_="internship_details"
                        ) or soup.find("div", class_="job-description")
                        if desc_div:
                            raw_html = str(desc_div)
                            if scraper_input.description_format == "markdown":
                                description = markdown_converter(raw_html)
                            else:
                                description = raw_html
                    time.sleep(random.uniform(0.3, 1.0))
                except Exception as exc:
                    logger.warning("Detail fetch failed for %s: %s", job_url, exc)

            if duration:
                prefix = f"Duration: {duration}\n\n"
                description = prefix + (description or "")

            compensation = parse_compensation(card.get("salary_raw"))

            job_type_raw = card.get("job_type_raw") or ""
            jt = JOB_TYPE_MAP.get(job_type_raw)
            job_type: list[JobType] | None = [jt] if jt else None

            loc_raw = card.get("location") or ""
            is_remote: bool | None = (
                True if loc_raw.lower() in ("work from home", "remote") else None
            )
            location = parse_location(loc_raw)

            return JobPost(
                id=job_id,
                site=self._site,
                job_url=job_url,
                job_url_direct=None,
                title=card.get("title") or "",
                company=card.get("company"),
                location=location,
                date_posted=None,
                job_type=job_type,
                compensation=compensation,
                is_remote=is_remote,
                job_level=None,
                description=description,
            )
        except Exception as exc:
            logger.warning("Failed to build JobPost: %s", exc)
            return None
