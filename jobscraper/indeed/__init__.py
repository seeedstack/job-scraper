"""Indeed scraper implementation."""

from __future__ import annotations

import random
import time
from datetime import date, datetime
from typing import Any

from jobscraper.exception import IndeedException
from jobscraper.indeed.constant import INDEED_HEADERS, JOB_TYPE_MAP, JOBS_SEARCH_URL
from jobscraper.indeed.util import (
    extract_emails,
    get_job_detail_url,
    parse_compensation,
    parse_location,
    parse_mosaic_json,
)
from jobscraper.model import JobPost, JobResponse, Scraper, ScraperInput, Site
from jobscraper.util import create_logger, create_session, markdown_converter

logger = create_logger("indeed")

_PAGE_SIZE = 15  # Indeed typically returns up to 15 results per page


class IndeedScraper(Scraper):
    """Scraper for in.indeed.com job listings.

    Uses TLS fingerprinting (chrome_120) to bypass anti-bot measures and
    extracts job data from the embedded mosaic-data JSON blob.
    """

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Fetch job listings from Indeed and return as a JobResponse.

        Args:
            scraper_input: Validated scraper configuration including search
                term, location, pagination, and session options.

        Returns:
            JobResponse containing all collected JobPost objects.

        Raises:
            IndeedException: On unrecoverable HTTP or parsing errors.
        """
        session = create_session(
            proxies=scraper_input.proxies,
            ca_cert=scraper_input.ca_cert,
            is_tls=True,
        )

        # Override User-Agent if provided
        headers = dict(INDEED_HEADERS)
        if scraper_input.user_agent:
            headers["User-Agent"] = scraper_input.user_agent

        jobs: list[JobPost] = []
        start = scraper_input.offset

        while len(jobs) < scraper_input.results_wanted:
            params = self._build_params(scraper_input, start)
            search_url = JOBS_SEARCH_URL.format(
                country=scraper_input.country_indeed.value
            )

            try:
                response = session.get(search_url, headers=headers, params=params)
            except Exception as exc:
                raise IndeedException(
                    f"Failed to fetch Indeed search page: {exc}"
                ) from exc

            html = (
                response.text
                if hasattr(response, "text")
                else response.content.decode()
            )
            job_dicts = parse_mosaic_json(html)

            if not job_dicts:
                logger.info("No job dicts found on page (start=%d); stopping.", start)
                break

            for raw in job_dicts:
                if len(jobs) >= scraper_input.results_wanted:
                    break
                job = self._build_job_post(raw, scraper_input, session, headers)
                if job:
                    jobs.append(job)

            # Exit early if Indeed returned a partial page (last page)
            if len(job_dicts) < _PAGE_SIZE:
                break

            start += _PAGE_SIZE
            time.sleep(random.uniform(0.5, 2.5))

        return JobResponse(jobs=jobs)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_params(self, scraper_input: ScraperInput, start: int) -> dict[str, Any]:
        """Build the query parameters for an Indeed search URL."""
        params: dict[str, Any] = {
            "q": scraper_input.search_term,
            "start": start,
            "limit": _PAGE_SIZE,
        }
        if scraper_input.location:
            params["l"] = scraper_input.location
        if scraper_input.distance is not None:
            params["radius"] = scraper_input.distance
        if scraper_input.hours_old is not None:
            params["fromage"] = scraper_input.hours_old // 24 or 1
        return params

    def _build_job_post(
        self,
        raw: dict[str, Any],
        scraper_input: ScraperInput,
        session: Any,
        headers: dict[str, str],
    ) -> JobPost | None:
        """Convert a raw Indeed job dict to a JobPost.

        Uses field-level try/except so partial data never crashes the scraper.
        Logs warnings for missing optional fields.
        """
        try:
            job_key = raw.get("jobkey") or raw.get("jobKey") or ""
            if not job_key:
                logger.warning("Job dict missing jobkey, skipping: %s", raw)
                return None

            job_url = get_job_detail_url(job_key, scraper_input.country_indeed)

            # Title
            try:
                title = raw["title"]
            except KeyError:
                logger.warning("Job %s missing title", job_key)
                return None

            # Company
            try:
                company = raw.get("company") or raw.get("companyName")
            except Exception:
                company = None
                logger.warning("Job %s: could not parse company", job_key)

            # Location
            try:
                raw_loc = raw.get("formattedLocation") or raw.get("location") or ""
                location = parse_location(raw_loc) if raw_loc else None
            except Exception:
                location = None
                logger.warning("Job %s: could not parse location", job_key)

            # Date posted
            try:
                ts = raw.get("pubDate") or raw.get("datePosted")
                if ts:
                    date_posted = datetime.fromtimestamp(int(ts) / 1000).date()
                else:
                    date_posted = None
            except Exception:
                date_posted = None
                logger.warning("Job %s: could not parse date_posted", job_key)

            # Job type
            try:
                raw_type = raw.get("jobTypes") or []
                job_type = None
                if isinstance(raw_type, list) and raw_type:
                    job_type = [
                        JOB_TYPE_MAP[t.lower()]
                        for t in raw_type
                        if t.lower() in JOB_TYPE_MAP
                    ] or None
            except Exception:
                job_type = None
                logger.warning("Job %s: could not parse job_type", job_key)

            # Compensation
            try:
                compensation = parse_compensation(raw)
            except Exception:
                compensation = None
                logger.warning("Job %s: could not parse compensation", job_key)

            # Remote
            try:
                is_remote = bool(raw.get("remoteLocation") or raw.get("remote"))
            except Exception:
                is_remote = None

            # Description & emails
            description: str | None = None
            emails: list[str] | None = None
            job_url_direct: str | None = None

            if scraper_input.fetch_full_description:
                try:
                    detail_resp = session.get(job_url, headers=headers)
                    detail_html = (
                        detail_resp.text
                        if hasattr(detail_resp, "text")
                        else detail_resp.content.decode()
                    )
                    from bs4 import BeautifulSoup

                    soup = BeautifulSoup(detail_html, "lxml")
                    desc_tag = soup.find("div", {"id": "jobDescriptionText"})
                    if desc_tag:
                        raw_html = str(desc_tag)
                        if scraper_input.description_format == "markdown":
                            description = markdown_converter(raw_html)
                        else:
                            description = raw_html
                    emails = extract_emails(detail_html) or None
                    # Try to get the direct apply URL
                    apply_tag = soup.find("a", {"id": "applyButton"}) or soup.find(
                        "a", {"data-testid": "applyButton"}
                    )
                    if apply_tag and apply_tag.get("href"):
                        job_url_direct = str(apply_tag["href"])
                    time.sleep(random.uniform(0.5, 2.5))
                except Exception as exc:
                    logger.warning(
                        "Job %s: failed to fetch detail page: %s", job_key, exc
                    )

            # Company URL / logo
            try:
                company_url = raw.get("companyOverviewLink") or None
            except Exception:
                company_url = None

            try:
                company_logo = (
                    raw.get("companyBrandingAttributes", {}).get("logoUrl") or None
                )
            except Exception:
                company_logo = None

            return JobPost(
                id=job_key,
                site=Site.INDEED,
                job_url=job_url,
                job_url_direct=job_url_direct,
                title=title,
                company=company,
                location=location,
                date_posted=date_posted,
                job_type=job_type,
                compensation=compensation,
                is_remote=is_remote,
                description=description,
                emails=emails,
                company_url=company_url,
                company_logo=company_logo,
            )

        except Exception as exc:
            logger.warning("Unexpected error building JobPost: %s", exc)
            return None
