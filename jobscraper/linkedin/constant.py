"""Constants for the LinkedIn scraper."""

from __future__ import annotations

from jobscraper.model import JobType

BASE_URL = "https://www.linkedin.com"
JOBS_SEARCH_URL = BASE_URL + "/jobs/search/"
JOB_DETAIL_URL = BASE_URL + "/jobs/view/{job_id}/"
VOYAGER_JOB_URL = BASE_URL + "/voyager/api/jobs/jobPostings/{job_id}"
VOYAGER_DECORATION = "com.linkedin.voyager.deco.jobs.web.shared.WebFullJobPosting-65"

LINKEDIN_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL + "/",
}

VOYAGER_HEADERS: dict[str, str] = {
    "Accept": "application/vnd.linkedin.normalized+json+2.1",
    "Accept-Language": "en-US,en;q=0.9",
    "X-RestLi-Protocol-Version": "2.0.0",
    "X-Li-Track": (
        '{"clientVersion":"1.13.1665","mpVersion":"1.13.1665","osName":"web",'
        '"timezoneOffset":5.5,"timezone":"Asia/Calcutta","deviceFormFactor":"DESKTOP",'
        '"mpName":"voyager-web","displayDensity":2,"displayWidth":1920,"displayHeight":1080}'
    ),
}

# LinkedIn URL filter code → JobType enum
JOB_TYPE_MAP: dict[str, JobType] = {
    "full-time": JobType.FULL_TIME,
    "full_time": JobType.FULL_TIME,
    "f": JobType.FULL_TIME,
    "part-time": JobType.PART_TIME,
    "part_time": JobType.PART_TIME,
    "p": JobType.PART_TIME,
    "contract": JobType.CONTRACT,
    "c": JobType.CONTRACT,
    "temporary": JobType.TEMPORARY,
    "t": JobType.TEMPORARY,
    "internship": JobType.INTERNSHIP,
    "i": JobType.INTERNSHIP,
}

# JobType enum value → LinkedIn URL filter code (for search params)
JOB_TYPE_FILTER: dict[str, str] = {
    "fulltime": "F",
    "parttime": "P",
    "contract": "C",
    "temporary": "T",
    "internship": "I",
}

PAGE_SIZE = 25  # LinkedIn returns up to 25 results per search page
