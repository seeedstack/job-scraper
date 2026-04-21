"""Constants for the Naukri scraper."""

from __future__ import annotations

from jobscraper.model import JobType

BASE_URL = "https://www.naukri.com"
SEARCH_URL = BASE_URL + "/search-results"

NAUKRI_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL + "/",
}

JOB_TYPE_MAP: dict[str, JobType] = {
    "Full Time": JobType.FULL_TIME,
    "Part Time": JobType.PART_TIME,
    "Contract": JobType.CONTRACT,
    "Temporary": JobType.TEMPORARY,
}
