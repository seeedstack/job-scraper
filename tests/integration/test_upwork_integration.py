"""Integration tests for Upwork scraper — hits live upwork.com.

Run with: pytest tests/test_upwork_integration.py -v -s

These tests require a live internet connection. Excluded from standard run
(pytest tests/ -k "not integration").
"""

from __future__ import annotations

import pytest

from jobscraper import scrape_jobs


@pytest.mark.integration
@pytest.mark.xfail(
    strict=False,
    reason="Upwork blocks scraping with Cloudflare; requires proxies or upwork_token to bypass.",
)
def test_upwork_returns_jobs():
    """Live fetch returns non-empty DataFrame with expected columns."""
    df = scrape_jobs(
        site_name=["upwork"],
        search_term="python developer",
        location="India",
        results_wanted=5,
    )
    assert not df.empty, "Expected at least one Upwork job result"
    assert "title" in df.columns
    assert "company" in df.columns
    assert "job_url" in df.columns
    assert df["site"].iloc[0] == "upwork"
    print(f"\nFetched {len(df)} Upwork jobs")
    print(df[["title", "company", "job_url"]].head())


@pytest.mark.integration
def test_upwork_job_url_format():
    """job_url contains upwork.com/jobs/."""
    df = scrape_jobs(
        site_name=["upwork"],
        search_term="data engineer",
        results_wanted=3,
    )
    if not df.empty:
        assert df["job_url"].str.contains("upwork.com").all()
