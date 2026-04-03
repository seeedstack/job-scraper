"""Utility functions for parsing Indeed job data."""

from __future__ import annotations

import json
import re
from typing import Any

from bs4 import BeautifulSoup

from jobscraper.model import Compensation, CompensationInterval, Country, Location
from jobscraper.util import currency_parser, extract_emails_from_text, extract_salary


def parse_mosaic_json(html: str) -> list[dict[str, Any]]:
    """Extract and parse the <script id="mosaic-data"> JSON blob from Indeed HTML.

    Returns a list of job dicts from the jobKeysWithInfo section,
    or an empty list on failure.
    """
    soup = BeautifulSoup(html, "lxml")
    script_tag = soup.find("script", {"id": "mosaic-data"})
    if not script_tag:
        return []

    try:
        raw_js = script_tag.string or ""
        # The script sets window.mosaic.providerData["mosaic-provider-jobcards"]
        match = re.search(
            r'window\.mosaic\.providerData\["mosaic-provider-jobcards"\]\s*=\s*(\{.*?\});',
            raw_js,
            re.DOTALL,
        )
        if match:
            data = json.loads(match.group(1))
        else:
            data = json.loads(raw_js)

        # Navigate to the job list
        # Structure: metaData -> mosaicProviderJobCardsModel -> results
        meta = data.get("metaData", {})
        model = meta.get("mosaicProviderJobCardsModel", {})
        results = model.get("results", [])
        return results if isinstance(results, list) else []
    except (json.JSONDecodeError, AttributeError, KeyError):
        return []


def parse_compensation(job_data: dict[str, Any]) -> Compensation | None:
    """Extract compensation info from an Indeed job dict.

    Indeed may provide salary under 'extractedSalary' (structured) or
    'salarySnippet' (text). Returns a Compensation model or None if no
    salary data is found.
    """
    # Try extractedSalary first (structured data)
    extracted = job_data.get("extractedSalary")
    if extracted:
        try:
            min_val = extracted.get("min")
            max_val = extracted.get("max")
            interval_str = extracted.get("type", "").lower()
            interval_map: dict[str, CompensationInterval] = {
                "yearly": CompensationInterval.YEARLY,
                "monthly": CompensationInterval.MONTHLY,
                "weekly": CompensationInterval.WEEKLY,
                "daily": CompensationInterval.DAILY,
                "hourly": CompensationInterval.HOURLY,
            }
            interval = interval_map.get(interval_str)
            if min_val is not None or max_val is not None:
                return Compensation(
                    interval=interval,
                    min_amount=float(min_val) if min_val is not None else None,
                    max_amount=float(max_val) if max_val is not None else None,
                )
        except (ValueError, TypeError):
            pass

    # Try salarySnippet (text snippet)
    snippet = job_data.get("salarySnippet", {})
    if isinstance(snippet, dict):
        text = snippet.get("text", "")
    else:
        text = str(snippet) if snippet else ""

    if text:
        try:
            interval_str, min_val, max_val, currency = extract_salary(text)
            if min_val is not None:
                interval = CompensationInterval(interval_str) if interval_str else None
                return Compensation(
                    interval=interval,
                    min_amount=min_val,
                    max_amount=max_val,
                    currency=currency,
                )
        except (ValueError, TypeError):
            pass

    return None


def parse_location(raw: str) -> Location:
    """Parse an Indeed location string into a Location model.

    Handles formats like:
    - "Bangalore, Karnataka"
    - "Remote in Mumbai, Maharashtra"
    - "Hyderabad, Telangana 500001"
    """
    if not raw:
        return Location()

    # Strip "Remote in " prefix
    clean = re.sub(r"^(?:remote\s+in\s+)", "", raw.strip(), flags=re.IGNORECASE)

    # Remove postal code (5–6 digits at end)
    clean = re.sub(r"\s*\d{5,6}\s*$", "", clean).strip()

    parts = [p.strip() for p in clean.split(",") if p.strip()]

    if len(parts) >= 2:
        return Location(city=parts[0], state=parts[1])
    elif len(parts) == 1:
        return Location(city=parts[0])
    return Location()


def get_job_detail_url(job_key: str, country: Country) -> str:
    """Build the full URL for an Indeed job detail page.

    Args:
        job_key: The Indeed job key (e.g. 'abc123def456').
        country: Country enum value (e.g. Country.INDIA).

    Returns:
        Full URL string for the job detail page.
    """
    from jobscraper.indeed.constant import BASE_URL

    base = BASE_URL.format(country=country.value)
    return f"{base}/viewjob?jk={job_key}"


def extract_emails(html: str) -> list[str]:
    """Extract email addresses from Indeed job detail HTML.

    Args:
        html: Raw HTML string from a job detail page.

    Returns:
        List of unique email addresses found.
    """
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text()
    return list(set(extract_emails_from_text(text)))
