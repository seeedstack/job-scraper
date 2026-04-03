"""Pydantic v2 models and Scraper abstract base class for jobscraper.

This module defines all shared data models, enums, and the abstract Scraper
interface used across all platform scrapers.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from enum import Enum
from typing import Literal

from pydantic import BaseModel


class Site(str, Enum):
    """Supported job platforms."""

    INDEED = "indeed"
    # NAUKRI = "naukri"           # planned
    # GLASSDOOR = "glassdoor"     # planned
    # LINKEDIN = "linkedin"       # planned
    # FOUNDIT = "foundit"         # planned
    # SHINE = "shine"             # planned
    # INTERNSHALA = "internshala" # planned
    # UPWORK = "upwork"           # planned
    # APNA = "apna"               # planned


class Country(str, Enum):
    """Supported countries for job searches."""

    INDIA = "in"

    @classmethod
    def from_string(cls, value: str) -> "Country":
        """Convert string like 'india' or 'in' to Country enum."""
        value_lower = value.lower().strip()
        mapping = {"india": cls.INDIA, "in": cls.INDIA}
        if value_lower in mapping:
            return mapping[value_lower]
        raise ValueError(f"Unknown country: {value!r}")


class CompensationInterval(str, Enum):
    """Pay interval for compensation amounts."""

    YEARLY = "yearly"
    MONTHLY = "monthly"
    WEEKLY = "weekly"
    DAILY = "daily"
    HOURLY = "hourly"


class JobType(str, Enum):
    """Employment type for a job posting."""

    FULL_TIME = "fulltime"
    PART_TIME = "parttime"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"


class Location(BaseModel):
    """Geographic location for a job posting."""

    city: str | None = None
    state: str | None = None
    country: str | None = None

    def display_location(self) -> str:
        """Return a human-readable location string."""
        parts = [p for p in [self.city, self.state, self.country] if p]
        return ", ".join(parts) if parts else ""


class Compensation(BaseModel):
    """Salary or pay information for a job posting."""

    interval: CompensationInterval | None = None
    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "INR"


class JobPost(BaseModel):
    """A single job posting with all available metadata."""

    id: str
    site: Site
    job_url: str
    job_url_direct: str | None = None
    title: str
    company: str | None = None
    location: Location | None = None
    date_posted: date | None = None
    job_type: list[JobType] | None = None
    compensation: Compensation | None = None
    is_remote: bool | None = None
    job_level: str | None = None
    description: str | None = None
    emails: list[str] | None = None
    company_url: str | None = None
    company_logo: str | None = None


class JobResponse(BaseModel):
    """Container for a list of job postings returned by a scraper."""

    jobs: list[JobPost] = []


class ScraperInput(BaseModel):
    """Validated input parameters passed to a scraper."""

    site_name: list[Site]
    search_term: str
    location: str | None = None
    distance: int | None = 50
    hours_old: int | None = None
    results_wanted: int = 20
    offset: int = 0
    country_indeed: Country = Country.INDIA
    description_format: Literal["markdown", "html"] = "markdown"
    fetch_full_description: bool = True
    proxies: list[str] | None = None
    ca_cert: str | None = None
    enforce_annual_salary: bool = False
    user_agent: str | None = None


class Scraper(ABC):
    """Abstract base class that all platform scrapers must implement."""

    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Run the scraper and return a JobResponse containing job postings."""
        ...
