"""Endpoints for listing, viewing, and deleting valid proxies."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.models.enums import ProxyHealthStatus, ProxyProtocol
from app.schemas.proxy import (
    BulkDeleteRequest,
    BulkDeleteResponse,
    ManualProxyBulkCreate,
    ManualProxyCreate,
    ManualProxyCreateResult,
    ValidProxyListResponse,
    ValidProxyResponse,
)
from app.services.valid_proxy_service import ValidProxyService

router = APIRouter()


@router.post("/", status_code=status.HTTP_201_CREATED, response_model=ManualProxyCreateResult)
async def create_manual_proxy(
    body: ManualProxyCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ManualProxyCreateResult:
    """Add a single manual proxy."""
    service = ValidProxyService(session)
    proxy = await service.create_manual_proxy(
        ip=body.ip,
        port=body.port,
        protocol=body.protocol,
        username=body.username,
        password=body.password,
    )
    resp = ValidProxyResponse.model_validate(proxy)
    resp.source_name = None
    return ManualProxyCreateResult(created=1, skipped=0, items=[resp])


@router.post("/bulk", status_code=status.HTTP_201_CREATED, response_model=ManualProxyCreateResult)
async def create_manual_proxies_bulk(
    body: ManualProxyBulkCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ManualProxyCreateResult:
    """Bulk-add manual proxies from raw text lines."""
    service = ValidProxyService(session)
    proxies, created, skipped = await service.create_manual_proxies_bulk(
        raw_text=body.raw_text,
        default_protocol=body.default_protocol,
    )
    items = [ValidProxyResponse.model_validate(p) for p in proxies]
    for item in items:
        item.source_name = None
    return ManualProxyCreateResult(created=created, skipped=skipped, items=items)


@router.get("/", response_model=ValidProxyListResponse)
async def list_valid_proxies(
    source_id: UUID | None = Query(
        None, description="Filter by proxy source config UUID"
    ),
    manual_only: bool = Query(
        False, description="Show only manual (source-less) proxies"
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
        manual_only=manual_only,
        protocol=protocol,
        health=health,
        skip=skip,
        limit=limit,
    )
    items = []
    for p in proxies:
        resp = ValidProxyResponse.model_validate(p)
        resp.source_name = p.source_config.name if p.source_config else None
        items.append(resp)
    return ValidProxyListResponse(items=items, total=total)


@router.get("/{proxy_id}", response_model=ValidProxyResponse)
async def get_valid_proxy(
    proxy_id: UUID = Path(..., description="Proxy UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> ValidProxyResponse:
    """Get a single valid proxy by ID."""
    service = ValidProxyService(session)
    proxy = await service.get_by_id(proxy_id)
    return ValidProxyResponse.model_validate(proxy)


@router.post("/bulk-delete", response_model=BulkDeleteResponse)
async def bulk_delete_proxies(
    body: BulkDeleteRequest,
    session: AsyncSession = Depends(get_async_session),
) -> BulkDeleteResponse:
    """Delete multiple proxies by their IDs."""
    service = ValidProxyService(session)
    count = await service.delete_by_ids(body.proxy_ids)
    return BulkDeleteResponse(deleted=count)


@router.delete("/", response_model=BulkDeleteResponse)
async def delete_all_proxies(
    source_id: UUID | None = Query(
        None, description="Only delete proxies from this source"
    ),
    manual_only: bool = Query(
        False, description="Only delete manual (source-less) proxies"
    ),
    protocol: ProxyProtocol | None = Query(
        None, description="Only delete proxies with this protocol"
    ),
    health: ProxyHealthStatus | None = Query(
        None, description="Only delete proxies with this health status"
    ),
    session: AsyncSession = Depends(get_async_session),
) -> BulkDeleteResponse:
    """Delete all proxies, optionally filtered. Use with caution."""
    service = ValidProxyService(session)
    count = await service.delete_all(
        source_config_id=source_id,
        manual_only=manual_only,
        protocol=protocol,
        health=health,
    )
    return BulkDeleteResponse(deleted=count)


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