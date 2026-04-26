"""Unified activity feed endpoint — crawl jobs + proxy fetch/validation logs."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.activity import ActivityListResponse, ActivityType
from app.services.activity_service import ActivityService

router = APIRouter()


@router.get("/", response_model=ActivityListResponse)
async def list_activities(
    type: list[ActivityType] | None = Query(
        None, description="Filter by activity type(s)"
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
) -> ActivityListResponse:
    """Unified activity feed across crawl jobs, proxy fetches, and validations."""
    service = ActivityService(session)
    items, total = await service.list_activities(
        type_filter=type, skip=skip, limit=limit,
    )
    return ActivityListResponse(items=items, total=total)