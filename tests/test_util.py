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


# ---------------------------------------------------------------------------
# util.py tests
# ---------------------------------------------------------------------------

from jobscraper.util import (
    convert_to_annual,
    create_logger,
    currency_parser,
    desired_order,
    extract_emails_from_text,
    extract_job_type,
    extract_salary,
    get_enum_from_job_type,
    get_enum_from_value,
    map_str_to_site,
    markdown_converter,
    plain_converter,
)


def test_extract_emails_from_text():
    """Emails embedded in plain text are correctly extracted."""
    text = "Contact us at jobs@example.com or hr@company.co.in"
    emails = extract_emails_from_text(text)
    assert "jobs@example.com" in emails
    assert "hr@company.co.in" in emails


def test_currency_parser_simple():
    """Standard comma-separated thousands are parsed to a float."""
    assert currency_parser("50,000") == 50000.0
    assert currency_parser("1,00,000") == 100000.0


def test_extract_salary_range():
    """A min-max salary range string is correctly parsed."""
    interval, min_a, max_a, currency = extract_salary("50,000 - 80,000")
    assert min_a == 50000.0
    assert max_a == 80000.0


def test_extract_job_type_fulltime():
    """Full-time keyword is correctly mapped to the FULL_TIME enum."""
    from jobscraper.model import JobType

    result = extract_job_type("This is a full-time position")
    assert result is not None
    assert JobType.FULL_TIME in result


def test_convert_to_annual_monthly():
    """Monthly amounts are multiplied by 12 and interval set to yearly."""
    job = {"interval": "monthly", "min_amount": 100000.0, "max_amount": 150000.0}
    convert_to_annual(job)
    assert job["interval"] == "yearly"
    assert job["min_amount"] == 1200000.0


def test_get_enum_from_job_type():
    """Known job type string returns correct enum; unknown returns None."""
    from jobscraper.model import JobType

    assert get_enum_from_job_type("fulltime") == JobType.FULL_TIME
    assert get_enum_from_job_type("unknown") is None


def test_get_enum_from_value_raises():
    """get_enum_from_value raises ValueError for an unrecognised string."""
    with pytest.raises(ValueError):
        get_enum_from_value("unknownjobtype")


def test_map_str_to_site():
    """A lowercase site name string maps to the correct Site enum member."""
    assert map_str_to_site("indeed") == Site.INDEED


def test_markdown_converter_none():
    """markdown_converter returns None when given None."""
    assert markdown_converter(None) is None


def test_desired_order_has_key_columns():
    """desired_order contains the essential output columns."""
    assert "title" in desired_order
    assert "job_url" in desired_order
    assert "min_amount" in desired_order


def test_create_logger_no_duplicate_handlers():
    """Calling create_logger twice for the same name does not add duplicate handlers."""
    logger1 = create_logger("test_dedup")
    logger2 = create_logger("test_dedup")
    assert len(logger2.handlers) == 1
    assert logger1 is logger2


def test_plain_converter_strips_html():
    """plain_converter removes HTML tags and returns clean text."""
    result = plain_converter("<p>Hello <b>world</b></p>")
    assert result == "Hello world"


def test_plain_converter_none():
    """plain_converter returns None when given None."""
    assert plain_converter(None) is None
