# Design: `jobscraper` — Multi-Platform Job Scraping Library

**Date:** 2026-04-02
**Status:** Approved
**Scope:** Phase 1 (core) + Phase 2 (Indeed scraper only)

---

## Overview

`jobscraper` is a Python library that scrapes job postings from multiple platforms and returns unified results as a `pandas.DataFrame`. Phase 1 implements the Indeed scraper for India only. Future scrapers (Naukri, Glassdoor, LinkedIn, Foundit, Shine, Internshala, Upwork, Apna) will follow the same module pattern.

**Import:** `import jobscraper`
**Published as:** `python-job-scraper`
**Source directory:** `jobscraper/`
**Python Version:** `^3.13`

---

## Module Layout

```
jobscraper/
├── __init__.py        # scrape_jobs(), SCRAPER_MAPPING, ThreadPoolExecutor
├── model.py           # Pydantic v2 models + Scraper ABC
├── util.py            # RequestsRotating, TLSRotating, extract_salary(), logger, html_to_markdown()
├── exception.py       # IndeedException (stubs for future sites)
└── indeed/
    ├── __init__.py    # IndeedScraper(Scraper)
    ├── constant.py    # Headers, BASE_URL, JOBS_SEARCH_URL, JOB_TYPE_MAP
    └── util.py        # parse_mosaic_json(), parse_compensation(), parse_location(), extract_emails()

examples/
└── test_indeed.py

tests/
├── __init__.py
├── test_scrape_jobs.py
├── test_util.py
└── test_indeed.py

pyproject.toml
.pre-commit-config.yaml
```

Tests use **pytest**. Run with:
```bash
pytest tests/
```

---

## Data Flow

1. `scrape_jobs()` validates args → `ScraperInput` → dispatches `IndeedScraper` via `ThreadPoolExecutor`
2. `IndeedScraper.scrape()` builds search URL for `in.indeed.com/jobs`
3. `TLSRotating` session (chrome_120 fingerprint) fetches the search results page
4. `parse_mosaic_json()` extracts `<script id="mosaic-data">` JSON blob → list of job dicts
5. Each job dict → `JobPost` via field-level `try/except` (never crash on partial data)
6. If `fetch_full_description=True`: fetch each job's detail URL, extract description, convert to markdown or keep as HTML
7. Paginate with `start` offset until `results_wanted` reached or Indeed returns no further results; `time.sleep(0.5–2.5)` between pages. No hard page cap — loop exits when the result list is empty or shorter than the page size.
8. Return `JobResponse(jobs=[...])` → normalized to `pd.DataFrame`

---

## Models (`model.py`)

### Enums

```python
class Site(str, Enum):
    INDEED = "indeed"
    # NAUKRI = "naukri"           # planned
    # GLASSDOOR = "glassdoor"     # planned
    # LINKEDIN = "linkedin"       # planned
    # FOUNDIT = "foundit"         # planned
    # SHINE = "shine"             # planned
    # INTERNSHALA = "internshala" # planned
    # UPWORK = "upwork"           # planned
    # APNA = "apna"               # planned

class Country(str, Enum):
    INDIA = "in"

class CompensationInterval(str, Enum):
    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    HOURLY = "hourly"

class JobType(str, Enum):
    FULL_TIME = "fulltime"
    PART_TIME = "parttime"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
```

### Core Models

```python
class Location(BaseModel):
    city: str | None = None
    state: str | None = None
    country: str | None = None

class Compensation(BaseModel):
    interval: CompensationInterval | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "INR"

class JobPost(BaseModel):
    id: str
    site: Site
    job_url: str
    job_url_direct: str | None = None
    title: str
    company: str | None = None
    location: Location | None = None
    date_posted: date | None = None
    job_type: list[JobType] | None = None
    compensation: Compensation | None = None
    is_remote: bool | None = None
    job_level: str | None = None
    description: str | None = None
    emails: list[str] | None = None
    company_url: str | None = None
    company_logo: str | None = None

class JobResponse(BaseModel):
    jobs: list[JobPost] = []

class ScraperInput(BaseModel):
    site_name: list[Site]
    search_term: str
    location: str | None = None
    distance: int | None = 50          # radius in km; passed as-is to Indeed's `radius` param
    hours_old: int | None = None       # filter to jobs posted within this many hours
    results_wanted: int = 20
    offset: int = 0                    # start from the Nth result (useful for pagination across calls)
    country_indeed: Country = Country.INDIA
    description_format: Literal["markdown", "html"] = "markdown"
    fetch_full_description: bool = True
    proxies: list[str] | None = None
    ca_cert: str | None = None         # path to CA bundle; passed to create_session()
    enforce_annual_salary: bool = False  # if True, convert_to_annual() normalizes all pay intervals
    user_agent: str | None = None      # overrides the default User-Agent in INDEED_HEADERS if set

class Scraper(ABC):
    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...
```

---

## Shared Utilities (`util.py`)

| Component | Description |
|---|---|
| `RotatingProxySession` | Base class that initializes a round-robin proxy cycle from a string or list; formats raw proxy strings into `{"http": ..., "https": ...}` dicts |
| `RequestsRotating` | Subclasses both `RotatingProxySession` and `requests.Session`; rotates proxies on each request, supports retry logic with configurable backoff, and optionally clears cookies between requests |
| `TLSRotating` | Wraps `tls_client.Session`; rotates `["chrome_120", "chrome_119", "firefox_108"]` identifiers. Falls back to `requests.Session` if `tls-client` unavailable |
| `create_session(...)` | Factory that returns either a `TLSRotating` or `RequestsRotating` session based on the `is_tls` flag; supports proxy, CA cert, retry, delay, and cookie-clearing options |
| `create_logger(name)` | Returns a `jobscraper:<name>` logger with `asctime - levelname - name - message` format; prevents duplicate handlers |
| `set_logger_level(verbose)` | Adjusts log level at runtime for all `jobscraper:*` loggers; maps `0→ERROR`, `1→WARNING`, `2→INFO` |
| `markdown_converter(html)` | Thin wrapper around `markdownify.markdownify()`; returns `None` for null input |
| `plain_converter(html)` | Strips HTML tags via BeautifulSoup and collapses whitespace into plain text |
| `extract_emails_from_text(text)` | Regex scan returning a list of email addresses found in a string |
| `get_enum_from_job_type(str)` | Matches a string against `JobType` enum values; returns the matching `JobType` or `None` |
| `get_enum_from_value(str)` | Same as above but raises an exception if no match is found |
| `currency_parser(str)` | Strips non-numeric characters, handles thousands separators and decimal commas, returns a rounded `float` |
| `extract_salary(str)` | Regex parses `$min–$max` patterns with optional `k` suffix; detects hourly/monthly/yearly interval by threshold comparison and optionally converts to annualized amounts; returns `(interval, min, max, currency)` |
| `extract_job_type(description)` | Scans job description text for keywords (`full time`, `part time`, `internship`, `contract`) and returns matching `JobType` enum list |
| `convert_to_annual(job_data)` | Mutates a job dict in-place, converting `min_amount`/`max_amount` from hourly, monthly, weekly, or daily rates to annual equivalents |
| `remove_attributes(tag)` | Strips all HTML attributes from a BeautifulSoup tag in-place |
| `map_str_to_site(name)` | Converts an uppercase string to its corresponding `Site` enum member |
| `desired_order` | Module-level list defining the canonical column ordering for job result output |

---

## Exceptions (`exception.py`)

```python
class IndeedException(Exception):
    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Indeed")

# class NaukriException(Exception): pass    # planned
# class GlassdoorException(Exception): pass # planned
```

---

## Entry Point (`jobscraper/__init__.py`)

`scrape_jobs()` validates input into a `ScraperInput`, instantiates the appropriate scraper via `SCRAPER_MAPPING`, runs it via `ThreadPoolExecutor`, and normalizes results into a pandas DataFrame. Phase 1 supports Indeed only.

```python
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
    # --- planned, not implemented in Phase 1 ---
    # google_search_term: str | None = None,
    # easy_apply: bool | None = None,
    # linkedin_fetch_description: bool | None = False,
    # linkedin_company_ids: list[int] | None = None,
) -> pd.DataFrame
```

```
Coerces site_name strings → Site enum values via map_str_to_site(); accepts a single string, a Site enum, or a mixed list of both
Converts country_indeed string → Country enum via Country.from_string(); converts job_type string → JobType enum via get_enum_from_value()
Passes verbose → set_logger_level() to configure jobscraper:* log output before dispatching
Builds a ScraperInput and dispatches to the Indeed scraper via ThreadPoolExecutor (Phase 1: Indeed only)
Flattens all JobResponse.jobs → pd.DataFrame with explicit nested flattening:

compensation.min_amount → min_amount, compensation.max_amount → max_amount, compensation.interval → interval, compensation.currency → currency
location → formatted string via Location.display_location()
job_type list → comma-joined string; emails list → comma-joined string

Falls back to extract_salary() on the description text when no structured compensation object is present; marks salary_source as DIRECT_DATA or DESCRIPTION accordingly
When enforce_annual_salary=True, calls convert_to_annual() to normalize hourly/monthly/weekly/daily pay to yearly before output
Drops all-NA columns before concat, ensures all desired_order columns are present (adding None for missing ones), and returns the final DataFrame sorted by ["site", "date_posted"] descending; returns an empty DataFrame if no jobs were found
```

---

## Indeed Scraper (`indeed/`)

### `indeed/constant.py`
- `INDEED_HEADERS` — Chrome 120 User-Agent, Accept-Language, Referer headers
- `BASE_URL = "https://{country}.indeed.com"`
- `JOBS_SEARCH_URL = BASE_URL + "/jobs"`
- `JOB_TYPE_MAP` — maps Indeed raw strings → `JobType` enum

### `indeed/util.py`
- `parse_mosaic_json(html: str) -> list[dict]` — extracts and parses `<script id="mosaic-data">` JSON
- `parse_compensation(job_data: dict) -> Compensation | None`
- `parse_location(raw: str) -> Location`
- `extract_emails(html: str) -> list[str]`
- `get_job_detail_url(job_key: str, country: Country) -> str`

### `indeed/__init__.py` — `IndeedScraper(Scraper)`

```
scrape(scraper_input) -> JobResponse:
1. Build search URL (q, l, start, limit params)
2. TLSRotating session fetches page (chrome_120); overrides User-Agent if scraper_input.user_agent is set
3. parse_mosaic_json() → list of job dicts
4. Each dict → JobPost (field-level try/except, log warnings on missing optional fields)
5. If fetch_full_description=True: fetch detail page per job
6. Paginate until results_wanted; exit early if Indeed returns empty or partial page
7. Handle errors with IndeedException + logger
8. Return JobResponse(jobs=[...])
```

**Anti-bot strategy:**
- `TLSRotating` with `chrome_120` identifier
- Randomized `time.sleep(0.5–2.5)` between page fetches
- Rotate proxies if provided
- `Referer: https://www.indeed.com` header

---

## Dependencies (`pyproject.toml`)

```toml
[tool.poetry.dependencies]
python = "^3.13"
requests = "^2.31"
tls-client = "^1.0"
pydantic = "^2.0"
pandas = "^2.0"
markdownify = "^0.11"
beautifulsoup4 = "^4.12"
lxml = "^4.9"

[tool.poetry.group.dev.dependencies]
black = "*"
pre-commit = "*"
pytest = "*"
```

---

## Smoke Test (`examples/test_indeed.py`)

```python
from jobscraper import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed"],
    search_term="software engineer",
    location="Bangalore",
    results_wanted=20,
    country_indeed="india",
    description_format="markdown",
)

print(jobs.columns.tolist())
print(jobs.head(3).to_string())
```

**Success criteria:** Non-empty DataFrame with at minimum: `title`, `company`, `location`, `job_url`, `date_posted`, `job_type`, `min_amount`, `max_amount`, `description`.

---

## Constraints

- Pydantic v2 (`model_config`, `field_validator`)
- All public functions/classes have docstrings
- Type hints everywhere
- No hardcoded credentials or API keys
- Scrapers never crash on partial data — `try/except` per field
- Log warnings (never raise) for missing optional fields
- `black` formatting must pass before committing