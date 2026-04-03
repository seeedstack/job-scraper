"""Constants for the Indeed scraper: headers, URLs, and job type mappings."""

from __future__ import annotations

from jobscraper.model import JobType

INDEED_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Referer": "https://www.indeed.com",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

BASE_URL: str = "https://{country}.indeed.com"
JOBS_SEARCH_URL: str = BASE_URL + "/jobs"

JOB_TYPE_MAP: dict[str, JobType] = {
    "fulltime": JobType.FULL_TIME,
    "full-time": JobType.FULL_TIME,
    "parttime": JobType.PART_TIME,
    "part-time": JobType.PART_TIME,
    "contract": JobType.CONTRACT,
    "contractor": JobType.CONTRACT,
    "temporary": JobType.TEMPORARY,
    "temp": JobType.TEMPORARY,
    "internship": JobType.INTERNSHIP,
    "intern": JobType.INTERNSHIP,
}
