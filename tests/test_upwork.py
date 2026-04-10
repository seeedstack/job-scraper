"""Tests for the Upwork scraper."""

from __future__ import annotations

import pytest

from jobscraper.exception import UpworkException


# ---------------------------------------------------------------------------
# UpworkException
# ---------------------------------------------------------------------------

def test_upwork_exception_default_message():
    """Default message used when none provided."""
    exc = UpworkException()
    assert str(exc) == "An error occurred with Upwork"


def test_upwork_exception_custom_message():
    """Custom message is preserved."""
    exc = UpworkException("Bot check detected")
    assert str(exc) == "Bot check detected"


def test_upwork_exception_is_exception():
    """UpworkException is catchable as Exception."""
    with pytest.raises(Exception):
        raise UpworkException()


# ---------------------------------------------------------------------------
# parse_location
# ---------------------------------------------------------------------------

from jobscraper.upwork.util import parse_compensation, parse_location
from jobscraper.model import Compensation, CompensationInterval, Location


def test_parse_location_country_only():
    """Country-only string → Location with country set."""
    loc = parse_location("India")
    assert loc.country == "India"
    assert loc.city is None
    assert loc.state is None


def test_parse_location_city_country():
    """'City, Country' format → city and country set."""
    loc = parse_location("Bangalore, India")
    assert loc.city == "Bangalore"
    assert loc.country == "India"


def test_parse_location_worldwide():
    """'Worldwide' → country='Worldwide', city=None."""
    loc = parse_location("Worldwide")
    assert loc.country == "Worldwide"
    assert loc.city is None


def test_parse_location_empty():
    """Empty/None input → empty Location."""
    assert parse_location("") == Location()
    assert parse_location(None) == Location()


# ---------------------------------------------------------------------------
# parse_compensation — API path (dict input)
# ---------------------------------------------------------------------------

def test_parse_compensation_hourly():
    """Hourly budget dict → Compensation with HOURLY interval."""
    job = {
        "job": {
            "hourlyBudgetMin": 20.0,
            "hourlyBudgetMax": 40.0,
            "budget": {"currencyCode": "USD"},
        }
    }
    comp = parse_compensation(job)
    assert comp is not None
    assert comp.interval == CompensationInterval.HOURLY
    assert comp.min_amount == 20.0
    assert comp.max_amount == 40.0
    assert comp.currency == "USD"


def test_parse_compensation_fixed():
    """Fixed-price budget → Compensation with min_amount, max=None."""
    job = {
        "job": {
            "hourlyBudgetMin": None,
            "hourlyBudgetMax": None,
            "amount": 500.0,
            "budget": {"currencyCode": "USD"},
        }
    }
    comp = parse_compensation(job)
    assert comp is not None
    assert comp.min_amount == 500.0
    assert comp.max_amount is None
    assert comp.currency == "USD"


def test_parse_compensation_missing_budget():
    """No budget signal → returns None."""
    assert parse_compensation({}) is None
    assert parse_compensation({"job": {}}) is None


def test_parse_compensation_default_currency():
    """Missing currencyCode → defaults to USD."""
    job = {"job": {"hourlyBudgetMin": 10.0, "hourlyBudgetMax": 20.0, "budget": {}}}
    comp = parse_compensation(job)
    assert comp.currency == "USD"


# ---------------------------------------------------------------------------
# parse_search_html
# ---------------------------------------------------------------------------

import json as _json

from jobscraper.upwork.util import parse_search_html


def _make_search_html(jobs: list[dict]) -> str:
    """Build minimal Next.js search page HTML with embedded jobs."""
    data = {"props": {"pageProps": {"jobs": jobs}}}
    return f'<html><head><script id="__NEXT_DATA__" type="application/json">{_json.dumps(data)}</script></head><body></body></html>'


SAMPLE_JOBS = [
    {
        "id": "~01abc123",
        "title": "Python Developer",
        "job": {
            "hourlyBudgetMin": 20.0,
            "hourlyBudgetMax": 40.0,
            "budget": {"currencyCode": "USD"},
        },
        "client": {"companyName": "Acme Corp"},
        "location": {"country": "India"},
        "publishedOn": "2026-04-01",
        "description": "Build awesome things.",
        "contractorTier": 2,
        "jobType": "hourly",
    }
]


def test_parse_search_html_returns_jobs():
    """Extracts job list from __NEXT_DATA__ script tag."""
    html = _make_search_html(SAMPLE_JOBS)
    jobs = parse_search_html(html)
    assert len(jobs) == 1
    assert jobs[0]["id"] == "~01abc123"
    assert jobs[0]["title"] == "Python Developer"


def test_parse_search_html_empty_page():
    """Returns [] when jobs list is empty."""
    html = _make_search_html([])
    assert parse_search_html(html) == []


def test_parse_search_html_no_next_data():
    """Returns [] when no __NEXT_DATA__ script tag found."""
    assert parse_search_html("<html><body>nothing</body></html>") == []


def test_parse_search_html_bot_check_raises():
    """Raises UpworkException when bot-check signature found in HTML."""
    html = "<html><body>Please verify you are a human</body></html>"
    with pytest.raises(UpworkException, match="Bot check detected"):
        parse_search_html(html)


from jobscraper.upwork.util import parse_html_detail, parse_job_detail


# ---------------------------------------------------------------------------
# parse_job_detail — API path
# ---------------------------------------------------------------------------

SAMPLE_API_RESPONSE = {
    "title": "Python Developer",
    "description": "<p>Build awesome things with Python.</p>",
    "job": {
        "hourlyBudgetMin": 20.0,
        "hourlyBudgetMax": 40.0,
        "budget": {"currencyCode": "USD"},
        "jobType": "hourly",
    },
    "client": {
        "companyName": "Acme Corp",
        "companyUrl": "https://www.upwork.com/companies/~01company",
    },
    "location": {"country": "India"},
    "publishedOn": "2026-04-01",
    "applyUrl": "https://www.upwork.com/jobs/apply/~01abc123",
    "contractorTier": 2,
}


def test_parse_job_detail_fields():
    """Extracts all key fields from API response dict."""
    detail = parse_job_detail(SAMPLE_API_RESPONSE)
    assert detail["title"] == "Python Developer"
    assert detail["company"] == "Acme Corp"
    assert detail["company_url"] == "https://www.upwork.com/companies/~01company"
    assert detail["job_url_direct"] == "https://www.upwork.com/jobs/apply/~01abc123"
    assert detail["job_level"] == "hourly"
    assert "<p>" in detail["description_html"]


def test_parse_job_detail_missing_client():
    """Returns None for company fields when client absent."""
    detail = parse_job_detail({})
    assert detail["company"] is None
    assert detail["job_url_direct"] is None


# ---------------------------------------------------------------------------
# parse_html_detail — fallback HTML path
# ---------------------------------------------------------------------------

DETAIL_HTML = """
<html><body>
<div class="up-card-section job-description">
  <p>We need a Python expert.</p>
</div>
</body></html>
"""


def test_parse_html_detail_description():
    """Extracts description text from job detail HTML."""
    desc, direct_url = parse_html_detail(DETAIL_HTML, "markdown")
    assert "Python expert" in desc
    assert direct_url is None  # never available in public HTML


def test_parse_html_detail_empty_page():
    """Returns None description when description div absent."""
    desc, direct_url = parse_html_detail("<html><body></body></html>", "markdown")
    assert desc is None
    assert direct_url is None


# ---------------------------------------------------------------------------
# UpworkScraper integration tests
# ---------------------------------------------------------------------------

import json as _json2
from unittest.mock import MagicMock, patch

from jobscraper.upwork._scraper import UpworkScraper
from jobscraper.model import JobPost, JobType, ScraperInput, Site


def _make_scraper_input(**kwargs) -> ScraperInput:
    defaults = dict(
        site_name=[Site.UPWORK],
        search_term="python developer",
        location="India",
        results_wanted=2,
        fetch_full_description=False,
    )
    defaults.update(kwargs)
    return ScraperInput(**defaults)


def _make_next_data_html(jobs: list[dict]) -> str:
    data = {"props": {"pageProps": {"jobs": jobs}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{_json2.dumps(data)}</script>'


MOCK_JOBS = [
    {
        "id": "~01abc123",
        "title": "Python Dev",
        "job": {"hourlyBudgetMin": 20.0, "hourlyBudgetMax": 40.0, "budget": {"currencyCode": "USD"}, "jobType": "hourly"},
        "client": {"companyName": "Acme"},
        "location": {"country": "India"},
        "publishedOn": "2026-04-01",
        "description": "Build things.",
        "contractorTier": 2,
    }
]


@patch("jobscraper.upwork._scraper.create_session")
def test_upwork_scraper_returns_job_posts(mock_create_session):
    """Scraper returns JobResponse with correct JobPost fields."""
    mock_session = MagicMock()
    mock_create_session.return_value = mock_session

    mock_warmup = MagicMock()
    mock_warmup.status_code = 200
    mock_search_p1 = MagicMock()
    mock_search_p1.status_code = 200
    mock_search_p1.text = _make_next_data_html(MOCK_JOBS)
    mock_search_p2 = MagicMock()
    mock_search_p2.status_code = 200
    mock_search_p2.text = _make_next_data_html([])

    mock_session.get.side_effect = [mock_warmup, mock_search_p1, mock_search_p2]

    scraper = UpworkScraper()
    response = scraper.scrape(_make_scraper_input())

    assert len(response.jobs) == 1
    job = response.jobs[0]
    assert isinstance(job, JobPost)
    assert job.title == "Python Dev"
    assert job.site == Site.UPWORK
    assert job.company == "Acme"
    assert "upwork.com" in job.job_url
    assert job.compensation is not None
    assert job.compensation.currency == "USD"
    assert job.job_type == [JobType.CONTRACT]


@patch("jobscraper.upwork._scraper.create_session")
def test_upwork_scraper_respects_results_wanted(mock_create_session):
    """Stops collecting when results_wanted is reached."""
    mock_session = MagicMock()
    mock_create_session.return_value = mock_session

    mock_warmup = MagicMock()
    mock_warmup.status_code = 200

    many_jobs = [dict(MOCK_JOBS[0], id=f"~0{i}") for i in range(10)]
    mock_page = MagicMock()
    mock_page.status_code = 200
    mock_page.text = _make_next_data_html(many_jobs)

    mock_session.get.side_effect = [mock_warmup, mock_page]

    scraper = UpworkScraper()
    response = scraper.scrape(_make_scraper_input(results_wanted=3))
    assert len(response.jobs) <= 3
