"""Schedule management endpoints — CRUD, URLs, configs, callback, trigger."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.schedule import (
    CallbackConfigCreate,
    CallbackConfigResponse,
    CallbackLogResponse,
    ScheduleCreate,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleUpdate,
    ScheduleUrlCreate,
    ScheduleUrlResponse,
    ScheduleConfigLinkResponse,
)
from app.services.callback_service import CallbackService
from app.services.schedule_service import ScheduleService

router = APIRouter()


# ── Schedule CRUD ────────────────────────────────────────────────


@router.post("/", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleResponse:
    """Create a new crawl schedule with optional configs, URLs, and callback."""
    service = ScheduleService(session)
    schedule = await service.create(body)
    return _to_response(schedule)


@router.get("/", response_model=ScheduleListResponse)
async def list_schedules(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    active_only: bool = Query(False),
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleListResponse:
    """List all schedules with pagination."""
    service = ScheduleService(session)
    items, total = await service.list_schedules(skip, limit, active_only)
    return ScheduleListResponse(
        items=[_to_response(s) for s in items],
        total=total,
    )


@router.get("/{schedule_id}", response_model=ScheduleResponse)
async def get_schedule(
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleResponse:
    """Get schedule details including configs, URLs, and callback."""
    service = ScheduleService(session)
    schedule = await service.get_by_id(schedule_id)
    return _to_response(schedule)


@router.patch("/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    body: ScheduleUpdate,
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleResponse:
    """Partially update a schedule."""
    service = ScheduleService(session)
    schedule = await service.update(schedule_id, body)
    return _to_response(schedule)


@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_schedule(
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Delete a schedule and all its related data."""
    service = ScheduleService(session)
    await service.delete(schedule_id)


# ── Manual trigger ───────────────────────────────────────────────


@router.post("/{schedule_id}/trigger", status_code=status.HTTP_202_ACCEPTED)
async def trigger_schedule(
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> dict:
    """Manually trigger a schedule — creates jobs for all config×url pairs."""
    from app.workers.tasks.scrape import run_crawl_job

    service = ScheduleService(session)
    jobs = await service.trigger(schedule_id)

    # Enqueue each job to Celery
    for job in jobs:
        run_crawl_job.apply_async(
            args=[str(job.id)],
            queue=job.queue,
        )

    return {
        "schedule_id": str(schedule_id),
        "jobs_created": len(jobs),
        "job_ids": [str(j.id) for j in jobs],
    }


# ── URL management ──────────────────────────────────────────────


@router.post(
    "/{schedule_id}/urls",
    response_model=ScheduleUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_url(
    body: ScheduleUrlCreate,
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleUrlResponse:
    """Add a target URL to a schedule."""
    service = ScheduleService(session)
    target = await service.add_url(schedule_id, body)
    return ScheduleUrlResponse.model_validate(target)


@router.delete(
    "/{schedule_id}/urls/{url_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_url(
    schedule_id: UUID = Path(...),
    url_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Remove a URL from a schedule."""
    service = ScheduleService(session)
    await service.remove_url(schedule_id, url_id)


# ── Callback management ─────────────────────────────────────────


@router.put(
    "/{schedule_id}/callback",
    response_model=CallbackConfigResponse,
)
async def set_callback(
    body: CallbackConfigCreate,
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> CallbackConfigResponse:
    """Create or replace the callback config for a schedule."""
    service = ScheduleService(session)
    cb = await service.set_callback(schedule_id, body)
    return CallbackConfigResponse.model_validate(cb)


@router.delete(
    "/{schedule_id}/callback",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_callback(
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Remove the callback config from a schedule."""
    service = ScheduleService(session)
    await service.remove_callback(schedule_id)


@router.get(
    "/{schedule_id}/callback/logs",
    response_model=list[CallbackLogResponse],
)
async def get_callback_logs(
    schedule_id: UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
) -> list[CallbackLogResponse]:
    """Get callback execution logs for a schedule."""
    service = CallbackService(session)
    logs = await service.get_logs(schedule_id, skip, limit)
    return [CallbackLogResponse.model_validate(log) for log in logs]


# ── Response builder ─────────────────────────────────────────────


def _to_response(schedule) -> ScheduleResponse:
    """Build ScheduleResponse with nested config names."""
    config_links = []
    for link in schedule.config_links:
        config_links.append(
            ScheduleConfigLinkResponse(
                id=link.id,
                config_id=link.config_id,
                config_name=link.config.name if link.config else None,
                priority=link.priority,
            )
        )

    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        description=schedule.description,
        is_active=schedule.is_active,
        timezone=schedule.timezone,
        cron_expression=schedule.cron_expression,
        interval_seconds=schedule.interval_seconds,
        default_queue=schedule.default_queue,
        next_run_at=schedule.next_run_at,
        last_run_at=schedule.last_run_at,
        run_count=schedule.run_count,
        created_at=schedule.created_at,
        updated_at=schedule.updated_at,
        config_links=config_links,
        url_targets=[
            ScheduleUrlResponse.model_validate(t)
            for t in schedule.url_targets
        ],
        callback=(
            CallbackConfigResponse.model_validate(schedule.callback)
            if schedule.callback
            else None
        ),
    )
