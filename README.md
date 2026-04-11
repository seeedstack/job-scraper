# python-job-scraper

Scrape job listings from multiple job sites with one function call. Results land in a single, normalized `pandas.DataFrame`.

**Supported sites:**

- [x] Indeed
- [x] Glassdoor
- [x] LinkedIn
- [ ] Naukri
- [ ] Foundit
- [ ] Shine
- [ ] Internshala
- [ ] Upwork
- [ ] Apna

```python
from jobscraper import scrape_jobs

jobs = scrape_jobs(
    site_name=["indeed", "glassdoor", "linkedin"],
    search_term="software engineer",
    location="Bangalore",
    results_wanted=20,
)
```

No API keys. No accounts. Chrome 120 TLS fingerprinting keeps requests looking like a real browser.

---

## Installation

**Requirements:** Python 3.13+

### With pip

```bash
pip install python-job-scraper                  # runtime only
```

### From source

```bash
git clone https://github.com/seeedstack/job-scraper.git
cd job-scraper

pip install .                          # runtime only
```

---

## Usage

### Single site

```python
jobs = scrape_jobs(
    site_name="indeed",
    search_term="data scientist",
    location="Mumbai",
    results_wanted=15,
    hours_old=48,          # only jobs posted in the last 48 hours
    job_type="fulltime",
)
print(jobs[["title", "company", "location", "date_posted", "min_amount"]].head())
```

### Multiple sites in parallel

```python
jobs = scrape_jobs(
    site_name=["indeed", "glassdoor", "linkedin"],
    search_term="product manager",
    location="Delhi",
    results_wanted=10,     # 10 per site → up to 30 total
    description_format="markdown",
)
```

### LinkedIn with authentication (richer data)

Without a cookie, LinkedIn returns public job cards — title, company, location, date.
With your `li_at` cookie, the Voyager API unlocks salary ranges, full descriptions, and direct apply URLs.

```bash
LI_AT=your_cookie python examples/test_linkedin.py
```

```python
jobs = scrape_jobs(
    site_name="linkedin",
    search_term="machine learning engineer",
    location="Hyderabad",
    cookies={"li_at": "your_li_at_cookie_value"},
    is_remote=True,
)
```

---

## Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `site_name` | `str \| list[str]` | **required** | `"indeed"`, `"glassdoor"`, `"linkedin"` |
| `search_term` | `str` | **required** | Job title or keyword |
| `location` | `str` | `None` | City or region |
| `results_wanted` | `int` | `20` | Max results **per site** |
| `hours_old` | `int` | `None` | Exclude jobs older than N hours |
| `job_type` | `str` | `None` | `"fulltime"` `"parttime"` `"contract"` `"internship"` |
| `is_remote` | `bool` | `False` | Remote jobs only (LinkedIn) |
| `distance` | `int` | `50` | Search radius in km |
| `country_indeed` | `str` | `"india"` | Country for Indeed |
| `description_format` | `str` | `"markdown"` | `"markdown"` or `"html"` |
| `enforce_annual_salary` | `bool` | `False` | Normalize all pay to annual |
| `offset` | `int` | `0` | Skip first N results (for pagination) |
| `cookies` | `dict` | `None` | Pass `{"li_at": "..."}` for LinkedIn Voyager |
| `proxies` | `str \| list` | `None` | Proxy URL(s) |
| `verbose` | `int` | `0` | `0`=errors `1`=warnings `2`=info |

---

## Output columns

| Column | Description |
|---|---|
| `site` | Source platform |
| `title` | Job title |
| `company` | Company name |
| `location` | City / state / country |
| `date_posted` | Posting date |
| `job_type` | Employment type |
| `is_remote` | Remote flag |
| `min_amount` / `max_amount` | Salary range |
| `interval` | Pay period: `hourly` `monthly` `yearly` |
| `currency` | Currency code |
| `description` | Full job description |
| `job_url` | Link to the listing |
| `job_url_direct` | Direct apply URL (when available) |
| `company_url` | Company profile URL |
| `emails` | Contact emails found in description |

All-NA columns are dropped automatically. Use `enforce_annual_salary=True` to normalize hourly/monthly/daily rates to annual before comparing across sites.

---

## Running tests

```bash
# Unit tests only
pytest tests/

# Include live integration tests (hits real sites)
pytest tests/ -m integration
```

---

## License

MIT © 2026 saran

This library is intended for personal and research use. Scraping job sites may conflict with their Terms of Service — use responsibly and at your own risk. No warranty is provided for the accuracy or availability of scraped data.
