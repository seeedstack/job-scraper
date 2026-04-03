"""Shared utilities: session factories, logging helpers, salary parsing, and converters."""

from __future__ import annotations

import itertools
import logging
import re
from typing import Any

import requests
from bs4 import BeautifulSoup
from markdownify import markdownify

from jobscraper.model import CompensationInterval, JobType, Site

# ---------------------------------------------------------------------------
# Module-level constant: canonical column ordering for job result output
# ---------------------------------------------------------------------------

desired_order: list[str] = [
    "id",
    "site",
    "job_url",
    "job_url_direct",
    "title",
    "company",
    "location",
    "date_posted",
    "job_type",
    "salary_source",
    "interval",
    "min_amount",
    "max_amount",
    "currency",
    "is_remote",
    "job_level",
    "company_url",
    "company_logo",
    "emails",
    "description",
]

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------


def create_logger(name: str) -> logging.Logger:
    """Return a jobscraper:<name> logger with asctime-levelname-name-message format.

    Prevents duplicate handlers by checking if any handlers are already attached.
    """
    logger = logging.getLogger(f"jobscraper:{name}")
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def set_logger_level(verbose: int) -> None:
    """Adjust log level for all jobscraper:* loggers.

    Maps 0 -> ERROR, 1 -> WARNING, 2 -> INFO. Values above 2 default to INFO.
    """
    level_map = {0: logging.ERROR, 1: logging.WARNING, 2: logging.INFO}
    level = level_map.get(verbose, logging.INFO)
    for name, logger in logging.Logger.manager.loggerDict.items():
        if name.startswith("jobscraper:") and isinstance(logger, logging.Logger):
            logger.setLevel(level)


# ---------------------------------------------------------------------------
# HTML / text converters
# ---------------------------------------------------------------------------


def markdown_converter(html: str | None) -> str | None:
    """Convert HTML to markdown using markdownify.

    Returns None for null input.
    """
    if html is None:
        return None
    return markdownify(html)


def plain_converter(html: str | None) -> str | None:
    """Strip HTML tags via BeautifulSoup and collapse whitespace into plain text.

    Returns None for null input.
    """
    if html is None:
        return None
    soup = BeautifulSoup(html, "lxml")
    return " ".join(soup.get_text().split())


def remove_attributes(tag: Any) -> None:
    """Strip all HTML attributes from a BeautifulSoup tag in-place.

    Modifies the tag and all its descendants directly.
    """
    for child in tag.find_all(True):
        child.attrs = {}
    tag.attrs = {}


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------


def extract_emails_from_text(text: str) -> list[str]:
    """Regex scan returning a list of email addresses found in the given text."""
    pattern = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return re.findall(pattern, text)


# ---------------------------------------------------------------------------
# Enum helpers
# ---------------------------------------------------------------------------


def get_enum_from_job_type(value: str) -> JobType | None:
    """Match a string against JobType enum values or names.

    Returns the matching JobType member, or None if no match is found.
    """
    value_lower = value.lower().strip()
    for member in JobType:
        if member.value == value_lower or member.name.lower() == value_lower:
            return member
    return None


def get_enum_from_value(value: str) -> JobType:
    """Same as get_enum_from_job_type but raises ValueError if no match is found."""
    result = get_enum_from_job_type(value)
    if result is None:
        raise ValueError(f"Unknown job type: {value!r}")
    return result


def map_str_to_site(name: str) -> Site:
    """Convert a string (case-insensitive) to the corresponding Site enum member.

    Raises ValueError if the name does not match any known site.
    """
    try:
        return Site[name.upper()]
    except KeyError:
        raise ValueError(f"Unknown site: {name!r}")


# ---------------------------------------------------------------------------
# Currency and salary parsing
# ---------------------------------------------------------------------------


def currency_parser(value: str) -> float:
    """Strip non-numeric characters, handle thousands separators, return rounded float.

    Handles European-style decimal commas: a comma is treated as a decimal separator
    only when there is exactly one comma, no period, and the part after the comma is
    NOT exactly 3 digits (which would indicate a thousands separator, e.g. "50,000").
    """
    cleaned = re.sub(r"[^\d.,]", "", value.strip())
    # Determine whether the comma is a decimal separator or a thousands separator.
    # If there is one comma, no dot, and the fractional part is exactly 3 digits,
    # it is a thousands separator (e.g. "50,000" → 50000).
    if cleaned.count(",") == 1 and "." not in cleaned:
        after_comma = cleaned.split(",")[1]
        if len(after_comma) == 3:
            # Thousands separator — remove it
            cleaned = cleaned.replace(",", "")
        else:
            # Decimal separator — replace with dot
            cleaned = cleaned.replace(",", ".")
    else:
        # Multiple commas or a dot present — treat all commas as thousands separators
        cleaned = cleaned.replace(",", "")
    return round(float(cleaned), 2)


def _annualize(
    interval: CompensationInterval, min_val: float, max_val: float
) -> tuple[float, float]:
    """Convert pay amounts to annual equivalents based on the given interval.

    Uses standard multipliers: hourly * 2080, daily * 260, weekly * 52, monthly * 12.
    """
    multipliers: dict[CompensationInterval, int] = {
        CompensationInterval.HOURLY: 2080,  # 40h * 52w
        CompensationInterval.DAILY: 260,
        CompensationInterval.WEEKLY: 52,
        CompensationInterval.MONTHLY: 12,
        CompensationInterval.YEARLY: 1,
    }
    mult = multipliers.get(interval, 1)
    return round(min_val * mult, 2), round(max_val * mult, 2)


def extract_salary(
    text: str, enforce_annual: bool = False
) -> tuple[str | None, float | None, float | None, str]:
    """Parse salary patterns like '$min-$max' with optional 'k' suffix.

    Detects interval by magnitude threshold:
      - avg <= 1000  -> hourly
      - avg <= 20000 -> monthly
      - otherwise    -> yearly

    When enforce_annual=True the amounts are converted to annual equivalents.

    Returns:
        (interval_str | None, min_amount | None, max_amount | None, currency)
    """
    currency = "INR"
    currency_symbols = {"$": "USD", "£": "GBP", "€": "EUR", "₹": "INR"}

    for sym, cur in currency_symbols.items():
        if sym in text:
            currency = cur
            break

    # Try to match a min–max range first
    pattern = r"([\d,\.]+)\s*[kK]?\s*[-\u2013to]+\s*([\d,\.]+)\s*[kK]?"
    match = re.search(pattern, text)

    if not match:
        # Fall back to a single number
        single = re.search(r"([\d,\.]+)\s*[kK]?", text)
        if not single:
            return None, None, None, currency
        val_str = single.group(1)
        try:
            val = currency_parser(val_str)
            if "k" in single.group(0).lower():
                val *= 1000
        except (ValueError, AttributeError):
            return None, None, None, currency
        min_val = max_val = val
    else:
        try:
            min_str, max_str = match.group(1), match.group(2)
            min_val = currency_parser(min_str)
            max_val = currency_parser(max_str)
            if "k" in match.group(0).lower():
                min_val *= 1000
                max_val *= 1000
        except (ValueError, AttributeError):
            return None, None, None, currency

    # Detect interval by magnitude of average value
    avg = (min_val + max_val) / 2
    if avg <= 1000:
        interval = CompensationInterval.HOURLY
    elif avg <= 20000:
        interval = CompensationInterval.MONTHLY
    else:
        interval = CompensationInterval.YEARLY

    if enforce_annual:
        min_val, max_val = _annualize(interval, min_val, max_val)
        interval = CompensationInterval.YEARLY

    return interval.value, min_val, max_val, currency


# ---------------------------------------------------------------------------
# Job type extraction from description text
# ---------------------------------------------------------------------------


def extract_job_type(description: str) -> list[JobType] | None:
    """Scan job description text for employment-type keywords.

    Returns a list of matching JobType enum values, or None if none are found.
    """
    text_lower = description.lower()
    keywords: dict[JobType, list[str]] = {
        JobType.FULL_TIME: ["full time", "full-time", "fulltime"],
        JobType.PART_TIME: ["part time", "part-time", "parttime"],
        JobType.INTERNSHIP: ["internship", "intern"],
        JobType.CONTRACT: ["contract", "contractor", "freelance"],
        JobType.TEMPORARY: ["temporary", "temp "],
    }
    found = [jt for jt, kws in keywords.items() if any(kw in text_lower for kw in kws)]
    return found if found else None


# ---------------------------------------------------------------------------
# Annual salary conversion (mutates job dict in-place)
# ---------------------------------------------------------------------------


def convert_to_annual(job_data: dict) -> None:
    """Mutate a job dict in-place, converting pay amounts to annual equivalents.

    Reads ``interval``, ``min_amount``, and ``max_amount`` from the dict and
    updates them when conversion is possible. Does nothing if interval is
    missing or unrecognised.
    """
    interval_str = job_data.get("interval")
    if not interval_str:
        return
    try:
        interval = CompensationInterval(interval_str)
    except ValueError:
        return

    min_val = job_data.get("min_amount")
    max_val = job_data.get("max_amount")

    if min_val is not None and max_val is not None:
        new_min, new_max = _annualize(interval, min_val, max_val)
        job_data["min_amount"] = new_min
        job_data["max_amount"] = new_max
        job_data["interval"] = CompensationInterval.YEARLY.value


# ---------------------------------------------------------------------------
# Proxy session classes
# ---------------------------------------------------------------------------


class RotatingProxySession:
    """Base class that round-robins proxies from a string or list.

    Accepts a comma-separated proxy string or a list of proxy strings.
    Formats raw proxy strings into ``{"http": ..., "https": ...}`` dicts.
    """

    def __init__(self, proxies: list[str] | str | None = None) -> None:
        """Initialize with optional proxy list or comma-separated string."""
        if isinstance(proxies, str):
            proxy_list = [p.strip() for p in proxies.split(",") if p.strip()]
        elif proxies:
            proxy_list = list(proxies)
        else:
            proxy_list = []
        self._proxy_cycle: itertools.cycle | None = (
            itertools.cycle(proxy_list) if proxy_list else None
        )

    def _get_proxy_dict(self) -> dict[str, str] | None:
        """Return the next proxy dict or None if no proxies are configured."""
        if self._proxy_cycle is None:
            return None
        proxy = next(self._proxy_cycle)
        return {"http": proxy, "https": proxy}


class RequestsRotating(RotatingProxySession, requests.Session):
    """requests.Session subclass with rotating proxy support.

    Rotates proxies on each request and optionally clears cookies between
    requests. Supports a custom CA certificate bundle.
    """

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
        clear_cookies: bool = False,
    ) -> None:
        """Initialize session with optional proxies, CA cert, and cookie clearing."""
        RotatingProxySession.__init__(self, proxies)
        requests.Session.__init__(self)
        if ca_cert:
            self.verify = ca_cert
        self._clear_cookies = clear_cookies

    def request(self, method: str, url: str, **kwargs):
        """Make an HTTP request with proxy rotation and optional cookie clearing."""
        if self._clear_cookies:
            self.cookies.clear()
        proxy = self._get_proxy_dict()
        if proxy:
            kwargs.setdefault("proxies", proxy)
        return super().request(method, url, **kwargs)


class TLSRotating(RotatingProxySession):
    """Wraps ``tls_client.Session`` with rotating TLS client identifiers.

    Cycles through ``["chrome_120", "chrome_119", "firefox_108"]`` identifiers.
    Falls back to a plain ``requests.Session`` if ``tls-client`` is not installed.
    """

    _IDENTIFIERS: list[str] = ["chrome_120", "chrome_119", "firefox_108"]

    def __init__(
        self,
        proxies: list[str] | str | None = None,
        ca_cert: str | None = None,
    ) -> None:
        """Initialize TLS session with identifier rotation and optional proxies."""
        super().__init__(proxies)
        self._ca_cert = ca_cert
        self._id_cycle: itertools.cycle = itertools.cycle(self._IDENTIFIERS)
        self._session = self._make_session()

    def _make_session(self):
        """Create a tls_client.Session or fall back to requests.Session."""
        try:
            import tls_client  # type: ignore[import]

            identifier = next(self._id_cycle)
            return tls_client.Session(
                client_identifier=identifier, random_tls_extension_order=True
            )
        except ImportError:
            return requests.Session()

    def get(self, url: str, **kwargs) -> Any:
        """Perform a GET request, injecting the next rotating proxy if available."""
        proxy = self._get_proxy_dict()
        if proxy:
            kwargs.setdefault("proxy", proxy.get("https"))
        return self._session.get(url, **kwargs)


def create_session(
    proxies: list[str] | str | None = None,
    ca_cert: str | None = None,
    is_tls: bool = True,
    clear_cookies: bool = False,
) -> TLSRotating | RequestsRotating:
    """Factory returning a TLSRotating or RequestsRotating session.

    Args:
        proxies: Optional proxy string or list of proxy strings.
        ca_cert: Optional path to a CA certificate bundle.
        is_tls: If True (default) returns a TLSRotating session; otherwise
            returns a RequestsRotating session.
        clear_cookies: Passed to RequestsRotating when is_tls=False.

    Returns:
        A configured session instance ready for HTTP requests.
    """
    if is_tls:
        return TLSRotating(proxies=proxies, ca_cert=ca_cert)
    return RequestsRotating(
        proxies=proxies, ca_cert=ca_cert, clear_cookies=clear_cookies
    )
