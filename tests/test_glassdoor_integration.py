"""Integration tests for the Glassdoor scraper against the live site.

Run with:
    pytest tests/test_glassdoor_integration.py -m integration -v -s

Skipped by default in the normal test suite.
"""

from __future__ import annotations

import pytest

from jobscraper import scrape_jobs


@pytest.mark.integration
def test_glassdoor_returns_dataframe() -> None:
    """scrape_jobs() returns a non-empty DataFrame with expected columns."""
    df = scrape_jobs(
        site_name=["glassdoor"],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=5,
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"

    required_cols = {"title", "company", "location", "job_url", "date_posted"}
    missing = required_cols - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


@pytest.mark.integration
def test_glassdoor_titles_are_strings() -> None:
    """All returned job titles are non-empty strings."""
    df = scrape_jobs(
        site_name=["glassdoor"],
        search_term="data engineer",
        location="Mumbai",
        results_wanted=3,
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert df["title"].notna().all(), "Some titles are null"
    assert (df["title"].str.strip() != "").all(), "Some titles are blank"


@pytest.mark.integration
def test_glassdoor_job_urls_are_glassdoor_links() -> None:
    """All job_url values point to glassdoor.co.in."""
    df = scrape_jobs(
        site_name=["glassdoor"],
        search_term="python developer",
        location="Hyderabad",
        results_wanted=3,
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    bad = df[~df["job_url"].str.startswith("https://www.glassdoor.co.in/")]
    assert bad.empty, f"Unexpected job URLs:\n{bad['job_url'].tolist()}"


@pytest.mark.integration
def test_glassdoor_apply_type_populated() -> None:
    """is_indeed_apply (easy apply flag) is populated for some results."""
    df = scrape_jobs(
        site_name=["glassdoor"],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=5,
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert "is_indeed_apply" in df.columns, "Missing is_indeed_apply column"
    # At least some jobs should have a known easy-apply value
    assert df["is_indeed_apply"].notna().any(), "is_indeed_apply is null for all jobs"


@pytest.mark.integration
def test_glassdoor_print_raw_data() -> None:
    """Pull live data and print the full DataFrame for manual inspection."""
    df = scrape_jobs(
        site_name=["glassdoor"],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=10,
        description_format="markdown",
        verbose=2,
    )

    print("\n=== Columns ===")
    print(df.columns.tolist())
    print(f"\n=== Shape: {df.shape} ===")
    print("\n=== Full Data ===")
    with __import__("pandas").option_context(
        "display.max_columns", None,
        "display.max_colwidth", 80,
        "display.width", 200,
    ):
        print(df.to_string(index=False))

    assert not df.empty, "Expected jobs but got empty DataFrame"
