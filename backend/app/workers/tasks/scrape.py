"""Scrape tasks executed by Celery workers.

Each task receives a ``crawl_job_id`` (UUID string), loads the job and
its configuration from PostgreSQL, runs the Scrapling pipeline, and
persists results back to the database.
"""

from __future__ import annotations

import logging
import time

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="pilgrim.scrape.run_job",
    bind=True,
    queue="crawl_default",
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def run_crawl_job(self, crawl_job_id: str) -> dict[str, str]:
    """Execute a single crawl job identified by *crawl_job_id*.

    Steps
    -----
    1. Load ``CrawlJob`` and its ``CrawlConfiguration`` from the DB.
    2. Update status → RUNNING.
    3. Fetch the target URL via Scrapling (using the config profile).
    4. Apply extraction rules.
    5. Persist ``CrawlJobResult`` rows.
    6. Update status → SUCCEEDED (or FAILED on error).
    """
    import asyncio

    async def _run() -> dict[str, str]:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker as async_sessionmaker_compat
        from sqlalchemy.ext.asyncio import async_sessionmaker

        from app.core.config import get_settings
        from app.crawlers.factory import create_fetcher
        from app.crawlers.extraction import extract_data
        from app.models.crawl_job import CrawlJob
        from app.models.crawl_job_result import CrawlJobResult
        from app.models.enums import CrawlJobStatus
        from app.services.crawl_job_service import CrawlJobService

        settings = get_settings()
        engine = create_async_engine(str(settings.database_url))
        session_factory = async_sessionmaker(engine, class_=AsyncSession)

        async with session_factory() as session:
            service = CrawlJobService(session)

            # 1. Load job
            job = await service.get_by_id(crawl_job_id)

            # 2. Mark running
            await service.update_status(
                job.id,
                CrawlJobStatus.RUNNING,
                celery_task_id=self.request.id,
            )

            start = time.monotonic()
            try:
                # 3. Load config (eagerly loaded via relationship)
                from sqlalchemy import select as sa_select
                from sqlalchemy.orm import selectinload as so
                from app.models.crawl_config import CrawlConfiguration

                result = await session.execute(
                    sa_select(CrawlConfiguration)
                    .options(so(CrawlConfiguration.sanitizer_config))
                    .where(CrawlConfiguration.id == job.crawl_configuration_id)
                )
                config = result.scalar_one()

                # 4. Fetch
                fetcher = create_fetcher(
                    config.scraper_profile,
                    config.fetch_options or {},
                )
                fetch_kwargs: dict = {}
                if config.custom_headers:
                    fetch_kwargs["headers"] = config.custom_headers
                if config.cookies:
                    fetch_kwargs["cookies"] = config.cookies
                response = fetcher.get(job.target_url, **fetch_kwargs)
                http_status = getattr(response, "status", None)

                # 5. Extract
                # If extraction spec uses json_path, provide structured data
                next_data = None
                json_ld = None
                fields = config.extraction_spec.get("fields", {}) if config.extraction_spec else {}
                if any(
                    f.get("type") == "json_path" for f in fields.values() if isinstance(f, dict)
                ):
                    from app.crawlers.html_sanitizer import sanitize_html

                    html_raw = (
                        getattr(response, "html", "")
                        or getattr(response, "html_content", "")
                        or getattr(response, "body", "")
                        or str(response)
                    )
                    if html_raw.strip():
                        sanitize_result = sanitize_html(html_raw)
                        next_data = sanitize_result.next_data
                        json_ld = sanitize_result.json_ld

                data = extract_data(
                    response, config.extraction_spec,
                    next_data=next_data, json_ld=json_ld,
                )

                # Apply sanitizer if linked
                if config.sanitizer_config and config.sanitizer_config.rules:
                    from app.schemas.sanitizer_config import FieldSanitizer
                    from app.services.sanitizer import apply_sanitizer
                    rules = [FieldSanitizer(**r) for r in config.sanitizer_config.rules]
                    data = apply_sanitizer(data, rules)

                # 6. Persist result
                result = CrawlJobResult(
                    crawl_job_id=job.id,
                    source_url=job.target_url,
                    http_status=http_status,
                    payload=data,
                )
                session.add(result)

                duration_ms = round((time.monotonic() - start) * 1000, 2)
                await service.update_status(
                    job.id,
                    CrawlJobStatus.SUCCEEDED,
                    result_summary={
                        "fields_extracted": len(data),
                        "duration_ms": duration_ms,
                    },
                )
                logger.info(
                    "Job %s succeeded in %.1fms", crawl_job_id, duration_ms
                )

                # ── Callback chain ───────────────────────────────
                await _maybe_enqueue_callback(session, job)

                # ── Email notification chain ────────────────────
                await _maybe_enqueue_email_notification(session, job, True)

                return {
                    "crawl_job_id": crawl_job_id,
                    "status": "succeeded",
                }

            except Exception as exc:
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                await service.update_status(
                    job.id,
                    CrawlJobStatus.FAILED,
                    error_message=str(exc),
                    result_summary={"duration_ms": duration_ms},
                )
                logger.error("Job %s failed: %s", crawl_job_id, exc)

                # ── Email notification on failure ──────────────
                try:
                    await _maybe_enqueue_email_notification(session, job, False)
                except Exception:
                    logger.warning(
                        "Failed to enqueue email notification for job %s",
                        crawl_job_id, exc_info=True,
                    )

                raise

        await engine.dispose()

    return asyncio.run(_run())


async def _maybe_enqueue_callback(session, job) -> None:
    """Check if this job's config is linked to a schedule with a callback."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.callback_config import CallbackConfig
    from app.models.schedule_config_link import ScheduleConfigLink

    # Find schedules linked to this config
    result = await session.execute(
        select(ScheduleConfigLink)
        .options(selectinload(ScheduleConfigLink.schedule))
        .where(ScheduleConfigLink.config_id == job.crawl_configuration_id)
    )
    links = list(result.scalars())

    for link in links:
        # Check if schedule has an active callback
        cb_result = await session.execute(
            select(CallbackConfig).where(
                CallbackConfig.schedule_id == link.schedule_id,
                CallbackConfig.is_active.is_(True),
            )
        )
        callback_config = cb_result.scalar_one_or_none()
        if callback_config and not callback_config.batch_results:
            # Individual mode: fire immediately per job
            from app.workers.tasks.callback import send_callback

            send_callback.apply_async(
                args=[
                    str(job.id),
                    str(callback_config.id),
                    str(link.schedule_id),
                ],
                queue="maintenance",
            )
            logger.info(
                "Enqueued callback for job %s → %s",
                job.id, callback_config.url,
            )


async def _maybe_enqueue_email_notification(session, job, job_succeeded: bool) -> None:
    """Check if this job's config is linked to a schedule with email notification."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.email_notification_config import EmailNotificationConfig
    from app.models.schedule_config_link import ScheduleConfigLink

    trigger_reason = "success" if job_succeeded else "failure"

    result = await session.execute(
        select(ScheduleConfigLink)
        .options(selectinload(ScheduleConfigLink.schedule))
        .where(ScheduleConfigLink.config_id == job.crawl_configuration_id)
    )
    links = list(result.scalars())

    for link in links:
        en_result = await session.execute(
            select(EmailNotificationConfig).where(
                EmailNotificationConfig.schedule_id == link.schedule_id,
                EmailNotificationConfig.is_active.is_(True),
            )
        )
        email_config = en_result.scalar_one_or_none()
        if not email_config:
            continue

        # Check trigger conditions
        if job_succeeded and not email_config.on_success:
            continue
        if not job_succeeded and not email_config.on_failure:
            continue

        if not email_config.batch_results:
            # Individual mode: fire immediately per job
            from app.workers.tasks.email_notification import send_email_notification

            send_email_notification.apply_async(
                args=[
                    str(job.id),
                    str(email_config.id),
                    str(link.schedule_id),
                    trigger_reason,
                ],
                queue="maintenance",
            )
            logger.info(
                "Enqueued email notification for job %s → %s (reason: %s)",
                job.id, email_config.recipient_emails, trigger_reason,
            )

