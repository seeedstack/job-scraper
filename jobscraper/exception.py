"""Custom exceptions for jobscraper.

This module defines platform-specific exception classes raised by scrapers
when they encounter unrecoverable errors. Future platform exceptions are
stubbed out as comments and will be uncommented as scrapers are added.
"""


class IndeedException(Exception):
    """Raised when the Indeed scraper encounters an unrecoverable error."""

    def __init__(self, message=None):
        super().__init__(message or "An error occurred with Indeed")


# class NaukriException(Exception): pass    # planned
# class GlassdoorException(Exception): pass # planned
