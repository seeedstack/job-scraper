"""Constants for the Internshala scraper."""

from __future__ import annotations

from jobscraper.model import JobType

BASE_URL = "https://internshala.com"
JOBS_URL = BASE_URL + "/jobs"
INTERNSHIPS_URL = BASE_URL + "/internships"

INTERNSHALA_HEADERS: dict[str, str] = {
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

# Maps Internshala job type strings to JobType enum.
# "Work From Home" sets is_remote=True on JobPost separately — mapped to FULL_TIME here.
JOB_TYPE_MAP: dict[str, JobType] = {
    "Full Time": JobType.FULL_TIME,
    "Part Time": JobType.PART_TIME,
    "Work From Home": JobType.FULL_TIME,
    "Freelance": JobType.CONTRACT,
    "Internship": JobType.INTERNSHIP,
}
