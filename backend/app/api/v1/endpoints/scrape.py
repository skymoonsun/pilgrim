"""Synchronous scrape endpoint — quick one-off test scrapes.

Adds an optional TTL response cache (``(config_id, url)`` → response) and
an IP-based rate limit.  Both are configured via ``PILGRIM_SCRAPE_CACHE_*``
and ``PILGRIM_RATE_LIMIT_*`` (see .env.example / README) and are read at
request time, so a settings change requires no code change.
"""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.core.config import get_settings
from app.core.rate_limit import rate_limit_scope
from app.integrations.cache import get_scrape_cache, scrape_cache_key
from app.schemas.crawl import ScrapeRequest, ScrapeResponse
from app.services.scrape_service import ScrapeService

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "/",
    response_model=ScrapeResponse,
    dependencies=[Depends(rate_limit_scope("scrape"))],
)
async def scrape(
    body: ScrapeRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ScrapeResponse:
    """Run a synchronous scrape using a stored configuration.

    Send ``config_id`` (UUID of a CrawlConfiguration) and ``url``
    (the target page).  The endpoint fetches the page, applies the
    extraction spec, and returns the result in the response body.

    Repeated calls with the same ``config_id``+``url`` inside the cache TTL
    return the stored response with ``"cached": true`` without refetching.
    Use this for quick tests.  For production workloads prefer the
    asynchronous ``POST /api/v1/crawl/jobs`` endpoint.
    """
    cache = get_scrape_cache()
    key = scrape_cache_key(str(body.config_id), body.url)

    if cache is not None:
        cached_payload = await cache.get(key)
        if cached_payload is not None:
            response = ScrapeResponse.model_validate(cached_payload)
            response.cached = True
            return response

    service = ScrapeService(session)
    result = await service.execute(config_id=body.config_id, url=body.url)

    # Only successful scrapes are worth caching; error responses (site
    # down, scrapling missing) must not pin failures into the cache.
    if cache is not None and result.error is None and result.data is not None:
        await cache.set(
            key,
            result.model_dump(mode="json"),
            get_settings().scrape_cache_ttl_seconds,
        )
    return result
