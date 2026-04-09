"""Tests for the LinkedIn scraper utilities."""

from __future__ import annotations

from datetime import date

import pytest

from jobscraper.linkedin.util import (
    build_search_params,
    parse_location,
    parse_search_html,
)
from jobscraper.model import ScraperInput, Site


# ---------------------------------------------------------------------------
# parse_search_html
# ---------------------------------------------------------------------------

SEARCH_HTML = """
<html><body>
<ul class="jobs-search__results-list">
  <li>
    <div class="base-card job-search-card"
         data-entity-urn="urn:li:jobPosting:9876543210">
      <a class="base-card__full-link"
         href="https://www.linkedin.com/jobs/view/software-engineer-9876543210">
      </a>
      <h3 class="base-search-card__title">Software Engineer</h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link">Acme Corp</a>
      </h4>
      <span class="job-search-card__location">Bengaluru, Karnataka, India</span>
      <time class="job-search-card__listdate" datetime="2026-04-01">2 weeks ago</time>
    </div>
  </li>
  <li>
    <div class="base-card job-search-card"
         data-entity-urn="urn:li:jobPosting:1111111111">
      <a class="base-card__full-link"
         href="https://www.linkedin.com/jobs/view/data-engineer-1111111111">
      </a>
      <h3 class="base-search-card__title">Data Engineer</h3>
      <h4 class="base-search-card__subtitle">
        <a class="hidden-nested-link">Widgets Inc</a>
      </h4>
      <span class="job-search-card__location">Mumbai, Maharashtra, India</span>
      <time class="job-search-card__listdate" datetime="2026-04-05">3 days ago</time>
    </div>
  </li>
</ul>
</body></html>
"""


def test_parse_search_html_count():
    """Returns one dict per job card."""
    jobs = parse_search_html(SEARCH_HTML)
    assert len(jobs) == 2


def test_parse_search_html_fields():
    """Extracts id, title, company, location, date, job_url."""
    jobs = parse_search_html(SEARCH_HTML)
    j = jobs[0]
    assert j["id"] == "9876543210"
    assert j["title"] == "Software Engineer"
    assert j["company"] == "Acme Corp"
    assert j["location"] == "Bengaluru, Karnataka, India"
    assert j["date"] == "2026-04-01"
    assert "linkedin.com/jobs/view" in j["job_url"]


def test_parse_search_html_empty():
    """Returns empty list when no job cards present."""
    assert parse_search_html("<html><body></body></html>") == []


# ---------------------------------------------------------------------------
# parse_location
# ---------------------------------------------------------------------------


def test_parse_location_three_parts():
    """Parses city, state, country from a three-part string."""
    loc = parse_location("Bengaluru, Karnataka, India")
    assert loc.city == "Bengaluru"
    assert loc.state == "Karnataka"
    assert loc.country == "India"


def test_parse_location_two_parts():
    """Parses city and state from a two-part string."""
    loc = parse_location("Mumbai, Maharashtra")
    assert loc.city == "Mumbai"
    assert loc.state == "Maharashtra"
    assert loc.country is None


def test_parse_location_city_only():
    """Parses bare city name."""
    loc = parse_location("Delhi")
    assert loc.city == "Delhi"
    assert loc.state is None


def test_parse_location_remote_prefix():
    """Strips 'Remote in' prefix."""
    loc = parse_location("Remote in Pune, Maharashtra, India")
    assert loc.city == "Pune"


def test_parse_location_empty():
    """Returns empty Location for empty string."""
    loc = parse_location("")
    assert loc.city is None


# ---------------------------------------------------------------------------
# build_search_params
# ---------------------------------------------------------------------------


def _make_input(**kwargs) -> ScraperInput:
    defaults = dict(site_name=[Site.LINKEDIN], search_term="engineer")
    defaults.update(kwargs)
    return ScraperInput(**defaults)


def test_build_search_params_basic():
    """Keywords and start always present."""
    params = build_search_params(_make_input(), start=0)
    assert params["keywords"] == "engineer"
    assert params["start"] == 0


def test_build_search_params_location():
    """Location included when set."""
    params = build_search_params(_make_input(location="Bangalore"), start=0)
    assert params["location"] == "Bangalore"


def test_build_search_params_no_location():
    """Location key absent when not set."""
    params = build_search_params(_make_input(), start=0)
    assert "location" not in params


def test_build_search_params_job_type():
    """job_type enum maps to LinkedIn filter code."""
    from jobscraper.model import JobType
    params = build_search_params(_make_input(job_type=JobType.FULL_TIME), start=0)
    assert params["f_JT"] == "F"


def test_build_search_params_hours_old():
    """hours_old converts to f_TPR in seconds."""
    params = build_search_params(_make_input(hours_old=24), start=0)
    assert params["f_TPR"] == "r86400"


def test_build_search_params_remote():
    """is_remote=True sets f_WT=2."""
    params = build_search_params(_make_input(is_remote=True), start=0)
    assert params["f_WT"] == "2"


def test_build_search_params_offset():
    """start offset passed through."""
    params = build_search_params(_make_input(), start=50)
    assert params["start"] == 50


# ---------------------------------------------------------------------------
# parse_voyager_job
# ---------------------------------------------------------------------------

from jobscraper.linkedin.util import (
    parse_compensation,
    parse_html_detail,
    parse_voyager_job,
)
from jobscraper.model import CompensationInterval


VOYAGER_RESPONSE = {
    "title": "Backend Engineer",
    "description": {"text": "<p>We are hiring.</p>"},
    "employmentStatus": "FULL_TIME",
    "workplaceTypes": ["REMOTE"],
    "listedAt": 1743984000000,
    "formattedLocation": "Bengaluru, Karnataka, India",
    "applyMethod": {
        "com.linkedin.voyager.jobs.OffsiteApply": {
            "websiteUrl": "https://careers.example.com/apply/123"
        }
    },
    "companyDetails": {
        "com.linkedin.voyager.deco.jobs.web.shared.WebJobPostingCompany": {
            "companyResolutionResult": {
                "name": "Example Corp",
                "url": "https://www.linkedin.com/company/example-corp",
                "logo": {
                    "com.linkedin.common.VectorImage": {
                        "rootUrl": "https://media.licdn.com/logo.png"
                    }
                },
            }
        }
    },
    "salary": {
        "salaryInsight": {
            "baseSalary": {
                "unitOfWork": "YEAR",
                "minValue": {"value": 1500000},
                "maxValue": {"value": 2500000},
                "currencyCode": "INR",
            }
        }
    },
}


def test_parse_voyager_job_title():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    assert parsed["title"] == "Backend Engineer"


def test_parse_voyager_job_description():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    assert "<p>We are hiring.</p>" in (parsed["description_html"] or "")


def test_parse_voyager_job_employment_status():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    assert parsed["employment_status"] == "full-time"


def test_parse_voyager_job_is_remote():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    assert parsed["is_remote"] is True


def test_parse_voyager_job_offsite_apply():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    assert parsed["job_url_direct"] == "https://careers.example.com/apply/123"
    assert parsed["is_easy_apply"] is False


def test_parse_voyager_job_company():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    assert parsed["company"] == "Example Corp"
    assert parsed["company_url"] == "https://www.linkedin.com/company/example-corp"
    assert "logo.png" in (parsed["company_logo"] or "")


def test_parse_voyager_job_salary():
    parsed = parse_voyager_job(VOYAGER_RESPONSE)
    s = parsed["salary"]
    assert s["min"] == 1500000
    assert s["max"] == 2500000
    assert s["currency"] == "INR"
    assert s["unit"] == "YEAR"


def test_parse_voyager_job_easy_apply():
    data = {**VOYAGER_RESPONSE, "applyMethod": {
        "com.linkedin.voyager.jobs.ComplexOnsiteApply": {}
    }}
    parsed = parse_voyager_job(data)
    assert parsed["is_easy_apply"] is True
    assert parsed["job_url_direct"] is None


def test_parse_voyager_job_missing_salary():
    data = {k: v for k, v in VOYAGER_RESPONSE.items() if k != "salary"}
    parsed = parse_voyager_job(data)
    assert parsed["salary"] is None


def test_parse_compensation_yearly():
    comp = parse_compensation({"min": 1200000, "max": 2000000, "currency": "INR", "unit": "YEAR"})
    assert comp is not None
    assert comp.interval == CompensationInterval.YEARLY
    assert comp.min_amount == 1200000.0
    assert comp.max_amount == 2000000.0
    assert comp.currency == "INR"


def test_parse_compensation_hourly():
    comp = parse_compensation({"min": 500, "max": 1000, "currency": "INR", "unit": "HOUR"})
    assert comp is not None
    assert comp.interval == CompensationInterval.HOURLY


def test_parse_compensation_none():
    assert parse_compensation(None) is None


def test_parse_compensation_empty():
    assert parse_compensation({}) is None


DETAIL_HTML_EXTERNAL = """
<html><body>
  <div class="show-more-less-html__markup">
    <p>We are a fast-growing startup. Contact jobs@example.com to apply.</p>
  </div>
  <a class="apply-button apply-button--link"
     href="https://careers.example.com/apply/999">Apply</a>
</body></html>
"""

DETAIL_HTML_EASY_APPLY = """
<html><body>
  <div class="show-more-less-html__markup">
    <p>Great opportunity at our company.</p>
  </div>
  <button class="jobs-apply-button">Easy Apply</button>
</body></html>
"""


def test_parse_html_detail_description():
    desc, _, _ = parse_html_detail(DETAIL_HTML_EXTERNAL, "markdown")
    assert desc is not None
    assert "fast-growing" in desc


def test_parse_html_detail_external_url():
    _, job_url_direct, _ = parse_html_detail(DETAIL_HTML_EXTERNAL, "markdown")
    assert job_url_direct == "https://careers.example.com/apply/999"


def test_parse_html_detail_easy_apply_no_url():
    _, job_url_direct, _ = parse_html_detail(DETAIL_HTML_EASY_APPLY, "markdown")
    assert job_url_direct is None


def test_parse_html_detail_emails():
    _, _, emails = parse_html_detail(DETAIL_HTML_EXTERNAL, "markdown")
    assert emails is not None
    assert "jobs@example.com" in emails


def test_parse_html_detail_html_format():
    desc, _, _ = parse_html_detail(DETAIL_HTML_EXTERNAL, "html")
    assert "<p>" in (desc or "")
