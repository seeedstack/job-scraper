"""Integration tests for the Indeed scraper against the live site.

Run with:
    pytest tests/test_indeed_integration.py -m integration -v

Skipped by default in the normal test suite.
"""

from __future__ import annotations

import pytest

from jobscraper import scrape_jobs


@pytest.mark.integration
def test_scrape_jobs_returns_dataframe() -> None:
    """scrape_jobs() returns a non-empty DataFrame with expected columns."""
    df = scrape_jobs(
        site_name=["indeed"],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=5,
        country_indeed="india",
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"

    required_cols = {"title", "company", "location", "job_url", "date_posted"}
    missing = required_cols - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


@pytest.mark.integration
def test_scrape_jobs_titles_are_strings() -> None:
    """All returned job titles are non-empty strings."""
    df = scrape_jobs(
        site_name=["indeed"],
        search_term="data engineer",
        location="Mumbai",
        results_wanted=3,
        country_indeed="india",
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert df["title"].notna().all(), "Some titles are null"
    assert (df["title"].str.strip() != "").all(), "Some titles are blank"


@pytest.mark.integration
def test_scrape_jobs_job_urls_are_indeed_links() -> None:
    """All job_url values point to in.indeed.com."""
    df = scrape_jobs(
        site_name=["indeed"],
        search_term="python developer",
        location="Hyderabad",
        results_wanted=3,
        country_indeed="india",
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    bad = df[~df["job_url"].str.startswith("https://in.indeed.com/")]
    assert bad.empty, f"Unexpected job URLs:\n{bad['job_url'].tolist()}"


@pytest.mark.integration
def test_scrape_jobs_descriptions_fetched() -> None:
    """Jobs include non-empty descriptions when fetch_full_description=True."""
    df = scrape_jobs(
        site_name=["indeed"],
        search_term="backend engineer",
        location="Bangalore",
        results_wanted=3,
        country_indeed="india",
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    filled = df["description"].notna().sum()
    assert filled > 0, "No descriptions were fetched"


@pytest.mark.integration
def test_scrape_jobs_apply_type() -> None:
    """is_indeed_apply is populated and job_url_direct set for external jobs."""
    df = scrape_jobs(
        site_name=["indeed"],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=10,
        country_indeed="india",
        description_format="markdown",
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert "is_indeed_apply" in df.columns, "Missing is_indeed_apply column"

    known = df["is_indeed_apply"].notna()
    assert known.any(), "is_indeed_apply is null for all jobs — mosaic field not parsed"

    external = df[df["is_indeed_apply"] == False]  # noqa: E712
    if not external.empty:
        assert external["job_url_direct"].notna().any(), (
            "External jobs should have job_url_direct set"
        )

    indeed_apply = df[df["is_indeed_apply"] == True]  # noqa: E712
    if not indeed_apply.empty:
        # Indeed Easy Apply jobs link back to indeed, not a third-party ATS
        filled = indeed_apply["job_url_direct"].dropna()
        bad = filled[~filled.str.contains("indeed.com", na=False)]
        assert bad.empty, f"Indeed Apply jobs have non-Indeed direct URLs:\n{bad.tolist()}"

    print("\n=== Apply Type Breakdown ===")
    print(df[["title", "company", "is_indeed_apply", "job_url_direct"]].to_string(index=False))


@pytest.mark.integration
def test_scrape_jobs_print_raw_data() -> None:
    """Pull live data and print the full DataFrame for manual inspection."""
    df = scrape_jobs(
        site_name=["indeed"],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=10,
        country_indeed="india",
        description_format="markdown",
        verbose=2,
    )

    print("\n=== Columns ===")
    print(df.columns.tolist())
    print(f"\n=== Shape: {df.shape} ===")
    print("\n=== Full Data ===")
    with __import__("pandas").option_context("display.max_columns", None, "display.max_colwidth", 80, "display.width", 200):
        print(df.to_string(index=False))

    assert not df.empty, "Expected jobs but got empty DataFrame"
