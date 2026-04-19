"""Schedule and callback request/response schemas.

URLs are nested under config links (not schedule-level), so each config
has its own URL target set.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ── URL targets ──────────────────────────────────────────────────


class ScheduleUrlCreate(BaseModel):
    """Add a URL to a config link's target set."""

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


# ── Config link + nested URLs ────────────────────────────────────


class ConfigLinkUrlsCreate(BaseModel):
    """A config ID with its own URL targets for schedule creation."""

    config_id: str = Field(..., description="CrawlConfiguration UUID")
    urls: list[ScheduleUrlCreate] = Field(
        default_factory=list,
        description="URLs to crawl with this config",
    )


class ScheduleConfigLinkResponse(BaseModel):
    """Serialised config link with its nested URL targets."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    config_id: UUID
    config_name: str | None = None
    priority: int
    url_targets: list[ScheduleUrlResponse] = []


# ── Proxy source link ─────────────────────────────────────────────


class ProxySourceLinkCreate(BaseModel):
    """A proxy source ID for schedule creation."""

    proxy_source_id: str = Field(..., description="ProxySourceConfig UUID")


class ScheduleProxySourceLinkResponse(BaseModel):
    """Serialised proxy source link."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    proxy_source_id: UUID
    proxy_source_name: str | None = None
    priority: int


# ── Email notification config ────────────────────────────────────


class EmailNotificationConfigCreate(BaseModel):
    """Create or replace an email notification config on a schedule."""

    recipient_emails: list[str] = Field(
        ..., min_length=1, max_length=20,
        description="Email addresses to notify",
    )
    subject_template: str = Field(
        default="Pilgrim: {{schedule_name}} completed",
        max_length=500,
        description="Subject line with optional {{var}} placeholders",
    )
    field_mapping: dict = Field(
        default_factory=dict,
        description="Payload field mapping (same syntax as callback)",
    )
    include_metadata: bool = Field(
        default=True,
        description="Include schedule/job metadata in email body",
    )
    batch_results: bool = Field(
        default=True,
        description="True = all results in one email; False = one per job",
    )
    on_success: bool = Field(
        default=True,
        description="Send email on job success",
    )
    on_failure: bool = Field(
        default=True,
        description="Send email on job failure",
    )
    is_active: bool = Field(default=True)

    @field_validator("recipient_emails")
    @classmethod
    def validate_emails(cls, v: list[str]) -> list[str]:
        for email in v:
            if "@" not in email or "." not in email.split("@")[-1]:
                raise ValueError(f"Invalid email address: {email}")
        return v


class EmailNotificationConfigResponse(BaseModel):
    """Serialised email notification config."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    schedule_id: UUID
    recipient_emails: list[str]
    subject_template: str
    field_mapping: dict
    include_metadata: bool
    batch_results: bool
    on_success: bool
    on_failure: bool
    is_active: bool
    created_at: datetime
    updated_at: datetime


class EmailNotificationLogResponse(BaseModel):
    """Serialised email notification execution log."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email_notification_config_id: UUID
    crawl_job_id: UUID | None
    schedule_id: UUID
    recipients: list[str]
    subject: str
    trigger_reason: str
    success: bool
    error_message: str | None
    smtp_response_code: int | None
    duration_ms: float
    attempt_number: int
    created_at: datetime


# ── Schedule ─────────────────────────────────────────────────────


class ScheduleCreate(BaseModel):
    """Create a new crawl schedule.

    Each config_link contains a config_id and its own URL targets.
    This ensures each URL is paired with the correct config.
    """

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

    # Schedule type
    schedule_type: str = Field(
        default="crawl",
        description="Schedule type: 'crawl' or 'proxy_source'",
    )

    # Config links with per-config URLs (for crawl schedules)
    config_links: list[ConfigLinkUrlsCreate] = Field(
        default_factory=list,
        description="Config + URL pairs (for crawl schedules)",
    )

    # Proxy source links (for proxy_source schedules)
    proxy_source_links: list[ProxySourceLinkCreate] = Field(
        default_factory=list,
        description="Proxy source IDs (for proxy_source schedules)",
    )

    callback: CallbackConfigCreate | None = Field(
        None, description="Optional webhook callback"
    )
    email_notification: EmailNotificationConfigCreate | None = Field(
        None, description="Optional email notification"
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
    """Full schedule response with nested config links (each with URLs) and callback."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    schedule_type: str
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
    proxy_source_links: list[ScheduleProxySourceLinkResponse] = []
    callback: CallbackConfigResponse | None = None
    email_notification: EmailNotificationConfigResponse | None = None


class ScheduleListResponse(BaseModel):
    """Paginated schedule list."""

    items: list[ScheduleResponse]
    total: int
