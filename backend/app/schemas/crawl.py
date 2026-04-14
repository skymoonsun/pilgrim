"""Crawl and scrape request / response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from app.models.enums import CrawlJobStatus


# ── Synchronous scrape ───────────────────────────────────────────
class ScrapeRequest(BaseModel):
    """Request body for the synchronous scrape endpoint."""

    config_id: UUID = Field(
        ..., description="ID of the CrawlConfiguration to use"
    )
    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Target URL to scrape",
    )


class ScrapeResponse(BaseModel):
    """Response from the synchronous scrape endpoint."""

    config_id: UUID
    url: str
    http_status: int | None = None
    data: dict | list | None = None
    error: str | None = None
    duration_ms: float | None = None


# ── Async crawl job ──────────────────────────────────────────────
class CrawlJobCreate(BaseModel):
    """Request body to enqueue an asynchronous crawl job."""

    config_id: UUID = Field(
        ..., description="CrawlConfiguration ID"
    )
    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Target URL",
    )
    queue: str | None = Field(
        None, description="Override Celery queue (default: crawl_default)"
    )
    priority: int = Field(
        default=5, ge=1, le=10, description="Job priority (1=low, 10=high)"
    )
    idempotency_key: str | None = Field(
        None,
        max_length=128,
        description="Client-provided dedup key",
    )


class CrawlJobResponse(BaseModel):
    """Crawl job status response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    crawl_configuration_id: UUID
    target_url: str
    status: CrawlJobStatus
    celery_task_id: str | None
    queue: str
    priority: int
    error_message: str | None
    result_summary: dict | None
    created_at: datetime
    updated_at: datetime
