"""Smoke test for the Indeed scraper.

Run this script directly to verify the library works end-to-end
against the live Indeed India website:

    python examples/test_indeed.py

A successful run prints the DataFrame columns and the first 3 rows.
"""

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
