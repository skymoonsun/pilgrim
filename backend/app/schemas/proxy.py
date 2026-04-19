"""Proxy management schemas (create / update / response)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ProxyFormatType, ProxyHealthStatus, ProxyProtocol


# ── Proxy Source Config ────────────────────────────────────────


class ProxySourceCreate(BaseModel):
    """Payload for creating a new proxy source config."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Unique source name"
    )
    description: str | None = Field(
        None, max_length=2000, description="Human-readable description"
    )
    url: str = Field(
        ..., min_length=1, max_length=2000, description="Proxy list source URL"
    )
    format_type: ProxyFormatType = Field(
        default=ProxyFormatType.RAW_TEXT,
        description="Format of the proxy list source",
    )
    extraction_spec: dict | None = Field(
        None,
        description="JSONB: extraction rules for JSON/XML/CSV sources",
    )
    source_headers: dict | None = Field(
        None,
        description="Optional HTTP headers for fetching the source",
    )
    validation_urls: dict = Field(
        default_factory=dict,
        description='JSONB: {"urls": ["https://example.com"]}',
    )
    require_all_urls: bool = Field(
        default=True,
        description="All validation URLs must succeed for proxy to be healthy",
    )
    validation_timeout: int = Field(
        default=10, ge=1, le=120, description="Seconds per validation request"
    )
    fetch_interval_seconds: int = Field(
        default=3600, ge=60, description="Re-fetch frequency in seconds"
    )
    proxy_ttl_seconds: int = Field(
        default=86400, ge=60, description="Proxy expiry after validation in seconds"
    )
    max_proxies: int | None = Field(
        None, ge=1, le=100000, description="Max proxies to process (None = unlimited)"
    )
    is_active: bool = True


class ProxySourceUpdate(BaseModel):
    """Payload for partially updating a proxy source config."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    url: str | None = Field(None, min_length=1, max_length=2000)
    format_type: ProxyFormatType | None = None
    extraction_spec: dict | None = None
    source_headers: dict | None = None
    validation_urls: dict | None = None
    require_all_urls: bool | None = None
    validation_timeout: int | None = Field(None, ge=1, le=120)
    fetch_interval_seconds: int | None = Field(None, ge=60)
    proxy_ttl_seconds: int | None = Field(None, ge=60)
    max_proxies: int | None = Field(None, ge=1, le=100000)
    is_active: bool | None = None


class ProxySourceResponse(BaseModel):
    """Single proxy source config response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    url: str
    format_type: ProxyFormatType
    extraction_spec: dict | None
    source_headers: dict | None
    validation_urls: dict
    require_all_urls: bool
    validation_timeout: int
    fetch_interval_seconds: int
    proxy_ttl_seconds: int
    max_proxies: int | None
    last_fetched_at: datetime | None
    last_fetch_error: str | None
    created_at: datetime
    updated_at: datetime


class ProxySourceListResponse(BaseModel):
    """Paginated list of proxy source configs."""

    items: list[ProxySourceResponse]
    total: int


# ── Valid Proxy ─────────────────────────────────────────────────


class ValidProxyResponse(BaseModel):
    """Single valid proxy response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_config_id: UUID | None
    source_name: str | None = None
    ip: str
    port: int
    protocol: ProxyProtocol
    username: str | None
    password: str | None
    health: ProxyHealthStatus
    avg_response_ms: float | None
    success_count: int
    failure_count: int
    last_checked_at: datetime | None
    last_success_at: datetime | None
    expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ValidProxyListResponse(BaseModel):
    """Paginated list of valid proxies."""

    items: list[ValidProxyResponse]
    total: int


# ── Fetch / Validate trigger ───────────────────────────────────


class FetchTriggerResponse(BaseModel):
    """Response for triggering a proxy source fetch."""

    source_id: UUID
    task_id: str
    message: str


class ValidateTriggerResponse(BaseModel):
    """Response for triggering proxy validation."""

    source_id: UUID
    task_id: str
    message: str


# ── Manual proxy creation ──────────────────────────────────────


class ManualProxyCreate(BaseModel):
    """Payload for adding a single manual proxy."""

    ip: str = Field(..., min_length=1, max_length=45, description="Proxy IP address")
    port: int = Field(..., ge=1, le=65535, description="Proxy port")
    protocol: ProxyProtocol = Field(
        default=ProxyProtocol.HTTP, description="Proxy protocol"
    )
    username: str | None = Field(None, max_length=255, description="Auth username")
    password: str | None = Field(None, max_length=255, description="Auth password")


class ManualProxyBulkCreate(BaseModel):
    """Payload for bulk-adding manual proxies via raw text lines."""

    raw_text: str = Field(
        ...,
        min_length=1,
        description="One proxy per line: ip:port, protocol://ip:port, protocol://user:pass@ip:port",
    )
    default_protocol: ProxyProtocol = Field(
        default=ProxyProtocol.HTTP,
        description="Protocol for lines without explicit protocol prefix",
    )


class ManualProxyCreateResult(BaseModel):
    """Result of manual proxy creation (single or bulk)."""

    created: int = Field(..., description="Number of proxies newly created")
    skipped: int = Field(..., description="Number of proxies already existing (upserted)")
    items: list[ValidProxyResponse] = Field(
        default_factory=list, description="Created proxy entries"
    )


class BulkDeleteRequest(BaseModel):
    """Payload for bulk-deleting proxies by ID list."""

    proxy_ids: list[UUID] = Field(
        ..., min_length=1, description="List of proxy UUIDs to delete"
    )


class BulkDeleteResponse(BaseModel):
    """Result of a bulk or full delete operation."""

    deleted: int = Field(..., description="Number of proxies deleted")