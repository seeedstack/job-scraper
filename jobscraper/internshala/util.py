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

    # Raw rupee range with /year: '₹ 6,00,000 - 6,50,000 /year'
    rupee_year = re.search(
        r"[\u20b9₹]\s*([\d,]+)\s*-\s*([\d,]+)\s*/\s*year", raw, re.IGNORECASE
    )
    if rupee_year:
        return Compensation(
            interval=CompensationInterval.YEARLY,
            min_amount=float(rupee_year.group(1).replace(",", "")),
            max_amount=float(rupee_year.group(2).replace(",", "")),
            currency="INR",
        )

    # Raw rupee range without interval (assume yearly if values > 1,00,000): '₹ 6,00,000 - 6,50,000'
    rupee_range = re.search(r"[\u20b9₹]\s*([\d,]+)\s*-\s*([\d,]+)", raw)
    if rupee_range:
        mn = float(rupee_range.group(1).replace(",", ""))
        mx = float(rupee_range.group(2).replace(",", ""))
        interval = CompensationInterval.YEARLY if mn >= 100_000 else CompensationInterval.MONTHLY
        return Compensation(interval=interval, min_amount=mn, max_amount=mx, currency="INR")

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
            # ID + URL from card-level attributes
            job_id = card.get("internshipid") or ""
            href = card.get("data-href") or ""
            job_url = "https://internshala.com" + href if href.startswith("/") else href

            # Title from anchor with job-title-href class
            title_a = card.find("a", class_="job-title-href")
            title = title_a.get_text(strip=True) if title_a else None

            # Company
            comp_p = card.find("p", class_="company-name")
            company = comp_p.get_text(strip=True) if comp_p else None

            # Location — element with class "locations" (div or p)
            loc_el = card.find(class_="locations")
            if loc_el:
                loc_inner = loc_el.find("a") or loc_el.find("span")
                location_raw = loc_inner.get_text(strip=True) if loc_inner else loc_el.get_text(strip=True)
            else:
                location_raw = None

            # Salary / stipend
            if mode == "internships":
                # Internships use a span.stipend element
                stipend_span = card.find("span", class_="stipend")
                salary_raw = stipend_span.get_text(strip=True) if stipend_span else None
            else:
                # Jobs: mobile span includes the /year interval label
                mobile_span = card.find("span", class_="mobile")
                salary_raw = mobile_span.get_text(strip=True) if mobile_span else None

            # Duration — internships only: 3rd row-1-item (location, stipend, duration)
            duration: str | None = None
            if mode == "internships":
                row1_items = card.find_all("div", class_="row-1-item")
                if len(row1_items) >= 3:
                    dur_span = row1_items[2].find("span")
                    duration = dur_span.get_text(strip=True) if dur_span else None

            # Employment type from card attribute ('job' → 'Job', 'internship' → 'Internship')
            emp_type = card.get("employment_type") or ""
            job_type_raw = emp_type.capitalize() if emp_type else None

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
