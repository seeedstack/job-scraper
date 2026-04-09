"""Glassdoor scraper implementation."""

from __future__ import annotations

import random
import time
from datetime import datetime
from typing import Any

from jobscraper.exception import GlassdoorException
from jobscraper.glassdoor.constant import GLASSDOOR_HEADERS, JOB_TYPE_MAP
from jobscraper.glassdoor.util import (
    build_search_url,
    extract_emails,
    get_job_detail_url,
    get_location_id,
    parse_compensation,
    parse_html_jobs,
    parse_location,
)
from jobscraper.model import JobPost, JobResponse, Scraper, ScraperInput, Site
from jobscraper.util import create_logger, create_session, markdown_converter

logger = create_logger("glassdoor")

_PAGE_SIZE = 27  # Glassdoor returns ~27 results per HTML page


class GlassdoorScraper(Scraper):
    """Scraper for glassdoor.co.in job listings.

    Fetches search result pages as HTML and extracts job data from the
    embedded RSC (React Server Components) JSON chunks. No GraphQL needed.
    """

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Fetch job listings from Glassdoor and return as a JobResponse.

        Args:
            scraper_input: Validated scraper configuration.

        Returns:
            JobResponse containing all collected JobPost objects.

        Raises:
            GlassdoorException: On unrecoverable HTTP errors.
        """
        session = create_session(
            proxies=scraper_input.proxies,
            ca_cert=scraper_input.ca_cert,
            is_tls=True,
        )

        headers = dict(GLASSDOOR_HEADERS)
        if scraper_input.user_agent:
            headers["User-Agent"] = scraper_input.user_agent

        # Warm up session to acquire cookies
        try:
            session.get(f"https://www.glassdoor.co.in", headers=headers)
            time.sleep(random.uniform(1.0, 2.0))
        except Exception:
            pass

        # Resolve location → slug + numeric ID
        loc_slug, loc_id = "india", 115
        if scraper_input.location:
            result = get_location_id(session, headers, scraper_input.location)
            if result:
                loc_slug, loc_id = result
            else:
                logger.warning(
                    "Could not resolve location '%s'; using fallback.",
                    scraper_input.location,
                )

        jobs: list[JobPost] = []
        start_page = (scraper_input.offset // _PAGE_SIZE) + 1
        page = start_page

        while len(jobs) < scraper_input.results_wanted:
            url = build_search_url(
                keyword=scraper_input.search_term,
                location_slug=loc_slug,
                location_id=loc_id,
                page=page,
            )
            logger.info("Fetching Glassdoor page %d: %s", page, url)

            try:
                response = session.get(url, headers=headers)
            except Exception as exc:
                raise GlassdoorException(f"Failed to fetch Glassdoor page: {exc}") from exc

            status = getattr(response, "status_code", None)
            if isinstance(status, int) and status >= 400:
                raise GlassdoorException(
                    f"Glassdoor returned HTTP {status}. Bot detection may be active."
                )

            html = (
                response.text
                if hasattr(response, "text")
                else response.content.decode()
            )

            raw_jobs = parse_html_jobs(html)
            if not raw_jobs:
                logger.info("No jobs parsed on page %d; stopping.", page)
                break

            for raw in raw_jobs:
                if len(jobs) >= scraper_input.results_wanted:
                    break
                job = self._build_job_post(raw, scraper_input, session, headers)
                if job:
                    jobs.append(job)

            if len(raw_jobs) < _PAGE_SIZE:
                break

            page += 1
            time.sleep(random.uniform(0.5, 2.5))

        return JobResponse(jobs=jobs)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_job_post(
        self,
        raw: dict[str, Any],
        scraper_input: ScraperInput,
        session: Any,
        headers: dict[str, str],
    ) -> JobPost | None:
        """Convert a raw Glassdoor jobview dict to a JobPost.

        Uses field-level try/except so partial data never crashes the scraper.
        """
        try:
            header = raw.get("header", {})
            job = raw.get("job", {})
            overview = raw.get("overview", {})

            # ID — listingId lives in job sub-dict
            try:
                listing_id = str(job.get("listingId") or "")
                if not listing_id:
                    logger.warning("Glassdoor job missing listingId, skipping")
                    return None
            except Exception:
                return None

            job_url = get_job_detail_url(listing_id)

            # Title — in both header and job; prefer header
            try:
                title = header.get("jobTitleText") or job.get("jobTitleText")
                if not title:
                    logger.warning("Glassdoor job %s missing title", listing_id)
                    return None
            except KeyError:
                return None

            # Company
            try:
                company = (
                    header.get("employerNameFromSearch")
                    or header.get("employer", {}).get("name")
                )
            except Exception:
                company = None

            # Location
            try:
                location = parse_location(header.get("locationName") or "")
            except Exception:
                location = None

            # Date posted — Glassdoor gives ageInDays, not a timestamp
            try:
                age = header.get("ageInDays")
                if age is not None:
                    from datetime import date, timedelta
                    date_posted = date.today() - timedelta(days=int(age))
                else:
                    date_posted = None
            except Exception:
                date_posted = None

            # Job type
            try:
                raw_types = job.get("jobTypes") or []
                job_type = (
                    [
                        JOB_TYPE_MAP[t.lower()]
                        for t in raw_types
                        if t.lower() in JOB_TYPE_MAP
                    ] or None
                ) if raw_types else None
            except Exception:
                job_type = None

            # Compensation
            try:
                compensation = parse_compensation(header)
            except Exception:
                compensation = None

            # Remote
            try:
                is_remote = bool(job.get("isRemoteOrHybrid"))
            except Exception:
                is_remote = None

            # Easy apply = Glassdoor's own apply flow
            try:
                is_indeed_apply: bool | None = bool(header.get("easyApply"))
            except Exception:
                is_indeed_apply = None

            # Description (fragments available inline; full fetch optional)
            description: str | None = None
            emails: list[str] | None = None
            job_url_direct: str | None = None

            fragments = job.get("descriptionFragmentsText") or []
            if fragments:
                inline = " ".join(fragments)
                description = (
                    markdown_converter(f"<p>{inline}</p>")
                    if scraper_input.description_format == "markdown"
                    else inline
                )

            if scraper_input.fetch_full_description:
                try:
                    from bs4 import BeautifulSoup

                    detail_resp = session.get(job_url, headers=headers)
                    detail_html = (
                        detail_resp.text
                        if hasattr(detail_resp, "text")
                        else detail_resp.content.decode()
                    )
                    soup = BeautifulSoup(detail_html, "lxml")
                    desc_tag = (
                        soup.find("div", {"class": "jobDescriptionContent"})
                        or soup.find("div", {"id": "JobDescriptionContainer"})
                        or soup.find("div", {"data-test": "jobDescriptionText"})
                    )
                    if desc_tag:
                        raw_html = str(desc_tag)
                        description = (
                            markdown_converter(raw_html)
                            if scraper_input.description_format == "markdown"
                            else raw_html
                        )
                    emails = extract_emails(detail_html) or None
                    time.sleep(random.uniform(0.5, 2.5))
                except Exception as exc:
                    logger.warning(
                        "Job %s: failed to fetch detail page: %s", listing_id, exc
                    )

            # Company URL from employer ID
            try:
                employer_id = header.get("employer", {}).get("id") or None
                company_url = (
                    f"{_GD_BASE}/Overview/W-EI_IE{employer_id}.htm"
                    if employer_id
                    else None
                )
            except Exception:
                company_url = None

            # Company logo
            try:
                company_logo = overview.get("squareLogoUrl") or None
            except Exception:
                company_logo = None

            return JobPost(
                id=listing_id,
                site=Site.GLASSDOOR,
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
            logger.warning("Unexpected error building Glassdoor JobPost: %s", exc)
            return None


_GD_BASE = "https://www.glassdoor.co.in"
