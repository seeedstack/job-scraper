"""Custom exceptions for jobscraper.

This module defines platform-specific exception classes raised by scrapers
when they encounter unrecoverable errors. Future platform exceptions are
stubbed out as comments and will be uncommented as scrapers are added.
"""

from __future__ import annotations


class IndeedException(Exception):
    """Raised when the Indeed scraper encounters an unrecoverable error."""

    def __init__(self, message: str | None = None):
        super().__init__(message or "An error occurred with Indeed")


class GlassdoorException(Exception):
    """Raised when the Glassdoor scraper encounters an unrecoverable error."""

    def __init__(self, message: str | None = None):
        super().__init__(message or "An error occurred with Glassdoor")


class LinkedInException(Exception):
    """Raised when the LinkedIn scraper encounters an unrecoverable error."""

    def __init__(self, message: str | None = None):
        super().__init__(message or "An error occurred with LinkedIn")


class UpworkException(Exception):
    """Raised when the Upwork scraper encounters an unrecoverable error."""

    def __init__(self, message: str | None = None):
        super().__init__(message or "An error occurred with Upwork")


class InternshalaException(Exception):
    """Raised when the Internshala scraper encounters an unrecoverable error."""

    def __init__(self, message: str | None = None):
        super().__init__(message or "An error occurred with Internshala")


# class NaukriException(Exception): pass    # planned
