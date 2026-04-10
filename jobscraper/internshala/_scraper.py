"""Internshala job and internship scraper subclasses."""

from __future__ import annotations

from jobscraper.internshala._base import InternshalaScraper
from jobscraper.internshala.constant import INTERNSHIPS_URL, JOBS_URL
from jobscraper.model import Site


class InternshalaJobsScraper(InternshalaScraper):
    """Scraper for internshala.com/jobs listing pages."""

    _endpoint = JOBS_URL
    _mode = "jobs"
    _site = Site.INTERNSHALA_JOBS


class InternshalaInternshipsScraper(InternshalaScraper):
    """Scraper for internshala.com/internships listing pages."""

    _endpoint = INTERNSHIPS_URL
    _mode = "internships"
    _site = Site.INTERNSHALA_INTERNSHIPS
