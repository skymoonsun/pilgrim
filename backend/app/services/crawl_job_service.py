"""Service for creating and managing crawl jobs."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConfigNotFoundError, JobNotFoundError
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_job import CrawlJob
from app.models.enums import CrawlJobStatus
from app.schemas.crawl import CrawlJobCreate

logger = logging.getLogger(__name__)


class CrawlJobService:
    """Service layer for crawl job lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_jobs(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[list[CrawlJob], int]:
        """List jobs with pagination, newest first."""
        count_query = select(func.count()).select_from(CrawlJob)
        total = (await self.session.execute(count_query)).scalar() or 0

        result = await self.session.execute(
            select(CrawlJob)
            .order_by(CrawlJob.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def create_and_enqueue(self, data: CrawlJobCreate) -> CrawlJob:
        """Create a job row ready for Celery enqueueing.

        Validates that the referenced config exists before persisting.
        """
        # Verify config exists
        result = await self.session.execute(
            select(CrawlConfiguration).where(
                CrawlConfiguration.id == data.config_id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise ConfigNotFoundError(str(data.config_id))

        job = CrawlJob(
            crawl_configuration_id=data.config_id,
            target_url=data.url,
            queue=data.queue or "crawl_default",
            priority=data.priority,
            idempotency_key=data.idempotency_key,
            status=CrawlJobStatus.QUEUED,
        )
        self.session.add(job)
        await self.session.commit()
        await self.session.refresh(job)
        logger.info("Created crawl job: %s for url %s", job.id, job.target_url)
        return job

    async def get_by_id(self, job_id: UUID) -> CrawlJob:
        """Get job by ID or raise ``JobNotFoundError``."""
        result = await self.session.execute(
            select(CrawlJob).where(CrawlJob.id == job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise JobNotFoundError(str(job_id))
        return job

    async def update_status(
        self,
        job_id: UUID,
        status: CrawlJobStatus,
        *,
        error_message: str | None = None,
        result_summary: dict | None = None,
        celery_task_id: str | None = None,
    ) -> CrawlJob:
        """Update the authoritative status of a crawl job."""
        job = await self.get_by_id(job_id)
        job.status = status
        if error_message is not None:
            job.error_message = error_message
        if result_summary is not None:
            job.result_summary = result_summary
        if celery_task_id is not None:
            job.celery_task_id = celery_task_id
        await self.session.commit()
        await self.session.refresh(job)
        logger.info("Job %s status → %s", job_id, status.value)
        return job
