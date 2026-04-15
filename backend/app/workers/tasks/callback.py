"""Callback task — sends webhook notifications after crawl completion.

Applies the field_mapping from CallbackConfig to transform extraction
results, then dispatches an HTTP request to the configured endpoint.
"""

from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="pilgrim.callback.send",
    queue="maintenance",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=3,
)
def send_callback(
    crawl_job_id: str,
    callback_config_id: str,
    schedule_id: str,
) -> dict[str, str]:
    """Send a callback for a completed crawl job.

    Parameters
    ----------
    crawl_job_id : str
        UUID of the completed CrawlJob.
    callback_config_id : str
        UUID of the CallbackConfig to use.
    schedule_id : str
        UUID of the owning schedule (for logging).
    """
    return asyncio.run(
        _send_callback(crawl_job_id, callback_config_id, schedule_id)
    )


async def _send_callback(
    crawl_job_id: str,
    callback_config_id: str,
    schedule_id: str,
) -> dict[str, str]:
    from uuid import UUID

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import selectinload

    from app.core.config import get_settings
    from app.models.callback_config import CallbackConfig
    from app.models.crawl_job import CrawlJob
    from app.models.crawl_job_result import CrawlJobResult
    from app.services.callback_service import CallbackService

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            # Load callback config
            cb_result = await session.execute(
                select(CallbackConfig).where(
                    CallbackConfig.id == UUID(callback_config_id)
                )
            )
            callback_config = cb_result.scalar_one_or_none()
            if not callback_config:
                logger.error("CallbackConfig %s not found", callback_config_id)
                return {"status": "error", "reason": "config_not_found"}

            # Load job results
            job_result = await session.execute(
                select(CrawlJob)
                .options(selectinload(CrawlJob.results))
                .where(CrawlJob.id == UUID(crawl_job_id))
            )
            job = job_result.scalar_one_or_none()
            if not job:
                logger.error("CrawlJob %s not found", crawl_job_id)
                return {"status": "error", "reason": "job_not_found"}

            # Build results list
            results = []
            for r in job.results:
                results.append({
                    "data": r.payload or {},
                    "url": r.source_url,
                    "http_status": r.http_status,
                })

            metadata = {
                "schedule_id": schedule_id,
                "job_id": crawl_job_id,
                "target_url": job.target_url,
                "job_status": job.status.value,
            }

            # Execute callback
            service = CallbackService(session)
            log = await service.execute_callback(
                callback_config, results, metadata
            )

            status = "success" if log.success else "failed"
            logger.info(
                "Callback for job %s: %s (attempt %d)",
                crawl_job_id, status, log.attempt_number,
            )
            return {
                "status": status,
                "callback_log_id": str(log.id),
            }

    finally:
        await engine.dispose()
