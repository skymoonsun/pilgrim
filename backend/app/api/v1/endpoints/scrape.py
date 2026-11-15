"""Synchronous scrape endpoint — quick one-off test scrapes."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.crawl import ScrapeRequest, ScrapeResponse
from app.services.scrape_service import ScrapeService

router = APIRouter()


@router.post("/", response_model=ScrapeResponse)
async def scrape(
    body: ScrapeRequest,
    session: AsyncSession = Depends(get_async_session),
) -> ScrapeResponse:
    """Run a synchronous scrape using a stored configuration.

    Send ``config_id`` (UUID of a CrawlConfiguration) and ``url``
    (the target page).  The endpoint fetches the page, applies the
    extraction spec, and returns the result in the response body.

    Use this for quick tests.  For production workloads prefer the
    asynchronous ``POST /api/v1/crawl/jobs`` endpoint.

    When the config has ``use_proxy: true``, the fetch is routed
    through the healthy proxy pool (rotation to a different proxy on
    failure, direct fallback on an exhausted pool) and the
    credential-free proxy story is returned in the response's
    ``proxy`` field — the same behaviour as the async crawl jobs.
    """
    service = ScrapeService(session)
    return await service.execute(config_id=body.config_id, url=body.url)
