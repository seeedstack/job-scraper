"""Tests for shared utilities in jobscraper.util."""

import jobscraper.util  # noqa: F401

import pytest

from jobscraper.model import (
    Compensation,
    Country,
    JobPost,
    Location,
    Site,
)


def test_location_display_location():
    """Full city/state/country produces a comma-separated string."""
    loc = Location(city="Bangalore", state="Karnataka", country="India")
    assert loc.display_location() == "Bangalore, Karnataka, India"


def test_location_display_location_partial():
    """Only the non-None parts appear in the output."""
    loc = Location(city="Mumbai")
    assert loc.display_location() == "Mumbai"


def test_location_display_location_empty():
    """An empty Location returns an empty string."""
    loc = Location()
    assert loc.display_location() == ""


def test_country_from_string():
    """Common string forms resolve to the correct Country enum member."""
    assert Country.from_string("india") == Country.INDIA
    assert Country.from_string("IN") == Country.INDIA


def test_country_from_string_invalid():
    """An unrecognised country string raises ValueError."""
    with pytest.raises(ValueError):
        Country.from_string("usa")


def test_job_post_minimal():
    """JobPost can be constructed with only required fields."""
    job = JobPost(
        id="1", site=Site.INDEED, job_url="https://example.com", title="Engineer"
    )
    assert job.company is None
    assert job.location is None


def test_compensation_defaults():
    """Compensation defaults to INR currency with no amounts set."""
    comp = Compensation()
    assert comp.currency == "INR"
    assert comp.min_amount is None
