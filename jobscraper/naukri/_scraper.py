"""Naukri scraper implementation using headless browser."""

from __future__ import annotations

import random
import time
from datetime import date
from typing import Any

from jobscraper.exception import NaukriException
from jobscraper.model import JobPost, JobResponse, Scraper, ScraperInput, Site
from jobscraper.naukri.constant import NAUKRI_HEADERS, JOB_TYPE_MAP, SEARCH_URL
from jobscraper.naukri.util import (
    parse_compensation,
    parse_location,
    parse_search_html,
)
from jobscraper.util import create_logger, get_enum_from_job_type, markdown_converter

logger = create_logger("naukri")


class NaukriScraper(Scraper):
    """Scraper for naukri.com using headless browser (Playwright).

    Uses browser automation to render CSR-based page and extract job listings.
    """

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        """Fetch job listings from Naukri.

        Args:
            scraper_input: Validated scraper config.

        Returns:
            JobResponse with collected JobPost objects.

        Raises:
            NaukriException: If browser launch fails or critical error occurs.
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise NaukriException(
                "Playwright required for Naukri scraper. "
                "Install: pip install playwright && playwright install"
            )

        jobs: list[JobPost] = []
        page = None
        browser = None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # Bypass headless detection
                page = browser.new_page(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                )

                # Add headers to bypass detection
                page.set_extra_http_headers({
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
                    "Accept-Language": "en-US,en;q=0.9",
                    "Sec-Fetch-Dest": "document",
                    "Sec-Fetch-Mode": "navigate",
                    "Sec-Fetch-Site": "none",
                    "Sec-Fetch-User": "?1",
                })

                page_no = 1
                while len(jobs) < scraper_input.results_wanted:
                    try:
                        url = self._build_url(
                            scraper_input.search_term,
                            scraper_input.location,
                            page_no,
                        )
                        logger.info(f"Fetching page {page_no}: {url}")
                        page.goto(url, wait_until="networkidle", timeout=30000)
                        time.sleep(random.uniform(0.5, 1.5))

                        html = page.content()
                        job_cards = parse_search_html(html)

                        if not job_cards:
                            logger.info("No more jobs found")
                            break

                        for card in job_cards:
                            if len(jobs) >= scraper_input.results_wanted:
                                break

                            try:
                                job = self._card_to_jobpost(card)
                                jobs.append(job)
                            except Exception as e:
                                logger.warning(f"Failed to parse card {card.get('id')}: {e}")
                                continue

                        page_no += 1
                        time.sleep(random.uniform(0.5, 1.5))

                    except Exception as e:
                        logger.error(f"Error on page {page_no}: {e}")
                        break

        except NaukriException:
            raise
        except Exception as e:
            raise NaukriException(f"Browser error: {e}")
        finally:
            if page:
                page.close()
            if browser:
                browser.close()

        return JobResponse(jobs=jobs)

    def _build_url(self, search_term: str, location: str | None, page: int) -> str:
        """Build Naukri search URL."""
        url = SEARCH_URL
        params = [f"keyword={search_term}"]
        if location:
            params.append(f"location={location}")
        params.append(f"pageNo={page}")
        return f"{url}?{'&'.join(params)}"

    def _card_to_jobpost(self, card: dict[str, Any]) -> JobPost:
        """Convert job card dict to JobPost."""
        return JobPost(
            id=str(card.get("id", "")),
            site=Site.NAUKRI,
            job_url=card.get("job_url") or f"https://www.naukri.com/jobs/{card.get('id')}",
            title=card.get("title") or "Unknown",
            company=card.get("company"),
            location=parse_location(card.get("location")),
            compensation=parse_compensation(card.get("salary")),
            job_type=[JOB_TYPE_MAP.get(card.get("job_type"), None)],
            is_remote=None,
            job_level=card.get("experience"),
            description=None,
        )
