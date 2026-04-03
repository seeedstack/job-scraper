"""Tests for scrape_jobs() entry point."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import jobscraper
from jobscraper import scrape_jobs


def _make_mosaic_html(results: list[dict]) -> str:
    """Build minimal Indeed HTML with a mosaic-data script tag."""
    payload = {
        "metaData": {
            "mosaicProviderJobCardsModel": {
                "results": results,
            }
        }
    }
    json_str = json.dumps(payload)
    script = f'window.mosaic.providerData["mosaic-provider-jobcards"] = {json_str};'
    return f'<html><script id="mosaic-data">{script}</script></html>'


@pytest.fixture()
def mock_indeed_session():
    """Patch create_session in the indeed module to return a mock."""
    raw_jobs = [
        {
            "jobkey": "jk001",
            "title": "Software Engineer",
            "company": "TechCorp",
            "formattedLocation": "Bangalore, Karnataka",
        },
        {
            "jobkey": "jk002",
            "title": "Data Scientist",
            "company": "DataInc",
            "formattedLocation": "Mumbai, Maharashtra",
            "extractedSalary": {"min": 100000, "max": 150000, "type": "monthly"},
        },
    ]
    html = _make_mosaic_html(raw_jobs)
    mock_resp = MagicMock()
    mock_resp.text = html

    with patch("jobscraper.indeed.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_factory.return_value = mock_session
        yield


def test_scrape_jobs_returns_dataframe(mock_indeed_session) -> None:
    """scrape_jobs() returns a non-empty DataFrame for valid input."""
    df = scrape_jobs(site_name="indeed", search_term="engineer", results_wanted=2)
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2


def test_scrape_jobs_has_expected_columns(mock_indeed_session) -> None:
    """DataFrame contains key columns from desired_order."""
    df = scrape_jobs(site_name="indeed", search_term="engineer", results_wanted=2)
    for col in ["title", "company", "job_url", "site"]:
        assert col in df.columns, f"Missing column: {col}"


def test_scrape_jobs_salary_columns(mock_indeed_session) -> None:
    """Compensation is flattened into min_amount, max_amount, interval, currency."""
    df = scrape_jobs(site_name="indeed", search_term="data scientist", results_wanted=2)
    # The second job has extractedSalary
    row = df[df["title"] == "Data Scientist"].iloc[0]
    assert row["min_amount"] == 100000.0
    assert row["max_amount"] == 150000.0
    assert row["interval"] == "monthly"


def test_scrape_jobs_location_flattened(mock_indeed_session) -> None:
    """Location is a formatted string, not a nested object."""
    df = scrape_jobs(site_name="indeed", search_term="engineer", results_wanted=2)
    # pandas 3.x uses StringDtype; check the value rather than the dtype
    bng = df[df["title"] == "Software Engineer"]["location"].iloc[0]
    assert "Bangalore" in bng


def test_scrape_jobs_site_name_list(mock_indeed_session) -> None:
    """site_name accepts a list of strings."""
    df = scrape_jobs(site_name=["indeed"], search_term="engineer", results_wanted=2)
    assert len(df) == 2


def test_scrape_jobs_no_site_raises() -> None:
    """Raises ValueError when site_name is not provided."""
    with pytest.raises(ValueError):
        scrape_jobs(site_name=None, search_term="engineer")


def test_scrape_jobs_empty_results() -> None:
    """Returns empty DataFrame when Indeed returns no results."""
    html = _make_mosaic_html([])
    mock_resp = MagicMock()
    mock_resp.text = html

    with patch("jobscraper.indeed.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_resp
        mock_factory.return_value = mock_session

        df = scrape_jobs(site_name="indeed", search_term="engineer")

    assert isinstance(df, pd.DataFrame)
    assert len(df) == 0


def test_scrape_jobs_enforce_annual_salary(mock_indeed_session) -> None:
    """enforce_annual_salary=True normalizes monthly pay to annual."""
    df = scrape_jobs(
        site_name="indeed",
        search_term="data scientist",
        results_wanted=2,
        enforce_annual_salary=True,
    )
    row = df[df["title"] == "Data Scientist"].iloc[0]
    # 100000 monthly * 12 = 1200000
    assert row["min_amount"] == 1200000.0
    assert row["interval"] == "yearly"
