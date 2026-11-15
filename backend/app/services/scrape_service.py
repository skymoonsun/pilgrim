"""Synchronous (request-scoped) scraping service.

Loads a CrawlConfiguration from the DB, fetches the target URL via
Scrapling, applies extraction rules, and returns the result in a single
request cycle.  Suitable for quick tests and one-off scrapes.

When the config has ``use_proxy = true`` the fetch is routed through
the healthy proxy pool with rotation and a direct-fetch fallback — the
behaviour the Celery path (``pilgrim.scrape.run_job``) already has;
see ``app.services.proxy_rotation`` (credential-free records included).
"""

import logging
import time
from collections.abc import Collection
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import CrawlingError
from app.crawlers.fetch_options import strip_app_owned_keys
from app.models.valid_proxy import ValidProxy
from app.schemas.crawl import ScrapeResponse
from app.services.crawl_config_service import CrawlConfigService
from app.services.proxy_rotation import (
    ProxyRotationReport,
    fetch_with_proxy_rotation,
    resolve_proxy_attempts,
)
from app.services.valid_proxy_service import ValidProxyService

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
        """Fetch *url* using the rules from *config_id* and return data.

        When the config has ``use_proxy = true``, the fetch runs through
        the healthy proxy pool: up to ``fetch_options.proxy_retries``
        distinct proxies are tried, each failure rotates to a different
        one, and an exhausted pool falls back to a direct request.  The
        credential-free story (which proxy was used, per-attempt
        outcomes, fallback) is attached to the response's ``proxy``
        field — there is no CrawlJob activity feed on this
        request-scoped path, so the response carries the record.
        """
        start = time.monotonic()

        # 1. Load config
        config_service = CrawlConfigService(self.session)
        config = await config_service.get_by_id(config_id)

        # 2. Fetch page (lazy imports to avoid crash on slim API image)
        proxy_report: ProxyRotationReport | None = None
        try:
            from app.crawlers.factory import create_fetcher
            from app.crawlers.extraction import extract_data

            fetcher = create_fetcher(
                profile=config.scraper_profile,
                # Strip app-owned keys (``proxy_retries``) so they never
                # reach the strict-kwargs Scrapling constructor; the raw
                # ``config.fetch_options`` stays untouched and still
                # drives the rotation budget below.
                fetch_options=strip_app_owned_keys(config.fetch_options or {}),
            )
            if config.use_proxy:
                proxy_report = ProxyRotationReport()
                proxy_service = ValidProxyService(self.session)

                async def _select_proxy(
                    exclude: Collection[UUID],
                ) -> ValidProxy | None:
                    return await proxy_service.get_random_healthy(
                        exclude_ids=exclude,
                    )

                # Sync parity with run_job: the fetch is delegated to
                # the existing rotation helper (credential-free logs).
                response = await fetch_with_proxy_rotation(
                    fetch=lambda kwargs: fetcher.get(url, **kwargs),
                    select_proxy=_select_proxy,
                    profile=config.scraper_profile,
                    max_attempts=resolve_proxy_attempts(config.fetch_options),
                    report=proxy_report,
                )
            else:
                response = fetcher.get(url)
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
                # Keep the proxy story visible on failed fetches too —
                # which proxies were tried and why we fell back.
                proxy=proxy_report.summary() if proxy_report else None,
                duration_ms=_elapsed_ms(start),
            )

        if proxy_report is not None:
            logger.info(
                "Sync scrape %s via proxy %s (fell_back_direct=%s, "
                "attempts=%d)",
                url,
                proxy_report.used_proxy or "none",
                proxy_report.fell_back_direct,
                len(proxy_report.attempts),
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
                proxy=proxy_report.summary() if proxy_report else None,
                duration_ms=_elapsed_ms(start),
            )

        return ScrapeResponse(
            config_id=config_id,
            url=url,
            http_status=http_status,
            data=data,
            proxy=proxy_report.summary() if proxy_report else None,
            duration_ms=_elapsed_ms(start),
        )


def _elapsed_ms(start: float) -> float:
    return round((time.monotonic() - start) * 1000, 2)
