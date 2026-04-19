"""CRUD + trigger endpoints for proxy source configs."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.proxy import (
    ProxySourceCreate,
    ProxySourceListResponse,
    ProxySourceResponse,
    ProxySourceUpdate,
    FetchTriggerResponse,
)
from app.services.proxy_source_service import ProxySourceService

router = APIRouter()


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=ProxySourceResponse,
)
async def create_proxy_source(
    body: ProxySourceCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ProxySourceResponse:
    """Create a new proxy source config."""
    service = ProxySourceService(session)
    config = await service.create(body)
    return ProxySourceResponse.model_validate(config)


@router.get("/", response_model=ProxySourceListResponse)
async def list_proxy_sources(
    active_only: bool = Query(
        False, description="Return only active sources"
    ),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    session: AsyncSession = Depends(get_async_session),
) -> ProxySourceListResponse:
    """List proxy source configs with optional filtering."""
    service = ProxySourceService(session)
    configs, total = await service.list_all(
        active_only=active_only, skip=skip, limit=limit
    )
    return ProxySourceListResponse(
        items=[ProxySourceResponse.model_validate(c) for c in configs],
        total=total,
    )


@router.get("/{source_id}", response_model=ProxySourceResponse)
async def get_proxy_source(
    source_id: UUID = Path(..., description="Proxy source UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> ProxySourceResponse:
    """Get a single proxy source config by ID."""
    service = ProxySourceService(session)
    config = await service.get_by_id(source_id)
    return ProxySourceResponse.model_validate(config)


@router.patch("/{source_id}", response_model=ProxySourceResponse)
async def update_proxy_source(
    body: ProxySourceUpdate,
    source_id: UUID = Path(..., description="Proxy source UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> ProxySourceResponse:
    """Partially update a proxy source config."""
    service = ProxySourceService(session)
    config = await service.update(source_id, body)
    return ProxySourceResponse.model_validate(config)


@router.delete(
    "/{source_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_proxy_source(
    source_id: UUID = Path(..., description="Proxy source UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Delete a proxy source config and its proxies."""
    service = ProxySourceService(session)
    await service.delete(source_id)


@router.post(
    "/{source_id}/fetch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=FetchTriggerResponse,
)
async def trigger_fetch(
    source_id: UUID = Path(..., description="Proxy source UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> FetchTriggerResponse:
    """Trigger a fetch task for this proxy source."""
    service = ProxySourceService(session)
    config = await service.get_by_id(source_id)

    from app.workers.tasks.proxy import fetch_proxy_source
    task = fetch_proxy_source.delay(str(config.id))

    return FetchTriggerResponse(
        source_id=config.id,
        task_id=task.id,
        message=f"Fetch task queued for source '{config.name}'",
    )