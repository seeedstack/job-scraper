"""Utility functions for parsing Glassdoor job data from HTML."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from jobscraper.glassdoor.constant import BASE_URL
from jobscraper.model import Compensation, CompensationInterval, Location
from jobscraper.util import extract_emails_from_text


def get_location_id(session: Any, headers: dict[str, str], location: str) -> tuple[str, int] | None:
    """Look up a Glassdoor location slug and ID via the suggest API.

    Args:
        session: Active HTTP session.
        headers: Request headers.
        location: City or region name (e.g. "Bangalore").

    Returns:
        ``(location_slug, location_id)`` tuple, or None if not found.
    """
    url = f"{BASE_URL}/findPopularLocationAjax.htm?term={location}"
    try:
        resp = session.get(url, headers=headers)
        results = resp.json() if hasattr(resp, "json") else json.loads(resp.text)
        if results:
            first = results[0]
            loc_id = int(first.get("locationId") or first.get("realId"))
            label = first.get("label", location)
            slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
            return slug, loc_id
    except Exception:
        pass
    return None


def build_search_url(
    keyword: str,
    location_slug: str,
    location_id: int,
    page: int = 1,
) -> str:
    """Build a Glassdoor job search URL.

    Uses Glassdoor's SEO URL format:
    ``/Job/{loc}-{kw}-jobs-SRCH_IL.0,{L}_IC{id}_KO{L+1},{L+1+K}[_IP{page}].htm``

    Args:
        keyword: Job search term (e.g. "software engineer").
        location_slug: Slugified location (e.g. "bengaluru-india").
        location_id: Numeric Glassdoor location ID.
        page: Page number (1-indexed).

    Returns:
        Full URL string.
    """
    kw_slug = re.sub(r"[^a-z0-9]+", "-", keyword.lower()).strip("-")
    L = len(location_slug)
    K = len(kw_slug)
    page_suffix = f"_IP{page}" if page > 1 else ""
    path = (
        f"/Job/{location_slug}-{kw_slug}-jobs-SRCH_"
        f"IL.0,{L}_IC{location_id}_KO{L + 1},{L + 1 + K}"
        f"{page_suffix}.htm"
    )
    return BASE_URL + path


def parse_html_jobs(html: str) -> list[dict[str, Any]]:
    """Extract job listing dicts from Glassdoor's RSC-streamed HTML page.

    Glassdoor embeds job data as JSON inside ``self.__next_f.push([1, "..."])``
    script tags. This function decodes those chunks and extracts the
    ``jobListings`` array.

    Args:
        html: Raw HTML from a Glassdoor search results page.

    Returns:
        List of raw jobview dicts, or empty list on failure.
    """
    scripts = re.findall(r"<script[^>]*>(.*?)</script>", html, re.DOTALL)

    combined = []
    for s in scripts:
        m = re.search(r'self\.__next_f\.push\(\[1,"(.*)"\]\)', s, re.DOTALL)
        if m:
            try:
                decoded = json.loads('"' + m.group(1) + '"')
                combined.append(decoded)
            except Exception:
                pass

    text = "".join(combined)
    if not text:
        return []

    # Find "jobListings":[{"jobview":...}] array and extract via depth counting
    marker = '"jobListings":[{"jobview"'
    start = text.find(marker)
    if start == -1:
        return []

    array_start = start + len('"jobListings":')
    depth = 0
    i = array_start
    while i < len(text):
        if text[i] == "[":
            depth += 1
        elif text[i] == "]":
            depth -= 1
            if depth == 0:
                break
        i += 1

    try:
        listings = json.loads(text[array_start : i + 1])
        return [item["jobview"] for item in listings if "jobview" in item]
    except Exception:
        return []


def parse_compensation(header: dict[str, Any]) -> Compensation | None:
    """Extract compensation from a Glassdoor job header dict.

    Reads ``payPeriodAdjustedPay`` (p10/p90 range) and ``payPeriod`` interval.

    Args:
        header: The ``header`` sub-dict from a Glassdoor jobview.

    Returns:
        Compensation model or None if no pay data is present.
    """
    pay = header.get("payPeriodAdjustedPay") or {}
    min_val = pay.get("p10") if isinstance(pay, dict) else None
    max_val = pay.get("p90") if isinstance(pay, dict) else None
    if min_val is None and max_val is None:
        return None

    period = (header.get("payPeriod") or "").lower()
    interval_map: dict[str, CompensationInterval] = {
        "annual": CompensationInterval.YEARLY,
        "yearly": CompensationInterval.YEARLY,
        "monthly": CompensationInterval.MONTHLY,
        "weekly": CompensationInterval.WEEKLY,
        "daily": CompensationInterval.DAILY,
        "hourly": CompensationInterval.HOURLY,
    }
    interval = interval_map.get(period)

    try:
        return Compensation(
            interval=interval,
            min_amount=float(min_val) if min_val is not None else None,
            max_amount=float(max_val) if max_val is not None else None,
            currency=header.get("payCurrency") or "INR",
        )
    except (ValueError, TypeError):
        return None


def parse_location(raw: str) -> Location:
    """Parse a Glassdoor location string into a Location model.

    Handles ``"Bengaluru, Karnataka"``, ``"Remote in Mumbai, Maharashtra"``,
    or a bare city name.

    Args:
        raw: Raw location string from Glassdoor header.

    Returns:
        Populated Location model.
    """
    if not raw:
        return Location()

    clean = re.sub(r"^(?:remote\s+in\s+)", "", raw.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*\d{5,6}\s*$", "", clean).strip()
    parts = [p.strip() for p in clean.split(",") if p.strip()]

    if len(parts) >= 2:
        return Location(city=parts[0], state=parts[1])
    elif len(parts) == 1:
        return Location(city=parts[0])
    return Location()


def get_job_detail_url(listing_id: str) -> str:
    """Build the full URL for a Glassdoor job detail page.

    Args:
        listing_id: The Glassdoor listing ID.

    Returns:
        Full URL string.
    """
    return f"{BASE_URL}/job-listing/jl={listing_id}"


def extract_emails(html: str) -> list[str]:
    """Extract email addresses from Glassdoor job detail HTML.

    Args:
        html: Raw HTML string from a job detail page.

    Returns:
        List of unique email addresses found.
    """
    soup = BeautifulSoup(html, "lxml")
    return list(set(extract_emails_from_text(soup.get_text())))
