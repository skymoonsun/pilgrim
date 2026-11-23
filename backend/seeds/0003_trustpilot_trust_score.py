"""Seed 0003 — Trustpilot seller trust-score crawl config.

Recipe for ``https://www.trustpilot.com/review/<domain>`` (the domain is
the runtime URL, the config is URL-agnostic). Output feeds the domain →
score JSON documented in ``app/services/trust_scores.py`` and consumed by
c4game-core seller trust badges.

Uses the ``stealth`` profile: the review page is behind an AWS WAF bot
challenge that a plain HTTP fetcher cannot pass (403 interstitial).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl_config import CrawlConfiguration
from app.models.enums import ScraperProfile
from app.services.trust_scores import (
    TRUSTPILOT_EXTRACTION_SPEC,
    TRUSTPILOT_FETCH_OPTIONS,
)


async def run(session: AsyncSession) -> None:
    """Insert the Trustpilot trust-score crawl configuration."""
    session.add(
        CrawlConfiguration(
            name="trustpilot-trust-score",
            description=(
                "Trustpilot business rating for one seller domain "
                "(target URL: https://www.trustpilot.com/review/<domain>). "
                "Prefers the JSON-LD Product block (aggregateRating), "
                "falls back to the embedded __NEXT_DATA__ businessUnit "
                "(trustScore / numberOfReviews / stars), then to DOM "
                "data-attributes. Output feeds the domain → score "
                "document via the trust_scores callback transform."
            ),
            scraper_profile=ScraperProfile.STEALTH,
            is_active=True,
            extraction_spec=TRUSTPILOT_EXTRACTION_SPEC,
            fetch_options=dict(TRUSTPILOT_FETCH_OPTIONS),
            use_proxy=False,
            rotate_user_agent=False,
        )
    )
    await session.flush()
