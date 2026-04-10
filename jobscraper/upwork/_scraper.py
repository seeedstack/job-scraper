"""Upwork scraper implementation."""

from __future__ import annotations

import random
import time
from datetime import date, datetime
from typing import Any

from jobscraper.exception import UpworkException
from jobscraper.model import JobPost, JobResponse, JobType, Scraper, ScraperInput, Site
from jobscraper.upwork.constant import (
    API_JOB_URL,
    BASE_URL,
    BOT_CHECK_SIGNATURES,
    SEARCH_URL,
    UPWORK_API_HEADERS,
    UPWORK_HEADERS,
)
from jobscraper.upwork.util import (
    parse_compensation,
    parse_html_detail,
    parse_job_detail,
    parse_location,
    parse_search_html,
)
from jobscraper.util import create_logger, create_session, markdown_converter

logger = create_logger("upwork")

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds; doubles each retry: 2, 4, 8


class UpworkScraper(Scraper):
    """Scraper for upwork.com job listings.

    Uses public Next.js HTML search (no auth required). When
    ``cookies["upwork_token"]`` is supplied, enriches each job via
    Upwork's ``/api/v3/jobs/{id}`` endpoint with a per-request
    Authorization header (never set on the session globally).
    """

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Fetch job listings from Upwork and return as a JobResponse.

        Args:
            scraper_input: Validated scraper configuration.

        Returns:
            JobResponse containing all collected JobPost objects.

        Raises:
            UpworkException: On unrecoverable errors (bot check, repeated 429).
        """
        session = create_session(
            proxies=scraper_input.proxies,
            ca_cert=scraper_input.ca_cert,
            is_tls=True,
        )
        headers = dict(UPWORK_HEADERS)
        if scraper_input.user_agent:
            headers["User-Agent"] = scraper_input.user_agent

        upwork_token: str | None = (scraper_input.cookies or {}).get("upwork_token")

        # Warmup — acquire session cookies from homepage
        try:
            session.get(BASE_URL, headers=headers)
            time.sleep(random.uniform(1.0, 2.0))
        except Exception as exc:
            logger.warning("Upwork warmup failed: %s", exc)

        jobs: list[JobPost] = []
        page = 1

        while len(jobs) < scraper_input.results_wanted:
            params = {
                "q": scraper_input.search_term,
                "sort": "recency",
                "page": page,
            }
            if scraper_input.location:
                params["location"] = scraper_input.location

            resp = self._get_with_retry(session, SEARCH_URL, headers, params)
            if resp is None:
                break

            try:
                cards = parse_search_html(resp.text)
            except UpworkException:
                raise

            if not cards:
                break

            for card in cards:
                if len(jobs) >= scraper_input.results_wanted:
                    break

                job_post = self._build_job_post(
                    card=card,
                    session=session,
                    headers=headers,
                    upwork_token=upwork_token,
                    scraper_input=scraper_input,
                )
                if job_post:
                    jobs.append(job_post)

            page += 1
            time.sleep(random.uniform(0.5, 2.5))

        return JobResponse(jobs=jobs)

    def _get_with_retry(
        self,
        session: Any,
        url: str,
        headers: dict,
        params: dict | None = None,
    ) -> Any | None:
        """GET with exponential backoff on 429/403. Returns None after exhausted retries."""
        for attempt in range(_MAX_RETRIES):
            try:
                resp = session.get(url, headers=headers, params=params)
                if resp.status_code in (429, 403):
                    # Detect Cloudflare / bot-check pages — no point retrying
                    body = resp.text
                    if any(sig in body for sig in BOT_CHECK_SIGNATURES):
                        raise UpworkException(
                            "Bot check detected (Cloudflare challenge). "
                            "Use proxies or an upwork_token to bypass."
                        )
                    wait = _BACKOFF_BASE ** (attempt + 1)
                    logger.warning("HTTP %s from Upwork; retrying in %ss", resp.status_code, wait)
                    time.sleep(wait)
                    continue
                return resp
            except Exception as exc:
                logger.warning("Request error on attempt %s: %s", attempt + 1, exc)
                if attempt == _MAX_RETRIES - 1:
                    raise UpworkException(f"Request failed after {_MAX_RETRIES} retries: {exc}") from exc
                time.sleep(_BACKOFF_BASE ** (attempt + 1))

        raise UpworkException(f"Rate limited after {_MAX_RETRIES} retries")

    def _build_job_post(
        self,
        card: dict,
        session: Any,
        headers: dict,
        upwork_token: str | None,
        scraper_input: ScraperInput,
    ) -> JobPost | None:
        """Build a JobPost from a search card, optionally enriching via API."""
        try:
            job_id = card.get("id") or ""
            job_url = f"{BASE_URL}/jobs/{job_id}" if job_id else ""

            detail: dict = {}
            if upwork_token and scraper_input.fetch_full_description and job_id:
                api_url = API_JOB_URL.format(job_id=job_id)
                api_headers = {**UPWORK_API_HEADERS, "Authorization": f"Bearer {upwork_token}"}
                try:
                    api_resp = self._get_with_retry(session, api_url, api_headers)
                    if api_resp is not None and api_resp.status_code == 200:
                        detail = parse_job_detail(api_resp.json())
                except Exception as exc:
                    logger.warning("API detail fetch failed for %s: %s", job_id, exc)

            elif scraper_input.fetch_full_description and job_id:
                try:
                    detail_resp = self._get_with_retry(session, job_url, headers)
                    if detail_resp is None:
                        raise UpworkException("No response from detail page")
                    desc, _ = parse_html_detail(
                        detail_resp.text, scraper_input.description_format
                    )
                    detail = {"description_html": desc}
                    time.sleep(random.uniform(0.3, 1.0))
                except Exception as exc:
                    logger.warning("HTML detail fetch failed for %s: %s", job_id, exc)

            # Description
            description: str | None = None
            desc_html = detail.get("description_html") or card.get("description")
            if desc_html:
                if scraper_input.description_format == "markdown":
                    description = markdown_converter(desc_html)
                else:
                    description = desc_html

            # Compensation
            compensation = parse_compensation(card)

            # Job type — both hourly and fixed-price map to CONTRACT
            job_type_raw = (card.get("job") or {}).get("jobType") or ""
            job_type: list[JobType] = [JobType.CONTRACT]  # all Upwork jobs are CONTRACT

            # job_level — preserve hourly / fixed-price distinction
            job_level = detail.get("job_level") or (job_type_raw.lower() if job_type_raw else None)
            if job_level == "fixed_price":
                job_level = "fixed-price"

            # Date
            date_posted: date | None = None
            raw_date = detail.get("published_on") or card.get("publishedOn")
            if raw_date:
                try:
                    date_posted = datetime.strptime(raw_date[:10], "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    pass

            # Location
            loc_raw = detail.get("location_raw") or (card.get("location") or {}).get("country")
            location = parse_location(loc_raw) if loc_raw else None

            return JobPost(
                id=job_id,
                site=Site.UPWORK,
                job_url=job_url,
                job_url_direct=detail.get("job_url_direct"),
                title=detail.get("title") or card.get("title") or "",
                company=detail.get("company") or (card.get("client") or {}).get("companyName"),
                company_url=detail.get("company_url"),
                location=location,
                date_posted=date_posted,
                job_type=job_type,
                compensation=compensation,
                job_level=job_level,
                description=description,
                is_remote=None,
            )
        except Exception as exc:
            logger.warning("Failed to build JobPost for Upwork card: %s", exc)
            return None
