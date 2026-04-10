"""Utility functions for the Upwork scraper."""

from __future__ import annotations

import json
import re

from bs4 import BeautifulSoup

from jobscraper.exception import UpworkException
from jobscraper.model import Compensation, CompensationInterval, Location
from jobscraper.upwork.constant import BOT_CHECK_SIGNATURES
from jobscraper.util import markdown_converter


def parse_location(raw: str | None) -> Location:
    """Parse a raw location string into a Location model.

    Handles formats: 'Worldwide', 'India', 'Bangalore, India'.
    Returns an empty Location for None or empty input.

    Args:
        raw: Raw location string from Upwork job card or API response.

    Returns:
        Populated Location instance.
    """
    if not raw or not raw.strip():
        return Location()

    raw = raw.strip()
    parts = [p.strip() for p in raw.split(",")]

    if len(parts) == 1:
        return Location(country=parts[0])
    if len(parts) == 2:
        return Location(city=parts[0], country=parts[1])
    # city, state, country
    return Location(city=parts[0], state=parts[1], country=parts[2])


def parse_compensation(job: dict) -> Compensation | None:
    """Parse budget/compensation from an Upwork API job dict.

    Handles both hourly (hourlyBudgetMin/Max) and fixed-price (amount) jobs.
    Currency defaults to 'USD' when not present in the response.

    Args:
        job: Raw job dict from API or search card.

    Returns:
        Compensation instance or None if no budget signal found.
    """
    try:
        inner = job.get("job", {})
        budget = inner.get("budget", {}) or {}
        currency = (budget.get("currencyCode") or "USD").strip() or "USD"

        hourly_min = inner.get("hourlyBudgetMin")
        hourly_max = inner.get("hourlyBudgetMax")

        if hourly_min is not None or hourly_max is not None:
            return Compensation(
                interval=CompensationInterval.HOURLY,
                min_amount=float(hourly_min) if hourly_min is not None else None,
                max_amount=float(hourly_max) if hourly_max is not None else None,
                currency=currency,
            )

        amount = inner.get("amount")
        if amount is not None:
            return Compensation(
                interval=None,
                min_amount=float(amount),
                max_amount=None,
                currency=currency,
            )

        return None
    except Exception:
        return None


def parse_search_html(html: str) -> list[dict]:
    """Extract job card dicts from Upwork's Next.js search results page.

    Upwork embeds all job data in a <script id="__NEXT_DATA__"> JSON blob.
    Returns an empty list when no jobs are found (end of results).

    Args:
        html: Raw HTML from GET /nx/search/jobs.

    Returns:
        List of raw job dicts from the page.

    Raises:
        UpworkException: When a bot-check or CAPTCHA page is detected.
    """
    # Check for bot-challenge before any parsing
    lower_html = html.lower()
    for sig in BOT_CHECK_SIGNATURES:
        if sig.lower() in lower_html:
            raise UpworkException(f"Bot check detected on search page ({sig!r})")

    soup = BeautifulSoup(html, "lxml")
    script_tag = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script_tag:
        return []

    try:
        data = json.loads(script_tag.string or "")
        jobs = data.get("props", {}).get("pageProps", {}).get("jobs", [])
        return jobs if isinstance(jobs, list) else []
    except (json.JSONDecodeError, AttributeError):
        return []


def parse_job_detail(data: dict) -> dict:
    """Extract enriched fields from Upwork's /api/v3/jobs/{id} response.

    Args:
        data: Parsed JSON response from the Upwork jobs API.

    Returns:
        Dict with: title, description_html, company, company_url,
        job_url_direct, job_level, location_raw, published_on.
    """
    client = data.get("client") or {}
    job = data.get("job") or {}

    job_type_raw = job.get("jobType") or ""
    job_level = job_type_raw.lower() if job_type_raw else None
    if job_level == "fixed_price":
        job_level = "fixed-price"

    return {
        "title": data.get("title"),
        "description_html": data.get("description") or "",
        "company": client.get("companyName"),
        "company_url": client.get("companyUrl"),
        "job_url_direct": data.get("applyUrl"),
        "job_level": job_level,
        "location_raw": (data.get("location") or {}).get("country"),
        "published_on": data.get("publishedOn"),
    }


def parse_html_detail(html: str, description_format: str) -> tuple[str | None, None]:
    """Extract description from Upwork's public job detail HTML page.

    The direct apply URL is never available in the public HTML — always returns None.

    Args:
        html: Raw HTML from GET /jobs/~{uid}.
        description_format: 'markdown' or 'html'.

    Returns:
        Tuple of (description, None) — job_url_direct is always None here.
    """
    soup = BeautifulSoup(html, "lxml")
    desc_div = soup.find("div", class_="job-description")
    if not desc_div:
        return None, None

    raw_html = str(desc_div)
    if description_format == "markdown":
        return markdown_converter(raw_html), None
    return raw_html, None
