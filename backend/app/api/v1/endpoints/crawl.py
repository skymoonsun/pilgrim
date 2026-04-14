"""Asynchronous crawl job endpoints (Celery-backed)."""

from uuid import UUID

from fastapi import APIRouter, Depends, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.crawl import CrawlJobCreate, CrawlJobResponse
from app.services.crawl_job_service import CrawlJobService
from app.workers.tasks.scrape import run_crawl_job

router = APIRouter()


@router.post(
    "/jobs",
    status_code=status.HTTP_202_ACCEPTED,
)
async def enqueue_crawl_job(
    body: CrawlJobCreate,
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    """Create a crawl job row and enqueue a Celery task.

    The actual scraping runs asynchronously in a worker process.
    Poll ``GET /api/v1/crawl/jobs/{id}`` for status.
    """
    service = CrawlJobService(session)
    job = await service.create_and_enqueue(body)

    # Dispatch to Celery
    run_crawl_job.apply_async(
        args=[str(job.id)],
        queue=body.queue or "crawl_default",
    )

    return {"crawl_job_id": str(job.id), "status": "queued"}


@router.get("/jobs/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_job(
    job_id: UUID = Path(..., description="Crawl job UUID"),
    session: AsyncSession = Depends(get_async_session),
) -> CrawlJobResponse:
    """Get the current status of a crawl job."""
    service = CrawlJobService(session)
    job = await service.get_by_id(job_id)
    return CrawlJobResponse.model_validate(job)
