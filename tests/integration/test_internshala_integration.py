"""Integration tests for Internshala scrapers — hits live internshala.com.

Run with: pytest tests/integration/test_internshala_integration.py -v -s

Excluded from standard run (pytest tests/ --ignore=tests/integration).
"""

from __future__ import annotations

import pytest

from jobscraper import scrape_jobs


@pytest.mark.integration
def test_internshala_jobs_returns_results():
    """Live fetch returns non-empty DataFrame for jobs."""
    df = scrape_jobs(
        site_name=["internshala_jobs"],
        search_term="python developer",
        location="Bangalore",
        results_wanted=5,
    )
    assert not df.empty, "Expected at least one Internshala job"
    assert "title" in df.columns
    assert "company" in df.columns
    assert df["site"].iloc[0] == "internshala_jobs"
    print(f"\nFetched {len(df)} Internshala jobs")
    print(df[["title", "company", "job_url"]].head())


@pytest.mark.integration
def test_internshala_internships_returns_results():
    """Live fetch returns non-empty DataFrame for internships."""
    df = scrape_jobs(
        site_name=["internshala_internships"],
        search_term="machine learning",
        results_wanted=5,
    )
    assert not df.empty, "Expected at least one Internshala internship"
    assert df["site"].iloc[0] == "internshala_internships"
    print(f"\nFetched {len(df)} Internshala internships")
    print(df[["title", "company"]].head())
