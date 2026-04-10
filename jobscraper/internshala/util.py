"""Utility functions for the Internshala scraper."""

from __future__ import annotations

import re
from typing import Literal

from bs4 import BeautifulSoup

from jobscraper.model import Compensation, CompensationInterval, Location
from jobscraper.util import markdown_converter

_LPA_TO_INR = 100_000.0


def parse_location(raw: str | None) -> Location:
    """Parse an Internshala location string into a Location model.

    All results are India-based, so country is always 'India'.
    Handles: 'Bangalore', 'Bangalore, Karnataka', 'Work from Home'.

    Args:
        raw: Raw location string from a job/internship card.

    Returns:
        Populated Location with country='India'.
    """
    if not raw or not raw.strip():
        return Location(country="India")

    raw = raw.strip()

    if raw.lower() in ("work from home", "remote", "pan india"):
        return Location(country="India")

    parts = [p.strip() for p in raw.split(",")]
    if len(parts) == 1:
        return Location(city=parts[0], country="India")
    return Location(city=parts[0], state=parts[1], country="India")


def parse_compensation(raw: str | None) -> Compensation | None:
    """Parse a compensation string from an Internshala card.

    Handles formats:
    - '₹ 3 - 5 LPA'  → yearly INR (multiply by 100,000)
    - '₹ 15,000 /month'  → monthly INR
    - '₹ 200 /day'  → daily INR
    - 'Performance based' → None

    Args:
        raw: Raw salary/stipend string from card HTML.

    Returns:
        Compensation instance or None if unparseable.
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    # LPA range: '₹ 3 - 5 LPA'
    lpa_match = re.search(r"(\d+(?:\.\d+)?)\s*-\s*(\d+(?:\.\d+)?)\s*LPA", raw, re.IGNORECASE)
    if lpa_match:
        return Compensation(
            interval=CompensationInterval.YEARLY,
            min_amount=float(lpa_match.group(1)) * _LPA_TO_INR,
            max_amount=float(lpa_match.group(2)) * _LPA_TO_INR,
            currency="INR",
        )

    # Single LPA: '5 LPA'
    single_lpa = re.search(r"(\d+(?:\.\d+)?)\s*LPA", raw, re.IGNORECASE)
    if single_lpa:
        val = float(single_lpa.group(1)) * _LPA_TO_INR
        return Compensation(
            interval=CompensationInterval.YEARLY,
            min_amount=val,
            max_amount=None,
            currency="INR",
        )

    # Monthly: '₹ 15,000 /month'
    monthly = re.search(r"[\u20b9₹]?\s*([\d,]+)\s*/\s*month", raw, re.IGNORECASE)
    if monthly:
        val = float(monthly.group(1).replace(",", ""))
        return Compensation(
            interval=CompensationInterval.MONTHLY,
            min_amount=val,
            max_amount=None,
            currency="INR",
        )

    # Daily: '₹ 200 /day'
    daily = re.search(r"[\u20b9₹]?\s*([\d,]+)\s*/\s*day", raw, re.IGNORECASE)
    if daily:
        val = float(daily.group(1).replace(",", ""))
        return Compensation(
            interval=CompensationInterval.DAILY,
            min_amount=val,
            max_amount=None,
            currency="INR",
        )

    return None


def parse_listing_html(
    html: str, mode: Literal["jobs", "internships"]
) -> list[dict]:
    """Extract job/internship card dicts from an Internshala listing page.

    Both jobs and internships share ~90% of the same HTML structure.
    The ``mode`` parameter gates internship-only fields (duration).

    Args:
        html: Raw HTML from GET /jobs or /internships listing page.
        mode: 'jobs' or 'internships'.

    Returns:
        List of raw card dicts. Empty list if no cards found.
    """
    soup = BeautifulSoup(html, "lxml")
    cards = soup.find_all("div", class_="individual_internship")
    results = []

    for card in cards:
        try:
            # ID + URL from profile link href
            profile_div = card.find("div", class_="profile")
            anchor = profile_div.find("a") if profile_div else None
            href = anchor.get("href", "") if anchor else ""
            title = anchor.get_text(strip=True) if anchor else None

            # Extract numeric ID from href: /job/detail/123456/slug or /internship/detail/789/slug
            id_match = re.search(r"/detail/(\d+)/", href)
            job_id = id_match.group(1) if id_match else href

            base = "https://internshala.com"
            job_url = base + href if href.startswith("/") else href

            # Company
            company_div = card.find("div", class_="company_name")
            company_anchor = company_div.find("a") if company_div else None
            company = company_anchor.get_text(strip=True) if company_anchor else None

            # Location
            loc_div = card.find("div", class_="location_link")
            loc_anchor = loc_div.find("a", class_="location_names") if loc_div else None
            location_raw = loc_anchor.get_text(strip=True) if loc_anchor else None

            # Salary / stipend
            sal_div = card.find("div", class_="salary-stipend")
            salary_raw = sal_div.get_text(strip=True) if sal_div else None

            # Job type
            type_div = card.find("div", class_="job-internship-type")
            type_span = type_div.find("span") if type_div else None
            job_type_raw = type_span.get_text(strip=True) if type_span else None

            # Duration — internships only
            duration: str | None = None
            if mode == "internships":
                details_container = card.find("div", class_="internship_other_details_container")
                if details_container:
                    for item in details_container.find_all("div", class_="other_detail_item"):
                        detail_type = item.find("span", class_="detail_type")
                        detail_val = item.find("span", class_="detail_value")
                        if detail_type and "duration" in detail_type.get_text(strip=True).lower():
                            duration = detail_val.get_text(strip=True) if detail_val else None

            results.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location_raw,
                "salary_raw": salary_raw,
                "job_type_raw": job_type_raw,
                "duration": duration,
                "job_url": job_url,
            })
        except Exception:
            continue  # never crash on a single bad card

    return results
