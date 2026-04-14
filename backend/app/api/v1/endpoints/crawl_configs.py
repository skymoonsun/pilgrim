"""CRUD endpoints for crawl configurations."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.crawl_config import (
    CrawlConfigCreate,
    CrawlConfigListResponse,
    CrawlConfigResponse,
    CrawlConfigUpdate,
)
from app.services.crawl_config_service import CrawlConfigService

router = APIRouter()


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=CrawlConfigResponse,
)
async def create_crawl_config(
    body: CrawlConfigCreate,
    session: AsyncSession = Depends(get_async_session),
) -> CrawlConfigResponse:
    """Create a new crawl configuration.

    The configuration defines *how* to scrape (profile, selectors,
    headers, rate limits) but **not** *what URL* to scrape — the URL is
    supplied at runtime.
    """
    service = CrawlConfigService(session)
    config = await service.create(body)
    return CrawlConfigResponse.model_validate(config)


@router.get("/", response_model=CrawlConfigListResponse)
async def list_crawl_configs(
    active_only: bool = Query(
        False, description="Return only active configurations"
    ),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    session: AsyncSession = Depends(get_async_session),
) -> CrawlConfigListResponse:
    """List crawl configurations with optional filtering."""
    service = CrawlConfigService(session)
    configs, total = await service.list_all(
        active_only=active_only, skip=skip, limit=limit
    )
    return CrawlConfigListResponse(
        items=[CrawlConfigResponse.model_validate(c) for c in configs],
        total=total,
    )


@router.get("/{config_id}", response_model=CrawlConfigResponse)
async def get_crawl_config(
    config_id: UUID = Path(..., description="Configuration UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> CrawlConfigResponse:
    """Get a single crawl configuration by ID."""
    service = CrawlConfigService(session)
    config = await service.get_by_id(config_id)
    return CrawlConfigResponse.model_validate(config)


@router.patch("/{config_id}", response_model=CrawlConfigResponse)
async def update_crawl_config(
    body: CrawlConfigUpdate,
    config_id: UUID = Path(..., description="Configuration UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> CrawlConfigResponse:
    """Partially update a crawl configuration."""
    service = CrawlConfigService(session)
    config = await service.update(config_id, body)
    return CrawlConfigResponse.model_validate(config)


@router.delete(
    "/{config_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_crawl_config(
    config_id: UUID = Path(..., description="Configuration UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Delete a crawl configuration and its associated jobs."""
    service = CrawlConfigService(session)
    await service.delete(config_id)
