"""Unit tests for Naukri scraper parsing utilities."""

import pytest
from jobscraper.naukri.util import parse_location, parse_compensation, parse_search_html
from jobscraper.model import CompensationInterval


class TestParseLocation:
    """Test location parsing."""

    def test_city_only(self):
        result = parse_location("Bangalore")
        assert result.city == "Bangalore"
        assert result.country == "India"

    def test_city_state(self):
        result = parse_location("Bangalore, Karnataka")
        assert result.city == "Bangalore"
        assert result.state == "Karnataka"
        assert result.country == "India"

    def test_remote_variations(self):
        for remote_text in ["Remote", "Work from Home", "WFH", "Pan India"]:
            result = parse_location(remote_text)
            assert result.country == "India"
            assert result.city is None

    def test_empty(self):
        result = parse_location(None)
        assert result.country == "India"
        assert result.city is None


class TestParseCompensation:
    """Test compensation parsing."""

    def test_lpa_range(self):
        result = parse_compensation("₹4 - 7 LPA")
        assert result is not None
        assert result.min_amount == 400_000
        assert result.max_amount == 700_000
        assert result.interval == CompensationInterval.YEARLY
        assert result.currency == "INR"

    def test_monthly_range(self):
        result = parse_compensation("₹15,000 - ₹20,000 /month")
        assert result is not None
        assert result.min_amount == 15_000
        assert result.max_amount == 20_000
        assert result.interval == CompensationInterval.MONTHLY

    def test_daily_rate(self):
        result = parse_compensation("₹500 /day")
        assert result is not None
        assert result.min_amount == 500
        assert result.interval == CompensationInterval.DAILY

    def test_not_disclosed(self):
        result = parse_compensation("Not disclosed")
        assert result is None

    def test_empty(self):
        result = parse_compensation(None)
        assert result is None


class TestParseSearchHTML:
    """Test HTML parsing with mock Naukri HTML."""

    def test_parse_single_job_card(self):
        html = """
        <html>
        <article class="jobTuple" data-jobid="12345">
            <a class="jobTitle" href="/jobs/12345">Python Developer</a>
            <a class="companyName" href="/company/abc">Tech Corp</a>
            <span class="locWc">Bangalore</span>
            <span class="exp">3 - 5 years</span>
            <span class="sal">₹8 - 12 LPA</span>
            <span class="jobType">Full Time</span>
        </article>
        </html>
        """
        jobs = parse_search_html(html)
        assert len(jobs) == 1
        assert jobs[0]["id"] == "12345"
        assert jobs[0]["title"] == "Python Developer"
        assert jobs[0]["company"] == "Tech Corp"
        assert jobs[0]["location"] == "Bangalore"

    def test_parse_multiple_cards(self):
        html = """
        <html>
        <article class="jobTuple" data-jobid="111"><a class="jobTitle">Job 1</a></article>
        <article class="jobTuple" data-jobid="222"><a class="jobTitle">Job 2</a></article>
        </html>
        """
        jobs = parse_search_html(html)
        assert len(jobs) == 2

    def test_parse_empty_html(self):
        html = "<html></html>"
        jobs = parse_search_html(html)
        assert len(jobs) == 0
