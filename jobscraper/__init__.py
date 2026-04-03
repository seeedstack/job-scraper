"""jobscraper — Multi-platform job scraping library.

Public API:
    scrape_jobs() — scrape job listings from one or more platforms and
                    return results as a pandas DataFrame.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import pandas as pd

from jobscraper.model import (
    Country,
    JobResponse,
    JobType,
    ScraperInput,
    Site,
)
from jobscraper.util import (
    convert_to_annual,
    desired_order,
    extract_salary,
    get_enum_from_value,
    map_str_to_site,
    set_logger_level,
)

# ---------------------------------------------------------------------------
# Scraper registry
# ---------------------------------------------------------------------------

from jobscraper.indeed import IndeedScraper  # noqa: E402

SCRAPER_MAPPING: dict[Site, type] = {
    Site.INDEED: IndeedScraper,
}


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def scrape_jobs(
    site_name: str | list[str] | Site | list[Site] | None = None,
    search_term: str | None = None,
    location: str | None = None,
    distance: int | None = 50,
    is_remote: bool = False,
    job_type: str | None = None,
    results_wanted: int = 20,
    country_indeed: str = "india",
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    description_format: str = "markdown",
    offset: int | None = 0,
    hours_old: int | None = None,
    enforce_annual_salary: bool = False,
    verbose: int = 0,
    user_agent: str | None = None,
) -> pd.DataFrame:
    """Scrape job listings from one or more platforms and return a DataFrame.

    Args:
        site_name: Platform(s) to scrape. Accepts a string, Site enum, or
            a mixed list of both. Currently supports "indeed".
        search_term: Job title or keyword to search for.
        location: City or region to filter jobs by.
        distance: Search radius in km (default 50). Passed as-is to Indeed's
            ``radius`` parameter.
        is_remote: If True, filter for remote jobs only (not yet used by
            Indeed in Phase 1; reserved for future scrapers).
        job_type: Filter by job type string (e.g. "fulltime", "internship").
        results_wanted: Maximum number of job results to return (default 20).
        country_indeed: Country for the Indeed scraper (default "india").
        proxies: Optional proxy URL string or list of proxy URL strings.
        ca_cert: Path to a CA certificate bundle for HTTPS verification.
        description_format: "markdown" (default) or "html" for job
            description text format.
        offset: Start from the Nth result (useful for pagination across
            calls). Defaults to 0.
        hours_old: Only return jobs posted within this many hours.
        enforce_annual_salary: If True, normalize all salary intervals to
            annual equivalents before returning.
        verbose: Logging verbosity. 0=ERROR, 1=WARNING, 2=INFO.
        user_agent: Override the default User-Agent header for Indeed.

    Returns:
        A pandas DataFrame with one row per job posting. Columns follow
        ``desired_order``; all-NA columns are dropped.

    Raises:
        ValueError: If site_name is missing or an unsupported site is
            requested.
    """
    set_logger_level(verbose)

    if not site_name:
        raise ValueError("site_name is required.")

    # Coerce site_name to list[Site]
    if isinstance(site_name, (str, Site)):
        site_name = [site_name]
    sites: list[Site] = []
    for s in site_name:
        if isinstance(s, str):
            sites.append(map_str_to_site(s))
        else:
            sites.append(s)

    # Coerce country_indeed
    country = Country.from_string(country_indeed)

    # Coerce job_type
    job_type_enum: JobType | None = None
    if job_type:
        job_type_enum = get_enum_from_value(job_type)

    # Normalize proxies to list
    if isinstance(proxies, str):
        proxies = [p.strip() for p in proxies.split(",") if p.strip()]

    scraper_input = ScraperInput(
        site_name=sites,
        search_term=search_term or "",
        location=location,
        distance=distance,
        hours_old=hours_old,
        results_wanted=results_wanted,
        offset=offset or 0,
        country_indeed=country,
        description_format=description_format,  # type: ignore[arg-type]
        fetch_full_description=True,
        proxies=proxies,
        ca_cert=ca_cert,
        enforce_annual_salary=enforce_annual_salary,
        user_agent=user_agent,
    )

    # Dispatch scrapers via ThreadPoolExecutor
    responses: list[JobResponse] = []

    def _run(site: Site) -> JobResponse:
        scraper_cls = SCRAPER_MAPPING.get(site)
        if scraper_cls is None:
            raise ValueError(f"No scraper implemented for site: {site}")
        return scraper_cls().scrape(scraper_input)

    with ThreadPoolExecutor(max_workers=len(sites)) as executor:
        futures = {executor.submit(_run, site): site for site in sites}
        for future in as_completed(futures):
            try:
                responses.append(future.result())
            except Exception as exc:
                site = futures[future]
                import logging

                logging.getLogger("jobscraper:main").warning(
                    "Scraper for %s raised: %s", site, exc
                )

    if not responses or not any(r.jobs for r in responses):
        return pd.DataFrame()

    # Flatten all JobPost objects to dicts
    rows: list[dict[str, Any]] = []
    for response in responses:
        for job in response.jobs:
            rows.append(_flatten_job(job, enforce_annual_salary))

    if not rows:
        return pd.DataFrame()

    df = pd.concat([pd.DataFrame([r]) for r in rows], ignore_index=True)

    # Drop all-NA columns
    df = df.dropna(axis=1, how="all")

    # Ensure all desired_order columns are present (add None for missing)
    for col in desired_order:
        if col not in df.columns:
            df[col] = None

    # Reorder columns: desired_order first, then any extras
    extra_cols = [c for c in df.columns if c not in desired_order]
    df = df[[c for c in desired_order if c in df.columns] + extra_cols]

    # Sort by site then date_posted descending
    sort_cols = [c for c in ["site", "date_posted"] if c in df.columns]
    if sort_cols:
        df = df.sort_values(sort_cols, ascending=[True, False], na_position="last")

    return df.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _flatten_job(job: Any, enforce_annual_salary: bool) -> dict[str, Any]:
    """Flatten a JobPost into a dict suitable for a DataFrame row.

    - compensation → min_amount, max_amount, interval, currency columns
    - location → formatted string via display_location()
    - job_type list → comma-joined string
    - emails list → comma-joined string
    - Falls back to extract_salary() on description when no compensation object
    """
    data: dict[str, Any] = {
        "id": job.id,
        "site": job.site.value if job.site else None,
        "job_url": job.job_url,
        "job_url_direct": job.job_url_direct,
        "title": job.title,
        "company": job.company,
        "location": job.location.display_location() if job.location else None,
        "date_posted": job.date_posted,
        "is_remote": job.is_remote,
        "job_level": job.job_level,
        "company_url": job.company_url,
        "company_logo": job.company_logo,
        "description": job.description,
        "emails": ", ".join(job.emails) if job.emails else None,
        "job_type": (
            ", ".join(jt.value for jt in job.job_type) if job.job_type else None
        ),
    }

    # Compensation columns
    salary_source: str | None = None
    if job.compensation:
        data["min_amount"] = job.compensation.min_amount
        data["max_amount"] = job.compensation.max_amount
        data["interval"] = (
            job.compensation.interval.value if job.compensation.interval else None
        )
        data["currency"] = job.compensation.currency
        salary_source = "DIRECT_DATA"
    elif job.description:
        # Fallback: extract salary from description text
        try:
            interval_str, min_val, max_val, currency = extract_salary(job.description)
            data["min_amount"] = min_val
            data["max_amount"] = max_val
            data["interval"] = interval_str
            data["currency"] = currency
            if min_val is not None:
                salary_source = "DESCRIPTION"
        except Exception:
            data["min_amount"] = None
            data["max_amount"] = None
            data["interval"] = None
            data["currency"] = None
    else:
        data["min_amount"] = None
        data["max_amount"] = None
        data["interval"] = None
        data["currency"] = None

    data["salary_source"] = salary_source

    # Enforce annual salary normalization
    if (
        enforce_annual_salary
        and data.get("interval")
        and data.get("min_amount") is not None
    ):
        convert_to_annual(data)

    return data
