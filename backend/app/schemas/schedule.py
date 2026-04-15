"""Schedule and callback request/response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


# ── URL targets ──────────────────────────────────────────────────


class ScheduleUrlCreate(BaseModel):
    """Add a URL to a schedule's target set."""

    url: str = Field(
        ..., min_length=1, max_length=2000, description="Target URL"
    )
    label: str | None = Field(
        None, max_length=200, description="Optional human-readable label"
    )
    is_active: bool = Field(default=True)


class ScheduleUrlResponse(BaseModel):
    """Serialised URL target."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    url: str
    label: str | None
    is_active: bool
    created_at: datetime


# ── Callback config ─────────────────────────────────────────────


class CallbackConfigCreate(BaseModel):
    """Create or replace a callback config on a schedule."""

    url: str = Field(
        ..., min_length=1, max_length=2000, description="Webhook endpoint URL"
    )
    method: str = Field(
        default="POST",
        description="HTTP method: POST, PUT, or PATCH",
    )
    headers: dict | None = Field(
        None, description='Custom headers, e.g. {"Authorization": "Bearer xxx"}'
    )
    field_mapping: dict = Field(
        default_factory=dict,
        description="Payload field mapping (see docs for syntax)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include schedule/job metadata in payload",
    )
    batch_results: bool = Field(
        default=True,
        description="True = send all results in one request; False = one per job",
    )
    retry_count: int = Field(default=3, ge=0, le=10)
    retry_delay_seconds: int = Field(default=30, ge=5, le=3600)
    is_active: bool = Field(default=True)


class CallbackConfigResponse(BaseModel):
    """Serialised callback config."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    url: str
    method: str
    headers: dict | None
    field_mapping: dict
    include_metadata: bool
    batch_results: bool
    retry_count: int
    retry_delay_seconds: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── Callback logs ────────────────────────────────────────────────


class CallbackLogResponse(BaseModel):
    """Serialised callback execution log."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    callback_config_id: UUID
    crawl_job_id: UUID | None
    schedule_id: UUID
    request_url: str
    request_method: str
    request_body: dict | None
    response_status: int | None
    response_body: str | None
    success: bool
    error_message: str | None
    duration_ms: float
    attempt_number: int
    created_at: datetime


# ── Config link (nested) ────────────────────────────────────────


class ScheduleConfigLinkResponse(BaseModel):
    """Serialised config link within a schedule."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    config_id: UUID
    config_name: str | None = None
    priority: int


# ── Schedule ─────────────────────────────────────────────────────


class ScheduleCreate(BaseModel):
    """Create a new crawl schedule."""

    name: str = Field(
        ..., min_length=1, max_length=200, description="Human-readable name"
    )
    description: str | None = None
    timezone: str = Field(default="UTC", max_length=64)

    # Exactly one of these should be set
    cron_expression: str | None = Field(
        None,
        max_length=128,
        description='Cron expression, e.g. "0 */6 * * *"',
    )
    interval_seconds: int | None = Field(
        None,
        ge=30,
        description="Repeat interval in seconds (min 30)",
    )

    default_queue: str = Field(default="crawl_default", max_length=64)

    # Initial sets
    config_ids: list[UUID] = Field(
        default_factory=list,
        description="CrawlConfiguration IDs to link",
    )
    urls: list[ScheduleUrlCreate] = Field(
        default_factory=list,
        description="Initial URL targets",
    )
    callback: CallbackConfigCreate | None = Field(
        None, description="Optional webhook callback"
    )


class ScheduleUpdate(BaseModel):
    """Partial update for a schedule."""

    name: str | None = Field(None, min_length=1, max_length=200)
    description: str | None = None
    timezone: str | None = Field(None, max_length=64)
    cron_expression: str | None = None
    interval_seconds: int | None = Field(None, ge=30)
    default_queue: str | None = Field(None, max_length=64)
    is_active: bool | None = None


class ScheduleResponse(BaseModel):
    """Full schedule response with nested configs, URLs, and callback."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    timezone: str
    cron_expression: str | None
    interval_seconds: int | None
    default_queue: str
    next_run_at: datetime | None
    last_run_at: datetime | None
    run_count: int
    created_at: datetime
    updated_at: datetime

    # Nested
    config_links: list[ScheduleConfigLinkResponse] = []
    url_targets: list[ScheduleUrlResponse] = []
    callback: CallbackConfigResponse | None = None


class ScheduleListResponse(BaseModel):
    """Paginated schedule list."""

    items: list[ScheduleResponse]
    total: int
