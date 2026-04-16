"""Email notification task — sends email after crawl completion.

Applies the field_mapping from EmailNotificationConfig to transform
extraction results, builds HTML body, and sends via SMTP.
"""

from __future__ import annotations

import asyncio
import logging

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="pilgrim.email_notification.send",
    queue="maintenance",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    max_retries=3,
)
def send_email_notification(
    crawl_job_id: str,
    email_notification_config_id: str,
    schedule_id: str,
    trigger_reason: str,
) -> dict[str, str]:
    """Send an email notification for a completed crawl job.

    Parameters
    ----------
    crawl_job_id : str
        UUID of the completed CrawlJob.
    email_notification_config_id : str
        UUID of the EmailNotificationConfig to use.
    schedule_id : str
        UUID of the owning schedule (for logging).
    trigger_reason : str
        "success" or "failure" — controls email content.
    """
    return asyncio.run(
        _send_email_notification(
            crawl_job_id, email_notification_config_id, schedule_id, trigger_reason
        )
    )


async def _send_email_notification(
    crawl_job_id: str,
    email_notification_config_id: str,
    schedule_id: str,
    trigger_reason: str,
) -> dict[str, str]:
    from uuid import UUID

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import selectinload

    from app.core.config import get_settings
    from app.models.crawl_job import CrawlJob
    from app.models.crawl_job_result import CrawlJobResult
    from app.models.email_notification_config import EmailNotificationConfig
    from app.services.email_notification_service import EmailNotificationService

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            # Load email notification config
            en_result = await session.execute(
                select(EmailNotificationConfig).where(
                    EmailNotificationConfig.id == UUID(email_notification_config_id)
                )
            )
            email_config = en_result.scalar_one_or_none()
            if not email_config:
                logger.error(
                    "EmailNotificationConfig %s not found",
                    email_notification_config_id,
                )
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

            # Build results list (same shape as callback task)
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

            # For failure, include error info
            if trigger_reason == "failure" and job.error_message:
                metadata["error_message"] = job.error_message

            # Execute email notification
            service = EmailNotificationService(session)
            log = await service.execute_notification(
                email_config, results, metadata, trigger_reason
            )

            status = "success" if log.success else "failed"
            logger.info(
                "Email notification for job %s: %s (attempt %d)",
                crawl_job_id, status, log.attempt_number,
            )
            return {
                "status": status,
                "email_notification_log_id": str(log.id),
            }

    finally:
        await engine.dispose()