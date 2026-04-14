"""Scrapling fetcher factory — maps ScraperProfile to concrete fetcher.

Workers call ``create_fetcher(profile, fetch_options)`` to get a
ready-to-use fetcher instance.

All scrapling imports are **lazy** so the slim API image does not crash
on startup when ``curl_cffi`` / browser libraries are absent.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.enums import ScraperProfile

logger = logging.getLogger(__name__)


def create_fetcher(
    profile: ScraperProfile,
    fetch_options: dict | None = None,
) -> Any:
    """Return a Scrapling fetcher configured for *profile*.

    Parameters
    ----------
    profile:
        One of the ``ScraperProfile`` enum values.
    fetch_options:
        Optional keyword arguments forwarded to the fetcher constructor
        (e.g. ``timeout``, ``impersonate``, ``stealthy_headers``).

    All imports are done inside this function so the API process can
    start without ``scrapling[fetchers]`` installed.
    """
    opts = fetch_options or {}

    if profile == ScraperProfile.FETCHER:
        from scrapling.fetchers import Fetcher
        return Fetcher(**opts)

    if profile == ScraperProfile.HTTP_SESSION:
        from scrapling.fetchers import FetcherSession
        return FetcherSession(**opts)

    if profile == ScraperProfile.STEALTH:
        from scrapling.fetchers import StealthyFetcher
        return StealthyFetcher(**opts)

    if profile == ScraperProfile.DYNAMIC:
        from scrapling.fetchers import DynamicFetcher
        return DynamicFetcher(**opts)

    if profile == ScraperProfile.SPIDER:
        from scrapling.fetchers import Fetcher
        logger.warning(
            "Spider profile requested via create_fetcher — "
            "returning basic Fetcher; use Spider classes for crawls."
        )
        return Fetcher(**opts)

    raise ValueError(f"Unknown scraper profile: {profile}")
