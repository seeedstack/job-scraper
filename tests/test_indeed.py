"""Tests for the Indeed scraper utilities."""

from __future__ import annotations

from jobscraper.indeed.util import (
    extract_emails,
    get_job_detail_url,
    parse_compensation,
    parse_location,
    parse_mosaic_json,
)
from jobscraper.model import CompensationInterval, Country


def test_parse_location_city_state() -> None:
    """Parse a standard 'City, State' location string."""
    loc = parse_location("Bangalore, Karnataka")
    assert loc.city == "Bangalore"
    assert loc.state == "Karnataka"


def test_parse_location_remote_prefix() -> None:
    """Strip 'Remote in' prefix before parsing."""
    loc = parse_location("Remote in Mumbai, Maharashtra")
    assert loc.city == "Mumbai"
    assert loc.state == "Maharashtra"


def test_parse_location_with_pincode() -> None:
    """Strip trailing postal code from location string."""
    loc = parse_location("Hyderabad, Telangana 500001")
    assert loc.city == "Hyderabad"
    assert loc.state == "Telangana"


def test_parse_location_city_only() -> None:
    """Parse a location string with only a city name."""
    loc = parse_location("Delhi")
    assert loc.city == "Delhi"
    assert loc.state is None


def test_parse_location_empty() -> None:
    """Return empty Location for empty input."""
    loc = parse_location("")
    assert loc.city is None


def test_get_job_detail_url() -> None:
    """Build correct Indeed job detail URL for India."""
    url = get_job_detail_url("abc123", Country.INDIA)
    assert url == "https://in.indeed.com/viewjob?jk=abc123"


def test_extract_emails_from_html() -> None:
    """Extract email addresses from HTML content."""
    html = "<p>Contact: hr@company.com for details</p>"
    emails = extract_emails(html)
    assert "hr@company.com" in emails


def test_parse_compensation_extracted_salary() -> None:
    """Parse structured extractedSalary data from job dict."""
    job_data = {
        "extractedSalary": {
            "min": 50000,
            "max": 80000,
            "type": "monthly",
        }
    }
    comp = parse_compensation(job_data)
    assert comp is not None
    assert comp.min_amount == 50000.0
    assert comp.max_amount == 80000.0
    assert comp.interval == CompensationInterval.MONTHLY


def test_parse_compensation_none() -> None:
    """Return None when no salary data present."""
    assert parse_compensation({}) is None


def test_parse_mosaic_json_no_script() -> None:
    """Return empty list when no mosaic-data script tag present."""
    assert parse_mosaic_json("<html><body></body></html>") == []


def test_parse_compensation_salary_snippet() -> None:
    """Parse compensation from a salarySnippet text field."""
    job_data = {"salarySnippet": {"text": "50,000 - 80,000 a month"}}
    comp = parse_compensation(job_data)
    # Should parse successfully (may or may not detect interval from text)
    assert comp is not None
    assert comp.min_amount == 50000.0
    assert comp.max_amount == 80000.0


# ---------------------------------------------------------------------------
# IndeedScraper unit tests (mocked HTTP)
# ---------------------------------------------------------------------------


import json
from unittest.mock import MagicMock, patch

from jobscraper.indeed import IndeedScraper
from jobscraper.model import ScraperInput, Site


def _make_mosaic_html(results: list[dict]) -> str:
    """Build a minimal HTML page containing a mosaic-data script tag."""
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


def _make_scraper_input(**kwargs) -> ScraperInput:
    """Build a minimal ScraperInput for testing."""
    defaults = dict(
        site_name=[Site.INDEED],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=2,
        fetch_full_description=False,
    )
    defaults.update(kwargs)
    return ScraperInput(**defaults)


def test_indeed_scraper_returns_jobs() -> None:
    """IndeedScraper.scrape() returns JobPost objects from mocked HTML."""
    raw_jobs = [
        {
            "jobkey": "key1",
            "title": "SWE",
            "company": "Acme",
            "formattedLocation": "Bangalore, Karnataka",
        },
        {
            "jobkey": "key2",
            "title": "Backend Dev",
            "company": "Beta",
            "formattedLocation": "Mumbai, Maharashtra",
        },
    ]
    html = _make_mosaic_html(raw_jobs)

    mock_response = MagicMock()
    mock_response.text = html

    with patch("jobscraper.indeed.create_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_factory.return_value = mock_session

        scraper = IndeedScraper()
        result = scraper.scrape(_make_scraper_input())

    assert len(result.jobs) == 2
    assert result.jobs[0].title == "SWE"
    assert result.jobs[1].title == "Backend Dev"
    assert result.jobs[0].site == Site.INDEED


def test_indeed_scraper_empty_page_stops() -> None:
    """Scraper stops paginating when Indeed returns no results."""
    html = _make_mosaic_html([])

    mock_response = MagicMock()
    mock_response.text = html

    with patch("jobscraper.indeed.create_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_factory.return_value = mock_session

        scraper = IndeedScraper()
        result = scraper.scrape(_make_scraper_input())

    assert result.jobs == []


def test_indeed_scraper_skips_missing_title() -> None:
    """Jobs without a title are skipped gracefully."""
    raw_jobs = [
        {"jobkey": "key1"},  # no title
        {"jobkey": "key2", "title": "Engineer"},
    ]
    html = _make_mosaic_html(raw_jobs)

    mock_response = MagicMock()
    mock_response.text = html

    with patch("jobscraper.indeed.create_session") as mock_session_factory:
        mock_session = MagicMock()
        mock_session.get.return_value = mock_response
        mock_session_factory.return_value = mock_session

        scraper = IndeedScraper()
        result = scraper.scrape(_make_scraper_input())

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "Engineer"
