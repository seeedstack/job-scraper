"""Constants for the Upwork scraper."""

from __future__ import annotations

BASE_URL = "https://www.upwork.com"
SEARCH_URL = BASE_URL + "/nx/search/jobs"
API_JOB_URL = BASE_URL + "/api/v3/jobs/{job_id}"

UPWORK_HEADERS: dict[str, str] = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": BASE_URL + "/",
}

UPWORK_API_HEADERS: dict[str, str] = {
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
    "Referer": SEARCH_URL,
}

# Strings that appear in Upwork's bot-challenge / CAPTCHA pages.
BOT_CHECK_SIGNATURES: list[str] = [
    "_Incapsula_Resource",
    "Please verify you are a human",
    "Ray ID:",
    "cf-browser-verification",
    "challenge-form",
    "captcha",
    "<title>Challenge - Upwork</title>",
    "challenge-running",
]
