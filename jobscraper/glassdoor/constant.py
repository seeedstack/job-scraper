"""Constants for the Glassdoor scraper."""

from __future__ import annotations

from jobscraper.model import JobType

BASE_URL = "https://www.glassdoor.co.in"
GRAPHQL_URL = BASE_URL + "/graph"

GLASSDOOR_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Content-Type": "application/json",
    "Apollo-Requires-Preflight": "true",
    "Referer": BASE_URL + "/",
    "Origin": BASE_URL,
}

JOB_TYPE_MAP: dict[str, JobType] = {
    "fulltime": JobType.FULL_TIME,
    "full_time": JobType.FULL_TIME,
    "parttime": JobType.PART_TIME,
    "part_time": JobType.PART_TIME,
    "contract": JobType.CONTRACT,
    "temporary": JobType.TEMPORARY,
    "internship": JobType.INTERNSHIP,
    "intern": JobType.INTERNSHIP,
}
