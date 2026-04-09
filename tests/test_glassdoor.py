"""Unit tests for the Glassdoor scraper utilities and scraper (mocked HTTP)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from jobscraper.glassdoor import GlassdoorScraper
from jobscraper.glassdoor.util import (
    build_search_url,
    get_job_detail_url,
    parse_compensation,
    parse_html_jobs,
    parse_location,
    extract_emails,
)
from jobscraper.model import CompensationInterval, ScraperInput, Site


# ---------------------------------------------------------------------------
# parse_location
# ---------------------------------------------------------------------------


def test_parse_location_city_state() -> None:
    """Parse standard 'City, State' string."""
    loc = parse_location("Bengaluru, Karnataka")
    assert loc.city == "Bengaluru"
    assert loc.state == "Karnataka"


def test_parse_location_remote_prefix() -> None:
    """Strip 'Remote in' prefix."""
    loc = parse_location("Remote in Mumbai, Maharashtra")
    assert loc.city == "Mumbai"
    assert loc.state == "Maharashtra"


def test_parse_location_city_only() -> None:
    """Return city-only Location for bare city name."""
    loc = parse_location("Hyderabad")
    assert loc.city == "Hyderabad"
    assert loc.state is None


def test_parse_location_empty() -> None:
    """Return empty Location for empty string."""
    loc = parse_location("")
    assert loc.city is None
    assert loc.state is None


# ---------------------------------------------------------------------------
# parse_compensation
# ---------------------------------------------------------------------------


def test_parse_compensation_annual() -> None:
    """Parse annual pay range from payPeriodAdjustedPay."""
    header = {
        "payPeriod": "annual",
        "payPeriodAdjustedPay": {"p10": 1200000, "p90": 2400000},
    }
    comp = parse_compensation(header)
    assert comp is not None
    assert comp.min_amount == 1200000.0
    assert comp.max_amount == 2400000.0
    assert comp.interval == CompensationInterval.YEARLY


def test_parse_compensation_hourly() -> None:
    """Parse hourly pay range."""
    header = {
        "payPeriod": "hourly",
        "payPeriodAdjustedPay": {"p10": 500, "p90": 800},
    }
    comp = parse_compensation(header)
    assert comp is not None
    assert comp.interval == CompensationInterval.HOURLY


def test_parse_compensation_none_when_missing() -> None:
    """Return None when no pay data in header."""
    assert parse_compensation({}) is None
    assert parse_compensation({"payPeriodAdjustedPay": {}}) is None


# ---------------------------------------------------------------------------
# parse_html_jobs
# ---------------------------------------------------------------------------


def _make_search_html(jobviews: list[dict]) -> str:
    """Build a minimal HTML page with RSC-streamed job data that parse_html_jobs can parse."""
    listings = [{"jobview": jv} for jv in jobviews]
    inner = json.dumps(f'"jobListings":{json.dumps(listings)},"totalJobsCount":{len(listings)}')
    inner_str = inner[1:-1]  # strip surrounding quotes added by json.dumps
    return f'<html><body><script>self.__next_f.push([1,"{inner_str}"])</script></body></html>'


def test_parse_html_jobs_extracts_jobviews() -> None:
    """parse_html_jobs() returns jobview list from RSC HTML."""
    jv1 = {"header": {"jobTitleText": "SWE"}, "job": {"listingId": "1", "jobTitleText": "SWE"}, "overview": {}}
    jv2 = {"header": {"jobTitleText": "QA"}, "job": {"listingId": "2", "jobTitleText": "QA"}, "overview": {}}
    html = _make_search_html([jv1, jv2])
    result = parse_html_jobs(html)
    assert len(result) == 2
    assert result[0]["header"]["jobTitleText"] == "SWE"


def test_parse_html_jobs_empty_on_no_data() -> None:
    """parse_html_jobs() returns [] when page has no RSC job data."""
    assert parse_html_jobs("<html><body></body></html>") == []
    assert parse_html_jobs("") == []


# ---------------------------------------------------------------------------
# build_search_url
# ---------------------------------------------------------------------------


def test_build_search_url_page_one() -> None:
    """build_search_url() builds correct URL for page 1 (no _IP suffix)."""
    url = build_search_url("software engineer", "bengaluru-india", 2940587, page=1)
    assert "bengaluru-india" in url
    assert "software-engineer" in url
    assert "IC2940587" in url
    assert "_IP" not in url


def test_build_search_url_page_two() -> None:
    """build_search_url() adds _IP{n} suffix for pages > 1."""
    url = build_search_url("engineer", "mumbai-india", 2997372, page=2)
    assert "_IP2" in url


# ---------------------------------------------------------------------------
# get_job_detail_url
# ---------------------------------------------------------------------------


def test_get_job_detail_url() -> None:
    """Build correct Glassdoor job detail URL."""
    url = get_job_detail_url("123456789")
    assert url == "https://www.glassdoor.co.in/job-listing/jl=123456789"


# ---------------------------------------------------------------------------
# extract_emails
# ---------------------------------------------------------------------------


def test_extract_emails_from_html() -> None:
    """Extract email address from HTML."""
    html = "<p>Send resume to careers@example.com or hr@corp.in</p>"
    emails = extract_emails(html)
    assert "careers@example.com" in emails
    assert "hr@corp.in" in emails


def test_extract_emails_empty() -> None:
    """Return empty list when no emails in HTML."""
    assert extract_emails("<p>No contact info here.</p>") == []


# ---------------------------------------------------------------------------
# GlassdoorScraper unit tests (mocked HTTP)
# ---------------------------------------------------------------------------


def _make_scraper_input(**overrides) -> ScraperInput:
    """Build a minimal ScraperInput for GlassdoorScraper tests."""
    defaults = dict(
        site_name=[Site.GLASSDOOR],
        search_term="software engineer",
        location="Bangalore",
        results_wanted=2,
        fetch_full_description=False,
    )
    defaults.update(overrides)
    return ScraperInput(**defaults)


def _mock_response(data: dict, status: int = 200) -> MagicMock:
    """Build a mock HTTP response that returns JSON data."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = data
    resp.text = json.dumps(data)
    resp.cookies = {}
    return resp


def _make_jobview(listing_id: str, title: str, company: str = "Acme") -> dict:
    """Build a minimal Glassdoor jobview dict."""
    return {
        "header": {
            "jobTitleText": title,
            "employerNameFromSearch": company,
            "locationName": "Bangalore, Karnataka",
            "payPeriod": None,
            "payPeriodAdjustedPay": None,
            "easyApply": False,
            "jobLink": f"/job-listing/jl={listing_id}",
        },
        "job": {
            "listingId": listing_id,
            "description": None,
            "jobTypes": ["fulltime"],
            "pubDate": None,
            "isRemoteOrHybrid": False,
        },
        "overview": {"squareLogoUrl": None},
    }


def _mock_html_response(html: str, status: int = 200) -> MagicMock:
    """Build a mock HTTP response returning HTML text."""
    resp = MagicMock()
    resp.status_code = status
    resp.text = html
    resp.cookies = {}
    return resp


def test_glassdoor_scraper_returns_jobs() -> None:
    """GlassdoorScraper.scrape() returns JobPost objects from mocked HTML."""
    jv1 = _make_jobview("1001", "Backend Engineer")
    jv2 = _make_jobview("1002", "Frontend Engineer")
    search_html = _make_search_html([jv1, jv2])

    warmup_resp = _mock_html_response("<html></html>")
    search_resp = _mock_html_response(search_html)

    with patch("jobscraper.glassdoor.get_location_id", return_value=("bengaluru-india", 2940587)), \
         patch("jobscraper.glassdoor.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.side_effect = [warmup_resp, search_resp]
        mock_factory.return_value = mock_session

        result = GlassdoorScraper().scrape(_make_scraper_input())

    assert len(result.jobs) == 2
    assert result.jobs[0].title == "Backend Engineer"
    assert result.jobs[1].title == "Frontend Engineer"
    assert result.jobs[0].site == Site.GLASSDOOR


def test_glassdoor_scraper_empty_page_stops() -> None:
    """Scraper stops when HTML page contains no job listings."""
    warmup_resp = _mock_html_response("<html></html>")
    empty_resp = _mock_html_response("<html></html>")

    with patch("jobscraper.glassdoor.get_location_id", return_value=("bengaluru-india", 2940587)), \
         patch("jobscraper.glassdoor.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.side_effect = [warmup_resp, empty_resp]
        mock_factory.return_value = mock_session

        result = GlassdoorScraper().scrape(_make_scraper_input())

    assert result.jobs == []


def test_glassdoor_scraper_skips_missing_title() -> None:
    """Jobs with no title are skipped gracefully."""
    jv_bad = _make_jobview("2001", "")
    jv_bad["header"].pop("jobTitleText")
    jv_bad["job"].pop("jobTitleText", None)
    jv_good = _make_jobview("2002", "DevOps Engineer")
    search_html = _make_search_html([jv_bad, jv_good])

    warmup_resp = _mock_html_response("<html></html>")
    search_resp = _mock_html_response(search_html)

    with patch("jobscraper.glassdoor.get_location_id", return_value=("bengaluru-india", 2940587)), \
         patch("jobscraper.glassdoor.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.side_effect = [warmup_resp, search_resp]
        mock_factory.return_value = mock_session

        result = GlassdoorScraper().scrape(_make_scraper_input())

    assert len(result.jobs) == 1
    assert result.jobs[0].title == "DevOps Engineer"


def test_glassdoor_scraper_http_error_raises() -> None:
    """Scraper raises GlassdoorException on HTTP 403."""
    from jobscraper.exception import GlassdoorException

    warmup_resp = _mock_html_response("<html></html>")
    error_resp = _mock_html_response("", status=403)

    with patch("jobscraper.glassdoor.get_location_id", return_value=("bengaluru-india", 2940587)), \
         patch("jobscraper.glassdoor.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.side_effect = [warmup_resp, error_resp]
        mock_factory.return_value = mock_session

        with pytest.raises(GlassdoorException):
            GlassdoorScraper().scrape(_make_scraper_input())


def test_glassdoor_scraper_respects_results_wanted() -> None:
    """Scraper returns at most results_wanted jobs."""
    jobviews = [_make_jobview(str(i), f"Job {i}") for i in range(10)]
    search_html = _make_search_html(jobviews)

    warmup_resp = _mock_html_response("<html></html>")
    search_resp = _mock_html_response(search_html)

    with patch("jobscraper.glassdoor.get_location_id", return_value=("bengaluru-india", 2940587)), \
         patch("jobscraper.glassdoor.create_session") as mock_factory:
        mock_session = MagicMock()
        mock_session.get.side_effect = [warmup_resp, search_resp]
        mock_factory.return_value = mock_session

        result = GlassdoorScraper().scrape(_make_scraper_input(results_wanted=3))

    assert len(result.jobs) == 3
