"""Smoke test for the LinkedIn scraper.

Run:
    python examples/test_linkedin.py

To use authenticated Voyager API (richer data), set LI_AT env var:
    LI_AT=your_li_at_cookie python examples/test_linkedin.py
"""

from __future__ import annotations

import os

from jobscraper import scrape_jobs

li_at = os.environ.get("LI_AT")
cookies = {"li_at": li_at} if li_at else None

jobs = scrape_jobs(
    site_name=["linkedin"],
    search_term="software engineer",
    location="Bangalore, India",
    results_wanted=10,
    description_format="markdown",
    cookies=cookies,
    verbose=2,
)

print("Columns:", jobs.columns.tolist())
print(f"Jobs found: {len(jobs)}")
if not jobs.empty:
    print(jobs[["title", "company", "location", "date_posted"]].head(5).to_string())
