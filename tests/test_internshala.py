"""Tests for the Internshala scraper."""

from __future__ import annotations

import pytest

from jobscraper.exception import InternshalaException


# ---------------------------------------------------------------------------
# InternshalaException
# ---------------------------------------------------------------------------

def test_internshala_exception_default_message():
    """Default message used when none provided."""
    exc = InternshalaException()
    assert str(exc) == "An error occurred with Internshala"


def test_internshala_exception_custom_message():
    """Custom message is preserved."""
    exc = InternshalaException("Rate limited after 3 retries")
    assert str(exc) == "Rate limited after 3 retries"


def test_internshala_exception_is_exception():
    """InternshalaException is catchable as Exception."""
    with pytest.raises(Exception):
        raise InternshalaException()


from jobscraper.internshala.util import parse_compensation, parse_location
from jobscraper.model import Compensation, CompensationInterval, Location


# ---------------------------------------------------------------------------
# parse_location
# ---------------------------------------------------------------------------

def test_parse_location_city_state():
    """'City, State' → Location with city, state, country=India."""
    loc = parse_location("Bangalore, Karnataka")
    assert loc.city == "Bangalore"
    assert loc.state == "Karnataka"
    assert loc.country == "India"


def test_parse_location_city_only():
    """Single token → city, country=India."""
    loc = parse_location("Mumbai")
    assert loc.city == "Mumbai"
    assert loc.country == "India"


def test_parse_location_work_from_home():
    """'Work from Home' → country=India, city=None."""
    loc = parse_location("Work from Home")
    assert loc.city is None
    assert loc.country == "India"


def test_parse_location_empty():
    """Empty/None input → Location with country=India."""
    assert parse_location("") == Location(country="India")
    assert parse_location(None) == Location(country="India")


# ---------------------------------------------------------------------------
# parse_compensation
# ---------------------------------------------------------------------------

def test_parse_compensation_lpa_range():
    """'₹ 3 - 5 LPA' → min=300000, max=500000, yearly, INR."""
    comp = parse_compensation("₹ 3 - 5 LPA")
    assert comp is not None
    assert comp.interval == CompensationInterval.YEARLY
    assert comp.min_amount == 300_000.0
    assert comp.max_amount == 500_000.0
    assert comp.currency == "INR"


def test_parse_compensation_monthly_stipend():
    """'₹ 15,000 /month' → min=15000, monthly, INR."""
    comp = parse_compensation("₹ 15,000 /month")
    assert comp is not None
    assert comp.interval == CompensationInterval.MONTHLY
    assert comp.min_amount == 15_000.0
    assert comp.currency == "INR"


def test_parse_compensation_performance_based():
    """'Performance based' → None."""
    assert parse_compensation("Performance based") is None


def test_parse_compensation_empty():
    """Empty/None → None."""
    assert parse_compensation("") is None
    assert parse_compensation(None) is None


# ---------------------------------------------------------------------------
# parse_listing_html
# ---------------------------------------------------------------------------

from jobscraper.internshala.util import parse_listing_html


JOBS_HTML = """
<html><body>
<div class="individual_internship" internshipid="123456" employment_type="job"
     data-href="/job/detail/123456/python-developer-job">
  <h2 class="job-internship-name">
    <a class="job-title-href" href="/job/detail/123456/python-developer-job">Python Developer</a>
  </h2>
  <p class="company-name">Acme Corp</p>
  <p class="row-1-item locations"><span><a>Bangalore, Karnataka</a></span></p>
  <div class="row-1-item">
    <span class="desktop">&#8377; 5 - 8 LPA</span>
    <span class="mobile">&#8377; 5 - 8 LPA</span>
  </div>
</div>
</body></html>
"""

INTERNSHIPS_HTML = """
<html><body>
<div class="individual_internship" internshipid="789" employment_type="internship"
     data-href="/internship/detail/789/ml-intern">
  <h2 class="job-internship-name">
    <a class="job-title-href" href="/internship/detail/789/ml-intern">ML Intern</a>
  </h2>
  <p class="company-name">Startup XYZ</p>
  <div class="row-1-item locations"><span><a>Work from Home</a></span></div>
  <div class="row-1-item">
    <span class="stipend">&#8377; 10,000 /month</span>
  </div>
  <div class="row-1-item">
    <span>3 Months</span>
  </div>
</div>
</body></html>
"""


def test_parse_listing_html_jobs_mode():
    """Extracts job card fields in jobs mode."""
    cards = parse_listing_html(JOBS_HTML, mode="jobs")
    assert len(cards) == 1
    c = cards[0]
    assert c["id"] == "123456"
    assert c["title"] == "Python Developer"
    assert c["company"] == "Acme Corp"
    assert c["location"] == "Bangalore, Karnataka"
    assert c["salary_raw"] == "₹ 5 - 8 LPA"
    assert c["job_type_raw"] == "Job"
    assert c["duration"] is None
    assert "internshala.com/job/detail/123456" in c["job_url"]


def test_parse_listing_html_internships_mode():
    """Extracts internship card fields including duration."""
    cards = parse_listing_html(INTERNSHIPS_HTML, mode="internships")
    assert len(cards) == 1
    c = cards[0]
    assert c["id"] == "789"
    assert c["title"] == "ML Intern"
    assert c["duration"] == "3 Months"
    assert c["location"] == "Work from Home"
    assert c["job_type_raw"] == "Internship"
    assert "internshala.com/internship/detail/789" in c["job_url"]


def test_parse_listing_html_empty():
    """Returns [] on page with no cards."""
    assert parse_listing_html("<html><body></body></html>", mode="jobs") == []


# ---------------------------------------------------------------------------
# Scraper tests
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock, patch

from jobscraper.internshala._scraper import (
    InternshalaInternshipsScraper,
    InternshalaJobsScraper,
)
from jobscraper.model import JobPost, JobType, ScraperInput, Site


def _make_scraper_input(site: Site, **kwargs) -> ScraperInput:
    defaults = dict(
        site_name=[site],
        search_term="python",
        location="Bangalore",
        results_wanted=2,
        fetch_full_description=False,
    )
    defaults.update(kwargs)
    return ScraperInput(**defaults)


JOBS_PAGE_HTML = """
<html><body>
<div class="individual_internship" internshipid="111" employment_type="job"
     data-href="/job/detail/111/python-dev">
  <h2 class="job-internship-name">
    <a class="job-title-href" href="/job/detail/111/python-dev">Python Dev</a>
  </h2>
  <p class="company-name">Acme</p>
  <p class="row-1-item locations"><span><a>Bangalore, Karnataka</a></span></p>
  <div class="row-1-item">
    <span class="desktop">&#8377; 5 - 8 LPA</span>
    <span class="mobile">&#8377; 5 - 8 LPA</span>
  </div>
</div>
</body></html>
"""

EMPTY_PAGE_HTML = "<html><body></body></html>"

INTERNSHIPS_PAGE_HTML = """
<html><body>
<div class="individual_internship" internshipid="222" employment_type="internship"
     data-href="/internship/detail/222/ml-intern">
  <h2 class="job-internship-name">
    <a class="job-title-href" href="/internship/detail/222/ml-intern">ML Intern</a>
  </h2>
  <p class="company-name">Startup</p>
  <div class="row-1-item locations"><span><a>Work from Home</a></span></div>
  <div class="row-1-item">
    <span class="stipend">&#8377; 10,000 /month</span>
  </div>
  <div class="row-1-item">
    <span>3 Months</span>
  </div>
</div>
</body></html>
"""


@patch("jobscraper.internshala._base.create_session")
def test_internshala_jobs_scraper_returns_jobs(mock_create_session):
    """InternshalaJobsScraper returns JobPosts with correct site."""
    mock_session = MagicMock()
    mock_create_session.return_value = mock_session

    mock_warmup = MagicMock()
    mock_warmup.status_code = 200
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.text = JOBS_PAGE_HTML
    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.text = EMPTY_PAGE_HTML

    mock_session.get.side_effect = [mock_warmup, mock_page1, mock_page2]

    scraper = InternshalaJobsScraper()
    response = scraper.scrape(_make_scraper_input(Site.INTERNSHALA_JOBS))

    assert len(response.jobs) == 1
    job = response.jobs[0]
    assert isinstance(job, JobPost)
    assert job.title == "Python Dev"
    assert job.site == Site.INTERNSHALA_JOBS
    assert job.company == "Acme"
    assert job.compensation is not None
    assert job.job_type == [JobType.FULL_TIME]
    assert job.job_level is None


@patch("jobscraper.internshala._base.create_session")
def test_internshala_internships_scraper_returns_internships(mock_create_session):
    """InternshalaInternshipsScraper sets is_remote=True for WFH and duration in description."""
    mock_session = MagicMock()
    mock_create_session.return_value = mock_session

    mock_warmup = MagicMock()
    mock_warmup.status_code = 200
    mock_page1 = MagicMock()
    mock_page1.status_code = 200
    mock_page1.text = INTERNSHIPS_PAGE_HTML
    mock_page2 = MagicMock()
    mock_page2.status_code = 200
    mock_page2.text = EMPTY_PAGE_HTML

    mock_session.get.side_effect = [mock_warmup, mock_page1, mock_page2]

    scraper = InternshalaInternshipsScraper()
    response = scraper.scrape(_make_scraper_input(Site.INTERNSHALA_INTERNSHIPS))

    assert len(response.jobs) == 1
    job = response.jobs[0]
    assert job.site == Site.INTERNSHALA_INTERNSHIPS
    assert job.is_remote is True
    assert job.job_level is None
    assert job.description is not None and "Duration: 3 Months" in job.description
    assert job.job_type == [JobType.INTERNSHIP]


@patch("jobscraper.internshala._base.create_session")
def test_internshala_retry_on_429(mock_create_session):
    """Scraper retries on 429 with exponential backoff."""
    mock_session = MagicMock()
    mock_create_session.return_value = mock_session

    mock_warmup = MagicMock()
    mock_warmup.status_code = 200
    mock_429 = MagicMock()
    mock_429.status_code = 429
    mock_ok = MagicMock()
    mock_ok.status_code = 200
    mock_ok.text = JOBS_PAGE_HTML
    mock_empty = MagicMock()
    mock_empty.status_code = 200
    mock_empty.text = EMPTY_PAGE_HTML

    mock_session.get.side_effect = [mock_warmup, mock_429, mock_429, mock_ok, mock_empty]

    with patch("jobscraper.internshala._base.time") as mock_time:
        mock_time.sleep = MagicMock()
        mock_time.sleep.return_value = None
        scraper = InternshalaJobsScraper()
        response = scraper.scrape(_make_scraper_input(Site.INTERNSHALA_JOBS))

    assert len(response.jobs) == 1
