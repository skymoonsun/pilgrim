"""Endpoints for listing, viewing, and deleting valid proxies."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.models.enums import ProxyHealthStatus, ProxyProtocol
from app.schemas.proxy import ValidProxyListResponse, ValidProxyResponse
from app.services.valid_proxy_service import ValidProxyService

router = APIRouter()


@router.get("/", response_model=ValidProxyListResponse)
async def list_valid_proxies(
    source_id: UUID | None = Query(
        None, description="Filter by proxy source config UUID"
    ),
    protocol: ProxyProtocol | None = Query(
        None, description="Filter by proxy protocol"
    ),
    health: ProxyHealthStatus | None = Query(
        None, description="Filter by health status"
    ),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    session: AsyncSession = Depends(get_async_session),
) -> ValidProxyListResponse:
    """List valid proxies with optional filtering."""
    service = ValidProxyService(session)
    proxies, total = await service.list_all(
        source_config_id=source_id,
        protocol=protocol,
        health=health,
        skip=skip,
        limit=limit,
    )
    return ValidProxyListResponse(
        items=[ValidProxyResponse.model_validate(p) for p in proxies],
        total=total,
    )


@router.get("/{proxy_id}", response_model=ValidProxyResponse)
async def get_valid_proxy(
    proxy_id: UUID = Path(..., description="Proxy UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> ValidProxyResponse:
    """Get a single valid proxy by ID."""
    service = ValidProxyService(session)
    proxy = await service.get_by_id(proxy_id)
    return ValidProxyResponse.model_validate(proxy)


@router.delete(
    "/{proxy_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def delete_valid_proxy(
    proxy_id: UUID = Path(..., description="Proxy UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Delete a valid proxy."""
    service = ValidProxyService(session)
    await service.delete_by_id(proxy_id)


@router.post(
    "/{source_id}/validate",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_validate(
    source_id: UUID = Path(..., description="Proxy source UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Trigger a validation task for all proxies from this source."""
    from app.workers.tasks.proxy import validate_proxies

    task = validate_proxies.delay(str(source_id))

    return {
        "source_id": str(source_id),
        "task_id": task.id,
        "message": "Validation task queued",
    }