"""Sanitizer config CRUD endpoints."""

from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.database import get_async_session
from app.schemas.sanitizer_config import (
    SanitizerConfigCreate,
    SanitizerConfigListResponse,
    SanitizerConfigResponse,
    SanitizerConfigUpdate,
)
from app.services.sanitizer_config_service import SanitizerConfigService

router = APIRouter()


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    response_model=SanitizerConfigResponse,
)
async def create_sanitizer_config(
    body: SanitizerConfigCreate,
    session: AsyncSession = Depends(get_async_session),
) -> SanitizerConfigResponse:
    """Create a new sanitizer configuration."""
    service = SanitizerConfigService(session)
    config = await service.create(body)
    return SanitizerConfigResponse.model_validate(config)


@router.get("/", response_model=SanitizerConfigListResponse)
async def list_sanitizer_configs(
    active_only: bool = Query(False),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
) -> SanitizerConfigListResponse:
    """List sanitizer configurations with optional active filter."""
    service = SanitizerConfigService(session)
    configs, total = await service.list_all(
        active_only=active_only, skip=skip, limit=limit
    )
    return SanitizerConfigListResponse(
        items=[SanitizerConfigResponse.model_validate(c) for c in configs],
        total=total,
    )


@router.get("/{config_id}", response_model=SanitizerConfigResponse)
async def get_sanitizer_config(
    config_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> SanitizerConfigResponse:
    """Get a sanitizer configuration by ID."""
    service = SanitizerConfigService(session)
    config = await service.get_by_id(config_id)
    return SanitizerConfigResponse.model_validate(config)


@router.patch("/{config_id}", response_model=SanitizerConfigResponse)
async def update_sanitizer_config(
    config_id: UUID,
    body: SanitizerConfigUpdate,
    session: AsyncSession = Depends(get_async_session),
) -> SanitizerConfigResponse:
    """Partially update a sanitizer configuration."""
    service = SanitizerConfigService(session)
    config = await service.update(config_id, body)
    return SanitizerConfigResponse.model_validate(config)


@router.delete(
    "/{config_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_sanitizer_config(
    config_id: UUID,
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Delete a sanitizer configuration."""
    service = SanitizerConfigService(session)
    await service.delete(config_id)