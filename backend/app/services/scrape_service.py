"""Synchronous (request-scoped) scraping service.

Loads a CrawlConfiguration from the DB, fetches the target URL via
Scrapling, applies extraction rules, and returns the result in a single
request cycle.  Suitable for quick tests and one-off scrapes.
"""

import logging
import time
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CrawlingError
from app.schemas.crawl import ScrapeResponse
from app.services.crawl_config_service import CrawlConfigService

logger = logging.getLogger(__name__)


class ScrapeService:
    """Execute a scrape using a stored configuration."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def execute(
        self,
        config_id: UUID,
        url: str,
    ) -> ScrapeResponse:
        """Fetch *url* using the rules from *config_id* and return data."""
        start = time.monotonic()

        # 1. Load config
        config_service = CrawlConfigService(self.session)
        config = await config_service.get_by_id(config_id)

        # 2. Fetch page (lazy imports to avoid crash on slim API image)
        try:
            from app.crawlers.factory import create_fetcher
            from app.crawlers.extraction import extract_data

            response = create_fetcher(
                profile=config.scraper_profile,
                fetch_options=config.fetch_options or {},
            ).get(url)
        except ImportError as exc:
            logger.error(
                "Scrapling dependencies not available: %s. "
                "Use the async crawl endpoint or run on the worker image.",
                exc,
            )
            return ScrapeResponse(
                config_id=config_id,
                url=url,
                error=(
                    "Scrapling dependencies not installed in this container. "
                    "Use POST /api/v1/crawl/jobs for async scraping."
                ),
                duration_ms=_elapsed_ms(start),
            )
        except Exception as exc:
            logger.error("Fetch failed for %s: %s", url, exc)
            return ScrapeResponse(
                config_id=config_id,
                url=url,
                error=f"Fetch error: {exc}",
                duration_ms=_elapsed_ms(start),
            )

        # 3. Extract data
        try:
            from app.crawlers.extraction import extract_data
            from app.crawlers.html_sanitizer import sanitize_html

            http_status = getattr(response, "status", None)

            # If extraction spec uses json_path, we need structured data
            next_data = None
            json_ld = None
            fields = config.extraction_spec.get("fields", {}) if config.extraction_spec else {}
            if any(
                f.get("type") == "json_path" for f in fields.values() if isinstance(f, dict)
            ):
                html_raw = (
                    getattr(response, "html", "")
                    or getattr(response, "html_content", "")
                    or getattr(response, "body", "")
                    or str(response)
                )
                if html_raw.strip():
                    sanitize_result = sanitize_html(html_raw)
                    next_data = sanitize_result.next_data
                    json_ld = sanitize_result.json_ld

            data = extract_data(
                response, config.extraction_spec,
                next_data=next_data, json_ld=json_ld,
            )
        except Exception as exc:
            logger.error("Extraction failed for %s: %s", url, exc)
            return ScrapeResponse(
                config_id=config_id,
                url=url,
                http_status=getattr(response, "status", None),
                error=f"Extraction error: {exc}",
                duration_ms=_elapsed_ms(start),
            )

        return ScrapeResponse(
            config_id=config_id,
            url=url,
            http_status=http_status,
            data=data,
            duration_ms=_elapsed_ms(start),
        )


def _elapsed_ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)
