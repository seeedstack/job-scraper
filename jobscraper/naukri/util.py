"""Utility functions for the Naukri scraper."""

from __future__ import annotations

import re
from bs4 import BeautifulSoup

from jobscraper.model import Compensation, CompensationInterval, Location


def parse_location(raw: str | None) -> Location:
    """Parse Naukri location string to Location model.

    All results India-based.
    Handles: 'Bangalore', 'Bangalore, Karnataka', 'Remote', 'Work from Home'.
    """
    if not raw or not raw.strip():
        return Location(country="India")

    raw = raw.strip()

    if raw.lower() in ("remote", "work from home", "pan india", "wfh"):
        return Location(country="India")

    parts = [p.strip() for p in raw.split(",")]
    if len(parts) == 1:
        return Location(city=parts[0], country="India")
    elif len(parts) == 2:
        return Location(city=parts[0], state=parts[1], country="India")
    else:
        return Location(city=parts[0], country="India")


def parse_compensation(raw: str | None) -> Compensation | None:
    """Parse compensation string from Naukri card.

    Handles:
    - '₹4 - 7 LPA' → yearly INR (multiply by 100,000)
    - '₹15,000 - ₹20,000 /month' → monthly INR
    - '₹500 /day' → daily INR
    - 'Not disclosed' → None
    """
    if not raw or not raw.strip():
        return None

    raw = raw.strip()

    if any(phrase in raw.lower() for phrase in ["not disclosed", "confidential", "as per"]):
        return None

    numbers = re.findall(r"[\d,]+(?:\.\d+)?", raw)
    if not numbers:
        return None

    try:
        values = [float(n.replace(",", "")) for n in numbers]
    except ValueError:
        return None

    min_val = None
    max_val = None
    interval = CompensationInterval.YEARLY

    if len(values) >= 2:
        min_val, max_val = values[0], values[1]
    elif len(values) == 1:
        min_val = values[0]

    if "/month" in raw.lower() or "per month" in raw.lower():
        interval = CompensationInterval.MONTHLY
    elif "/day" in raw.lower() or "per day" in raw.lower():
        interval = CompensationInterval.DAILY
    elif "/hour" in raw.lower() or "per hour" in raw.lower():
        interval = CompensationInterval.HOURLY
    elif "LPA" in raw.upper():
        interval = CompensationInterval.YEARLY
        if min_val:
            min_val *= 100_000
        if max_val:
            max_val *= 100_000
    else:
        if min_val and min_val >= 100_000:
            interval = CompensationInterval.YEARLY
        else:
            interval = CompensationInterval.MONTHLY

    return Compensation(
        min_amount=min_val,
        max_amount=max_val,
        interval=interval,
        currency="INR",
    )


def parse_search_html(html: str) -> list[dict]:
    """Extract job postings from Naukri search results page."""
    soup = BeautifulSoup(html, "lxml")
    jobs = []

    for job_card in soup.find_all("article", class_="jobTuple"):
        try:
            job_id = job_card.get("data-jobid") or job_card.get("id")
            if not job_id:
                continue

            title_elem = job_card.find("a", class_="jobTitle")
            title = title_elem.get_text(strip=True) if title_elem else None

            company_elem = job_card.find("a", class_="companyName")
            company = company_elem.get_text(strip=True) if company_elem else None

            loc_elem = job_card.find("span", class_="locWc")
            location = loc_elem.get_text(strip=True) if loc_elem else None

            exp_elem = job_card.find("span", class_="exp")
            experience = exp_elem.get_text(strip=True) if exp_elem else None

            salary_elem = job_card.find("span", class_="sal")
            salary = salary_elem.get_text(strip=True) if salary_elem else None

            job_type_elem = job_card.find("span", class_="jobType")
            job_type = job_type_elem.get_text(strip=True) if job_type_elem else None

            job_url = None
            link_elem = job_card.find("a", {"href": True})
            if link_elem:
                href = link_elem.get("href", "")
                if href and not href.startswith("http"):
                    job_url = "https://www.naukri.com" + href
                else:
                    job_url = href

            jobs.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "experience": experience,
                "salary": salary,
                "job_type": job_type,
                "job_url": job_url,
            })
        except Exception:
            continue

    return jobs
