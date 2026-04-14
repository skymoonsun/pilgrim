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
    """
    service = ScrapeService(session)
    return await service.execute(config_id=body.config_id, url=body.url)
