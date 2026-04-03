# Design: `jobscraper` — Multi-Platform Job Scraping Library

**Date:** 2026-04-02
**Status:** Approved
**Scope:** Phase 1 (core) + Phase 2 (Indeed scraper only)

---

## Overview

`jobscraper` is a Python library that scrapes job postings from multiple platforms and returns unified results as a `pandas.DataFrame`. Phase 1 implements the Indeed scraper for India only. Future scrapers (Naukri, Glassdoor, LinkedIn, Foundit, Shine, Internshala, Upwork, Apna) will follow the same module pattern.

**Import:** `import jobscraper`
**Published as:** `python-job-scraper`
**Python:** `^3.13`

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

pyproject.toml
.pre-commit-config.yaml
```

---

## Data Flow

1. `scrape_jobs()` validates args → `ScraperInput` → dispatches `IndeedScraper` via `ThreadPoolExecutor`
2. `IndeedScraper.scrape()` builds search URL for `in.indeed.com/jobs`
3. `TLSRotating` session (chrome_120 fingerprint) fetches the search results page
4. `parse_mosaic_json()` extracts `<script id="mosaic-data">` JSON blob → list of job dicts
5. Each job dict → `JobPost` via field-level `try/except` (never crash on partial data)
6. If `fetch_full_description=True`: fetch each job's detail URL, extract description, convert to markdown or keep as HTML
7. Paginate with `start` offset until `results_wanted` reached; `time.sleep(0.5–2.5)` between pages
8. Return `JobResponse(jobs=[...])` → normalized to `pd.DataFrame`

---

## Models (`model.py`)

### Enums

```python
class Site(str, Enum):
    INDEED = "indeed"
    # NAUKRI = "naukri"       # planned
    # GLASSDOOR = "glassdoor" # planned
    # LINKEDIN = "linkedin"   # planned
    # FOUNDIT = "foundit"     # planned
    # SHINE = "shine"         # planned
    # INTERNSHALA = "internshala" # planned
    # UPWORK = "upwork"       # planned
    # APNA = "apna"           # planned

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
    results_wanted: int = 20
    country_indeed: Country = Country.INDIA
    description_format: Literal["markdown", "html"] = "markdown"
    fetch_full_description: bool = True
    proxies: list[str] | None = None
    offset: int = 0

class Scraper(ABC):
    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...
```

---

## Shared Utilities (`util.py`)

| Component | Description |
|---|---|
| `RequestsRotating` | Subclasses `requests.Session`; cycles proxy list round-robin via `send()` override |
| `TLSRotating` | Wraps `tls_client.Session`; rotates `["chrome_120", "chrome_119", "firefox_108"]` identifiers. Falls back to `requests.Session` if `tls-client` unavailable |
| `extract_salary(text)` | Regex handles `₹4–8 LPA`, `₹50,000/month`, `$25/hr`; returns `(min, max, currency)` |
| `logger_factory(name)` | Returns logger with `[jobscraper.name] LEVEL: msg` format |
| `html_to_markdown(html)` | Thin wrapper around `markdownify.markdownify()` |

---

## Exceptions (`exception.py`)

```python
class IndeedException(Exception): pass
# class NaukriException(Exception): pass    # planned
# class GlassdoorException(Exception): pass # planned
```

---

## Entry Point (`__init__.py`)

```python
def scrape_jobs(
    site_name: str | list[str] | Site | list[Site],
    search_term: str,
    location: str | None = None,
    results_wanted: int = 20,
    country_indeed: str | Country = Country.INDIA,
    description_format: str = "markdown",
    fetch_full_description: bool = True,
    proxies: list[str] | None = None,
    offset: int = 0,
) -> pd.DataFrame
```

- Coerces `site_name` strings → `Site` enum values
- Builds `ScraperInput`, dispatches via `ThreadPoolExecutor`
- Flattens all `JobResponse.jobs` → `pd.DataFrame` via `model_dump()` with explicit nested flattening:
  - `compensation.min_amount` → `min_amount`, `compensation.max_amount` → `max_amount`, `compensation.interval` → `interval`, `compensation.currency` → `currency`
  - `location.city` → `city`, `location.state` → `state`, `location.country` → `country`
- Public exports: `scrape_jobs`, `Site`, `JobType`, `Country`, `Compensation`, `Location`

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
2. TLSRotating session fetches page (chrome_120)
3. parse_mosaic_json() → list of job dicts
4. Each dict → JobPost (field-level try/except, log warnings on missing optional fields)
5. If fetch_full_description=True: fetch detail page per job
6. Paginate until results_wanted; sleep 0.5–2.5s between pages
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
```

---

## Smoke Test (`examples/test_indeed.py`)

```python
from jobscraper import scrape_jobs, Site, Country

jobs = scrape_jobs(
    site_name=[Site.INDEED],
    search_term="software engineer",
    location="Bangalore",
    results_wanted=20,
    country_indeed=Country.INDIA,
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
