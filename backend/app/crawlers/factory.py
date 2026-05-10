"""Scrapling fetcher factory — maps ScraperProfile to concrete fetcher.

Workers call ``create_fetcher(profile)`` to get a ready-to-use fetcher
instance.  HTTP options (timeout, impersonate, etc.) must be passed
per-request to ``.get()`` since Scrapling v0.4+ silently discards
constructor kwargs and logs a deprecation warning.

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
    # Deprecated: kept for backward-compat but silently ignored by
    # Scrapling since v0.4.  Pass HTTP opts to .get() instead.
    fetch_options: dict | None = None,
) -> Any:
    """Return a Scrapling fetcher configured for *profile*.

    Parameters
    ----------
    profile:
        One of the ``ScraperProfile`` enum values.
    fetch_options:
        **Deprecated** — Scrapling v0.4+ ignores constructor kwargs.
        Pass HTTP options (timeout, impersonate, etc.) directly to
        ``fetcher.get(url, **opts)`` instead.

    All imports are done inside this function so the API process can
    start without ``scrapling[fetchers]`` installed.
    """
    if fetch_options:
        logger.warning(
            "create_fetcher: fetch_options are deprecated (Scrapling v0.4+ "
            "ignores constructor kwargs).  Pass HTTP options to .get() instead."
        )

    if profile == ScraperProfile.FETCHER:
        from scrapling.fetchers import Fetcher
        return Fetcher()

    if profile == ScraperProfile.HTTP_SESSION:
        from scrapling.fetchers import FetcherSession
        return FetcherSession()

    if profile == ScraperProfile.STEALTH:
        from scrapling.fetchers import StealthyFetcher
        return StealthyFetcher()

    if profile == ScraperProfile.DYNAMIC:
        from scrapling.fetchers import DynamicFetcher
        return DynamicFetcher()

    if profile == ScraperProfile.SPIDER:
        from scrapling.fetchers import Fetcher
        logger.warning(
            "Spider profile requested via create_fetcher — "
            "returning basic Fetcher; use Spider classes for crawls."
        )
        return Fetcher()

    raise ValueError(f"Unknown scraper profile: {profile}")