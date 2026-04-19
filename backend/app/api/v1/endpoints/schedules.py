"""Schedule management endpoints — CRUD, URLs per config, callback, trigger."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.models.enums import ScheduleType
from app.schemas.schedule import (
    CallbackConfigCreate,
    CallbackConfigResponse,
    CallbackLogResponse,
    EmailNotificationConfigCreate,
    EmailNotificationConfigResponse,
    EmailNotificationLogResponse,
    ScheduleConfigLinkResponse,
    ScheduleCreate,
    ScheduleListResponse,
    ScheduleProxySourceLinkResponse,
    ScheduleResponse,
    ScheduleUpdate,
    ScheduleUrlCreate,
    ScheduleUrlResponse,
)
from app.services.callback_service import CallbackService
from app.services.email_notification_service import EmailNotificationService
from app.services.schedule_service import ScheduleService

router = APIRouter()


# ── Schedule CRUD ────────────────────────────────────────────────


@router.post("/", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    body: ScheduleCreate,
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleResponse:
    """Create a new crawl schedule with config links (each with URLs) and optional callback."""
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
    """Get schedule details including config links with URLs and callback."""
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
    """Manually trigger — creates jobs for crawl schedules or enqueues
    fetch+validate tasks for proxy_source schedules."""
    from app.workers.tasks.scrape import run_crawl_job
    from app.workers.tasks.proxy import fetch_proxy_source, validate_proxies

    service = ScheduleService(session)
    schedule = await service.get_by_id(schedule_id)

    if schedule.schedule_type == ScheduleType.PROXY_SOURCE:
        # Enqueue fetch + validate for each linked proxy source
        fetches_triggered = 0
        for link in schedule.proxy_source_links:
            fetch_proxy_source.apply_async(
                args=[str(link.proxy_source_id)],
                queue="maintenance",
            )
            validate_proxies.apply_async(
                args=[str(link.proxy_source_id)],
                queue="maintenance",
            )
            fetches_triggered += 1

        # Update tracking
        jobs = await service.trigger(schedule_id)

        return {
            "schedule_id": str(schedule_id),
            "fetches_triggered": fetches_triggered,
            "schedule_type": "proxy_source",
        }

    # Crawl schedule
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
        "schedule_type": "crawl",
    }


# ── URL management (per config link) ────────────────────────────


@router.post(
    "/{schedule_id}/config-links/{config_link_id}/urls",
    response_model=ScheduleUrlResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_url(
    body: ScheduleUrlCreate,
    schedule_id: UUID = Path(...),
    config_link_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> ScheduleUrlResponse:
    """Add a target URL to a specific config link."""
    service = ScheduleService(session)
    await service.get_by_id(schedule_id)  # validate schedule exists
    target = await service.add_url(config_link_id, body)
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
    """Remove a URL from a config link."""
    service = ScheduleService(session)
    await service.remove_url(url_id)


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


# ── Email notification management ─────────────────────────────────


@router.put(
    "/{schedule_id}/email-notification",
    response_model=EmailNotificationConfigResponse,
)
async def set_email_notification(
    body: EmailNotificationConfigCreate,
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> EmailNotificationConfigResponse:
    """Create or replace the email notification config for a schedule."""
    service = ScheduleService(session)
    en = await service.set_email_notification(schedule_id, body)
    return EmailNotificationConfigResponse.model_validate(en)


@router.delete(
    "/{schedule_id}/email-notification",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_email_notification(
    schedule_id: UUID = Path(...),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Remove the email notification config from a schedule."""
    service = ScheduleService(session)
    await service.remove_email_notification(schedule_id)


@router.get(
    "/{schedule_id}/email-notification/logs",
    response_model=list[EmailNotificationLogResponse],
)
async def get_email_notification_logs(
    schedule_id: UUID = Path(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_async_session),
) -> list[EmailNotificationLogResponse]:
    """Get email notification logs for a schedule."""
    service = EmailNotificationService(session)
    logs = await service.get_logs(schedule_id, skip, limit)
    return [EmailNotificationLogResponse.model_validate(log) for log in logs]


# ── Response builder ─────────────────────────────────────────────


def _to_response(schedule) -> ScheduleResponse:
    """Build ScheduleResponse with nested config links, proxy source links, and URLs."""
    config_links = []
    for link in schedule.config_links:
        config_links.append(
            ScheduleConfigLinkResponse(
                id=link.id,
                config_id=link.config_id,
                config_name=link.config.name if link.config else None,
                priority=link.priority,
                url_targets=[
                    ScheduleUrlResponse.model_validate(t)
                    for t in link.url_targets
                ],
            )
        )

    proxy_source_links = []
    for link in schedule.proxy_source_links:
        proxy_source_links.append(
            ScheduleProxySourceLinkResponse(
                id=link.id,
                proxy_source_id=link.proxy_source_id,
                proxy_source_name=link.proxy_source.name if link.proxy_source else None,
                priority=link.priority,
            )
        )

    return ScheduleResponse(
        id=schedule.id,
        name=schedule.name,
        description=schedule.description,
        is_active=schedule.is_active,
        schedule_type=schedule.schedule_type.value,
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
        proxy_source_links=proxy_source_links,
        callback=(
            CallbackConfigResponse.model_validate(schedule.callback)
            if schedule.callback
            else None
        ),
        email_notification=(
            EmailNotificationConfigResponse.model_validate(schedule.email_notification)
            if schedule.email_notification
            else None
        ),
    )
