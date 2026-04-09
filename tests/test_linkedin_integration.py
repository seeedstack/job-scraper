"""Integration tests for the LinkedIn scraper against the live site.

Run with:
    pytest tests/test_linkedin_integration.py -m integration -v -s

With li_at cookie for Voyager API (richer data):
    LI_AT=your_cookie pytest tests/test_linkedin_integration.py -m integration -v -s

Skipped by default in the normal test suite.
"""

from __future__ import annotations

import os

import pytest

from jobscraper import scrape_jobs


def _cookies() -> dict[str, str] | None:
    li_at = os.environ.get("LI_AT")
    return {"li_at": li_at} if li_at else None


@pytest.mark.integration
def test_linkedin_returns_dataframe() -> None:
    """scrape_jobs() returns a non-empty DataFrame with expected columns."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="software engineer",
        location="Bangalore, India",
        results_wanted=5,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"

    required_cols = {"title", "company", "location", "job_url", "date_posted"}
    missing = required_cols - set(df.columns)
    assert not missing, f"Missing columns: {missing}"


@pytest.mark.integration
def test_linkedin_titles_are_strings() -> None:
    """All returned job titles are non-empty strings."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="data engineer",
        location="Mumbai, India",
        results_wanted=3,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert df["title"].notna().all(), "Some titles are null"
    assert (df["title"].str.strip() != "").all(), "Some titles are blank"


@pytest.mark.integration
def test_linkedin_job_urls_are_linkedin_links() -> None:
    """All job_url values point to linkedin.com."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="python developer",
        location="Hyderabad, India",
        results_wanted=3,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    bad = df[~df["job_url"].str.startswith("https://www.linkedin.com/jobs/view/")]
    assert bad.empty, f"Unexpected job URLs:\n{bad['job_url'].tolist()}"


@pytest.mark.integration
def test_linkedin_descriptions_fetched() -> None:
    """Jobs include non-empty descriptions when fetch_full_description=True."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="backend engineer",
        location="Bangalore, India",
        results_wanted=3,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    filled = df["description"].notna().sum()
    assert filled > 0, "No descriptions were fetched"


@pytest.mark.integration
def test_linkedin_apply_type_populated() -> None:
    """is_indeed_apply (LinkedIn Easy Apply flag) is populated for some results."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="software engineer",
        location="Bangalore, India",
        results_wanted=10,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert "is_indeed_apply" in df.columns, "Missing is_indeed_apply column"

    if _cookies():
        # With Voyager auth, easy apply flag should be populated
        assert df["is_indeed_apply"].notna().any(), (
            "is_indeed_apply is null for all jobs — Voyager applyMethod not parsed"
        )

        external = df[df["is_indeed_apply"] == False]  # noqa: E712
        if not external.empty:
            assert external["job_url_direct"].notna().any(), (
                "External jobs should have job_url_direct set"
            )

    print("\n=== Apply Type Breakdown ===")
    print(df[["title", "company", "is_indeed_apply", "job_url_direct"]].to_string(index=False))


@pytest.mark.integration
def test_linkedin_site_column_is_linkedin() -> None:
    """All rows have site='linkedin'."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="software engineer",
        location="Bangalore, India",
        results_wanted=3,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    assert (df["site"] == "linkedin").all(), "site column contains non-linkedin values"


@pytest.mark.integration
def test_linkedin_voyager_enrichment() -> None:
    """With li_at cookie, Voyager API enriches jobs with company and salary data."""
    if not _cookies():
        pytest.skip("LI_AT env var not set — skipping Voyager enrichment test")

    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="software engineer",
        location="Bangalore, India",
        results_wanted=5,
        description_format="markdown",
        cookies=_cookies(),
    )

    assert not df.empty, "Expected jobs but got empty DataFrame"
    # Voyager should enrich at least some jobs with company_url or company_logo
    enriched = df[df["company_url"].notna() | df["company_logo"].notna()]
    assert not enriched.empty, "No jobs enriched via Voyager (company_url/logo all null)"


@pytest.mark.integration
def test_linkedin_print_raw_data() -> None:
    """Pull live data and print the full DataFrame for manual inspection."""
    df = scrape_jobs(
        site_name=["linkedin"],
        search_term="software engineer",
        location="Bangalore, India",
        results_wanted=10,
        description_format="markdown",
        cookies=_cookies(),
        verbose=2,
    )

    print("\n=== Columns ===")
    print(df.columns.tolist())
    print(f"\n=== Shape: {df.shape} ===")
    print(f"\n=== Auth: {'Voyager (li_at)' if _cookies() else 'Public HTML'} ===")
    print("\n=== Full Data ===")
    with __import__("pandas").option_context(
        "display.max_columns", None,
        "display.max_colwidth", 80,
        "display.width", 200,
    ):
        print(df.to_string(index=False))

    assert not df.empty, "Expected jobs but got empty DataFrame"
