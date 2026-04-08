"""Utility functions for parsing LinkedIn job data."""

from __future__ import annotations

import re
from datetime import date
from typing import Any

from bs4 import BeautifulSoup

from jobscraper.linkedin.constant import JOB_TYPE_FILTER, JOB_TYPE_MAP
from jobscraper.model import Compensation, CompensationInterval, Location, ScraperInput
from jobscraper.util import extract_emails_from_text, markdown_converter


def parse_search_html(html: str) -> list[dict[str, Any]]:
    """Extract job listing dicts from a LinkedIn public search results page.

    Parses ``<div class="base-card">`` job cards and returns a list of dicts
    with keys: id, title, company, location, date, job_url.

    Args:
        html: Raw HTML from a LinkedIn /jobs/search/ page.

    Returns:
        List of raw job dicts, or empty list if none found.
    """
    soup = BeautifulSoup(html, "lxml")
    results: list[dict[str, Any]] = []

    cards = soup.find_all("div", class_="base-card")
    for card in cards:
        try:
            urn = card.get("data-entity-urn", "")
            job_id = urn.split(":")[-1] if urn else card.get("data-job-id", "")
            if not job_id:
                continue

            title_tag = card.find("h3", class_="base-search-card__title")
            title = title_tag.get_text(strip=True) if title_tag else None

            company_tag = card.find("h4", class_="base-search-card__subtitle")
            company = company_tag.get_text(strip=True) if company_tag else None

            loc_tag = card.find("span", class_="job-search-card__location")
            location = loc_tag.get_text(strip=True) if loc_tag else None

            time_tag = card.find("time")
            date_str = time_tag.get("datetime") if time_tag else None

            a_tag = card.find("a", class_="base-card__full-link")
            job_url = a_tag.get("href") if a_tag else None

            results.append({
                "id": job_id,
                "title": title,
                "company": company,
                "location": location,
                "date": date_str,
                "job_url": job_url,
            })
        except Exception:
            continue

    return results


def parse_location(raw: str) -> Location:
    """Parse a LinkedIn location string into a Location model.

    Handles ``"Bengaluru, Karnataka, India"``, ``"Remote in Mumbai, Maharashtra"``,
    or a bare city name.

    Args:
        raw: Raw location string.

    Returns:
        Populated Location model.
    """
    if not raw:
        return Location()

    clean = re.sub(r"^(?:remote\s+in\s+)", "", raw.strip(), flags=re.IGNORECASE)
    clean = re.sub(r"\s*\d{5,6}\s*$", "", clean).strip()
    parts = [p.strip() for p in clean.split(",") if p.strip()]

    if len(parts) >= 3:
        return Location(city=parts[0], state=parts[1], country=parts[2])
    elif len(parts) == 2:
        return Location(city=parts[0], state=parts[1])
    elif len(parts) == 1:
        return Location(city=parts[0])
    return Location()


def build_search_params(scraper_input: ScraperInput, start: int) -> dict[str, Any]:
    """Build query parameters for a LinkedIn /jobs/search/ request.

    Args:
        scraper_input: Validated scraper configuration.
        start: Result offset (0, 25, 50, …).

    Returns:
        Dict of query parameters.
    """
    params: dict[str, Any] = {
        "keywords": scraper_input.search_term,
        "start": start,
        "pageNum": 0,
    }
    if scraper_input.location:
        params["location"] = scraper_input.location
    if scraper_input.distance is not None:
        miles = scraper_input.distance * 0.621
        params["distance"] = min([5, 10, 25, 50, 100], key=lambda x: abs(x - miles))
    if scraper_input.job_type:
        code = JOB_TYPE_FILTER.get(scraper_input.job_type.value)
        if code:
            params["f_JT"] = code
    if scraper_input.hours_old:
        params["f_TPR"] = f"r{scraper_input.hours_old * 3600}"
    if scraper_input.is_remote:
        params["f_WT"] = "2"
    return params


def parse_voyager_job(data: dict[str, Any]) -> dict[str, Any]:
    """Extract fields from a LinkedIn Voyager /jobs/jobPostings/{id} response.

    Args:
        data: The ``data`` sub-dict (or full response if already unwrapped)
            from the Voyager API JSON response.

    Returns:
        Dict with keys: title, description_html, employment_status, is_remote,
        listed_at, formatted_location, job_url_direct, is_easy_apply, company,
        company_url, company_logo, salary.
    """
    out: dict[str, Any] = {}

    out["title"] = data.get("title")

    desc_data = data.get("description") or {}
    out["description_html"] = desc_data.get("text") if isinstance(desc_data, dict) else None

    emp = (data.get("employmentStatus") or "").lower().replace("_", "-")
    out["employment_status"] = emp

    wtypes = data.get("workplaceTypes") or []
    out["is_remote"] = any(w.upper() in ("REMOTE", "HYBRID") for w in wtypes)

    out["listed_at"] = data.get("listedAt")
    out["formatted_location"] = data.get("formattedLocation")

    # Apply method
    apply = data.get("applyMethod") or {}
    offsite_key = next((k for k in apply if "OffsiteApply" in k), None)
    onsite_key = next((k for k in apply if "OnsiteApply" in k or "ComplexOnsite" in k), None)
    if offsite_key:
        out["job_url_direct"] = (apply[offsite_key] or {}).get("websiteUrl")
        out["is_easy_apply"] = False
    elif onsite_key:
        out["job_url_direct"] = None
        out["is_easy_apply"] = True
    else:
        out["job_url_direct"] = None
        out["is_easy_apply"] = None

    # Company details — key name varies by decoration version
    cd = data.get("companyDetails") or {}
    company_key = next(
        (k for k in cd if "WebJobPostingCompany" in k or "Company" in k), None
    )
    if company_key:
        res = (cd[company_key] or {}).get("companyResolutionResult") or {}
        out["company"] = res.get("name")
        out["company_url"] = res.get("url")
        logo_data = res.get("logo") or {}
        vi_key = next((k for k in logo_data if "VectorImage" in k), None)
        out["company_logo"] = (logo_data[vi_key] or {}).get("rootUrl") if vi_key else None
    else:
        out["company"] = None
        out["company_url"] = None
        out["company_logo"] = None

    out["salary"] = _extract_voyager_salary(data)

    return out


def _extract_voyager_salary(data: dict[str, Any]) -> dict[str, Any] | None:
    """Extract salary range from a Voyager job response dict.

    Tries ``salary.salaryInsight.baseSalary`` first, then
    ``jobSalaryHighQualityMetadata.salaryRange`` as fallback.

    Args:
        data: Voyager job response dict.

    Returns:
        Dict with keys min, max, currency, unit — or None if no salary data.
    """
    try:
        base = data["salary"]["salaryInsight"]["baseSalary"]
        return {
            "min": base["minValue"]["value"],
            "max": base["maxValue"]["value"],
            "currency": base.get("currencyCode", "INR"),
            "unit": base.get("unitOfWork", "YEAR"),
        }
    except (KeyError, TypeError):
        pass

    try:
        sr = data["jobSalaryHighQualityMetadata"]["salaryRange"]
        return {
            "min": sr["min"],
            "max": sr["max"],
            "currency": sr.get("currencyCode", "INR"),
            "unit": sr.get("compensationType", "ANNUAL"),
        }
    except (KeyError, TypeError):
        pass

    return None


def parse_compensation(salary_dict: dict[str, Any] | None) -> Compensation | None:
    """Convert a salary dict (from _extract_voyager_salary) to a Compensation model.

    Args:
        salary_dict: Dict with keys min, max, currency, unit — or None.

    Returns:
        Compensation model or None if input is None or missing required fields.
    """
    if not salary_dict:
        return None

    unit = (salary_dict.get("unit") or "ANNUAL").upper()
    interval_map: dict[str, CompensationInterval] = {
        "ANNUAL": CompensationInterval.YEARLY,
        "YEAR": CompensationInterval.YEARLY,
        "MONTHLY": CompensationInterval.MONTHLY,
        "MONTH": CompensationInterval.MONTHLY,
        "HOURLY": CompensationInterval.HOURLY,
        "HOUR": CompensationInterval.HOURLY,
        "WEEKLY": CompensationInterval.WEEKLY,
        "WEEK": CompensationInterval.WEEKLY,
        "DAILY": CompensationInterval.DAILY,
        "DAY": CompensationInterval.DAILY,
    }
    interval = interval_map.get(unit)

    min_val = salary_dict.get("min")
    max_val = salary_dict.get("max")
    if min_val is None and max_val is None:
        return None

    try:
        return Compensation(
            interval=interval,
            min_amount=float(min_val) if min_val is not None else None,
            max_amount=float(max_val) if max_val is not None else None,
            currency=salary_dict.get("currency") or "INR",
        )
    except (ValueError, TypeError):
        return None


def parse_html_detail(
    html: str,
    description_format: str,
) -> tuple[str | None, str | None, list[str] | None]:
    """Parse description, direct apply URL, and emails from a LinkedIn job detail page.

    Args:
        html: Raw HTML from a ``/jobs/view/{id}/`` page.
        description_format: ``"markdown"`` or ``"html"``.

    Returns:
        Tuple of (description, job_url_direct, emails). Any element may be None.
    """
    soup = BeautifulSoup(html, "lxml")

    # Description — try multiple selectors in priority order
    desc_tag = (
        soup.find("div", class_="show-more-less-html__markup")
        or soup.find("div", {"id": "job-details"})
        or soup.find("div", class_="description__text")
    )
    description: str | None = None
    if desc_tag:
        raw_html = str(desc_tag)
        description = (
            markdown_converter(raw_html)
            if description_format == "markdown"
            else raw_html
        )

    # External apply URL — only capture non-LinkedIn links
    job_url_direct: str | None = None
    apply_tag = soup.find("a", class_="apply-button") or soup.find(
        "a", attrs={"data-tracking-control-name": "public_jobs_apply-link-offsite"}
    )
    if apply_tag:
        href = apply_tag.get("href") or ""
        if href.startswith("http") and "linkedin.com" not in href:
            job_url_direct = str(href)

    # Emails
    raw_emails = list(set(extract_emails_from_text(soup.get_text()))) or None

    return description, job_url_direct, raw_emails


def parse_date(date_str: str | None) -> date | None:
    """Parse an ISO 8601 date string to a date object.

    Args:
        date_str: String like ``"2026-04-01"`` or None.

    Returns:
        date object or None.
    """
    if not date_str:
        return None
    try:
        return date.fromisoformat(date_str)
    except (ValueError, TypeError):
        return None
