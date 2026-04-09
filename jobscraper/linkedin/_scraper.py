"""LinkedIn scraper implementation."""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any

from jobscraper.exception import LinkedInException
from jobscraper.linkedin.constant import (
    BASE_URL,
    JOB_DETAIL_URL,
    JOB_TYPE_MAP,
    LINKEDIN_HEADERS,
    PAGE_SIZE,
    VOYAGER_DECORATION,
    VOYAGER_HEADERS,
    VOYAGER_JOB_URL,
)
from jobscraper.linkedin.util import (
    build_search_params,
    parse_compensation,
    parse_date,
    parse_html_detail,
    parse_location,
    parse_search_html,
    parse_voyager_job,
)
from jobscraper.model import JobPost, JobResponse, JobType, Scraper, ScraperInput, Site
from jobscraper.util import create_logger, create_session, markdown_converter

logger = create_logger("linkedin")


class LinkedInScraper(Scraper):
    """Scraper for linkedin.com job listings.

    Uses public HTML search (no auth required) to discover jobs. When
    ``cookies["li_at"]`` is supplied, fetches rich detail data from
    LinkedIn's internal Voyager API. Falls back to HTML detail page otherwise.
    """

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Fetch job listings from LinkedIn and return as a JobResponse.

        Args:
            scraper_input: Validated scraper configuration.

        Returns:
            JobResponse containing all collected JobPost objects.

        Raises:
            LinkedInException: On unrecoverable HTTP errors.
        """
        session = create_session(
            proxies=scraper_input.proxies,
            ca_cert=scraper_input.ca_cert,
            is_tls=True,
        )

        headers = dict(LINKEDIN_HEADERS)
        if scraper_input.user_agent:
            headers["User-Agent"] = scraper_input.user_agent

        li_at = (scraper_input.cookies or {}).get("li_at")

        # Warmup — acquire JSESSIONID from homepage cookies
        jsessionid: str | None = None
        try:
            warmup_resp = session.get(BASE_URL, headers=headers)
            cookies = getattr(warmup_resp, "cookies", {})
            raw_jsid = cookies.get("JSESSIONID") or ""
            jsessionid = raw_jsid.strip('"') if raw_jsid else None
            time.sleep(random.uniform(1.0, 2.0))
        except Exception:
            pass

        # Build authenticated headers when li_at is present
        voyager_headers: dict[str, str] | None = None
        if li_at:
            cookie_str = f"li_at={li_at}"
            if jsessionid:
                cookie_str += f'; JSESSIONID="{jsessionid}"'
            headers["Cookie"] = cookie_str
            if jsessionid:
                headers["Csrf-Token"] = jsessionid

            voyager_headers = dict(VOYAGER_HEADERS)
            voyager_headers["Cookie"] = cookie_str
            if jsessionid:
                voyager_headers["Csrf-Token"] = jsessionid
            if scraper_input.user_agent:
                voyager_headers["User-Agent"] = scraper_input.user_agent

        jobs: list[JobPost] = []
        start = scraper_input.offset

        while len(jobs) < scraper_input.results_wanted:
            params = build_search_params(scraper_input, start)
            logger.info("Fetching LinkedIn jobs start=%d", start)

            try:
                response = session.get(
                    BASE_URL + "/jobs/search/", headers=headers, params=params
                )
            except Exception as exc:
                raise LinkedInException(
                    f"Failed to fetch LinkedIn search page: {exc}"
                ) from exc

            status = getattr(response, "status_code", None)
            if isinstance(status, int) and status >= 400:
                raise LinkedInException(
                    f"LinkedIn returned HTTP {status}. Bot detection may be active."
                )

            html = (
                response.text
                if hasattr(response, "text")
                else response.content.decode()
            )

            raw_jobs = parse_search_html(html)
            if not raw_jobs:
                logger.info("No jobs parsed at start=%d; stopping.", start)
                break

            for raw in raw_jobs:
                if len(jobs) >= scraper_input.results_wanted:
                    break
                job = self._build_job_post(
                    raw, scraper_input, session, headers, voyager_headers
                )
                if job:
                    jobs.append(job)

            if len(raw_jobs) < PAGE_SIZE:
                break

            start += PAGE_SIZE
            time.sleep(random.uniform(0.5, 2.5))

        return JobResponse(jobs=jobs)

    def _build_job_post(
        self,
        raw: dict[str, Any],
        scraper_input: ScraperInput,
        session: Any,
        headers: dict[str, str],
        voyager_headers: dict[str, str] | None,
    ) -> JobPost | None:
        """Convert a raw LinkedIn search card dict to a JobPost.

        Uses Voyager API when voyager_headers are set; falls back to HTML
        detail page. Field-level try/except prevents partial data from
        crashing the scraper.
        """
        try:
            job_id = raw.get("id")
            if not job_id:
                logger.warning("LinkedIn job missing id, skipping")
                return None

            job_url = JOB_DETAIL_URL.format(job_id=job_id)

            title = raw.get("title")
            if not title:
                logger.warning("LinkedIn job %s missing title", job_id)
                return None

            company: str | None = raw.get("company")
            location = parse_location(raw.get("location") or "")
            date_posted = parse_date(raw.get("date"))

            description: str | None = None
            job_type: list[JobType] | None = None
            is_remote: bool | None = None
            compensation = None
            company_url: str | None = None
            company_logo: str | None = None
            job_url_direct: str | None = None
            is_indeed_apply: bool | None = None
            emails: list[str] | None = None

            # ---- Voyager path (authenticated) --------------------------------
            if voyager_headers and scraper_input.fetch_full_description:
                try:
                    vurl = VOYAGER_JOB_URL.format(job_id=job_id)
                    vresp = session.get(
                        vurl,
                        headers=voyager_headers,
                        params={"decorationId": VOYAGER_DECORATION},
                    )
                    vstatus = getattr(vresp, "status_code", None)
                    if isinstance(vstatus, int) and vstatus < 400:
                        vdata = vresp.json()
                        parsed = parse_voyager_job(vdata.get("data") or vdata)

                        title = parsed.get("title") or title
                        company = parsed.get("company") or company
                        company_url = parsed.get("company_url")
                        company_logo = parsed.get("company_logo")
                        job_url_direct = parsed.get("job_url_direct")
                        is_indeed_apply = parsed.get("is_easy_apply")
                        is_remote = parsed.get("is_remote")

                        emp = parsed.get("employment_status") or ""
                        jt = JOB_TYPE_MAP.get(emp)
                        job_type = [jt] if jt else None

                        loc_str = parsed.get("formatted_location")
                        if loc_str:
                            location = parse_location(loc_str)

                        listed_at = parsed.get("listed_at")
                        if listed_at:
                            try:
                                date_posted = datetime.fromtimestamp(
                                    int(listed_at) / 1000
                                ).date()
                            except (ValueError, OSError):
                                pass

                        compensation = parse_compensation(parsed.get("salary"))

                        raw_desc = parsed.get("description_html")
                        if raw_desc:
                            description = (
                                markdown_converter(raw_desc)
                                if scraper_input.description_format == "markdown"
                                else raw_desc
                            )

                        time.sleep(random.uniform(0.5, 2.5))
                except Exception as exc:
                    logger.warning(
                        "Job %s: Voyager fetch failed (%s); falling back to HTML",
                        job_id,
                        exc,
                    )

            # ---- HTML fallback (no cookie or Voyager failed) -----------------
            if description is None and scraper_input.fetch_full_description:
                try:
                    detail_resp = session.get(job_url, headers=headers)
                    detail_html = (
                        detail_resp.text
                        if hasattr(detail_resp, "text")
                        else detail_resp.content.decode()
                    )
                    description, job_url_direct, emails = parse_html_detail(
                        detail_html, scraper_input.description_format
                    )
                    time.sleep(random.uniform(0.5, 2.5))
                except Exception as exc:
                    logger.warning(
                        "Job %s: HTML detail fetch failed: %s", job_id, exc
                    )

            return JobPost(
                id=str(job_id),
                site=Site.LINKEDIN,
                job_url=job_url,
                job_url_direct=job_url_direct,
                title=title,
                company=company,
                location=location,
                date_posted=date_posted,
                job_type=job_type,
                compensation=compensation,
                is_remote=is_remote,
                is_indeed_apply=is_indeed_apply,
                description=description,
                emails=emails,
                company_url=company_url,
                company_logo=company_logo,
            )

        except Exception as exc:
            logger.warning("Unexpected error building LinkedIn JobPost: %s", exc)
            return None
