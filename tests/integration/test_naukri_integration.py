"""Integration tests for Naukri scraper (live site).

Note: Naukri.com uses Akamai WAF which blocks headless browser automation.
These tests are expected to fail unless run from a residential IP or with proxy.
"""

import pytest
from jobscraper.model import ScraperInput, Site
from jobscraper.naukri import NaukriScraper


@pytest.mark.integration
@pytest.mark.xfail(strict=False, reason="Naukri WAF blocks headless browser (Akamai)")
def test_naukri_scraper_live_search():
    """Test live Naukri search."""
    scraper = NaukriScraper()
    input_data = ScraperInput(
        site_name=[Site.NAUKRI],
        search_term="python",
        location="Bangalore",
        results_wanted=5,
    )
    response = scraper.scrape(input_data)
    assert response.jobs is not None
    # This assertion will fail due to WAF
    assert len(response.jobs) > 0


@pytest.mark.integration
@pytest.mark.xfail(strict=False, reason="Naukri WAF blocks headless browser")
def test_naukri_scraper_remote_jobs():
    """Test Naukri remote job search."""
    scraper = NaukriScraper()
    input_data = ScraperInput(
        site_name=[Site.NAUKRI],
        search_term="data scientist",
        location="Remote",
        results_wanted=5,
    )
    response = scraper.scrape(input_data)
    assert response.jobs is not None
