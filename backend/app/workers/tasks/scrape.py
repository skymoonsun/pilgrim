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
                config = await session.run_sync(
                    lambda s: job.crawl_configuration
                )

                # 4. Fetch
                fetcher = create_fetcher(
                    config.scraper_profile,
                    config.fetch_options or {},
                )
                response = fetcher.get(job.target_url)
                http_status = getattr(response, "status", None)

                # 5. Extract
                data = extract_data(response, config.extraction_spec)

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

