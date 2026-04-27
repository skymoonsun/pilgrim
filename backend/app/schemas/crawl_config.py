"""Crawl configuration schemas (create / update / response)."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ScraperProfile


# ── Create ───────────────────────────────────────────────────────
class CrawlConfigCreate(BaseModel):
    """Payload for creating a new crawl configuration."""

    name: str = Field(
        ..., min_length=1, max_length=100, description="Unique config name"
    )
    description: str | None = Field(
        None, max_length=2000, description="Human-readable description"
    )
    scraper_profile: ScraperProfile = Field(
        default=ScraperProfile.FETCHER,
        description="Scrapling fetcher profile",
    )
    fetch_options: dict | None = Field(
        None,
        description="JSONB: timeouts, impersonate, stealthy_headers, etc.",
    )
    extraction_spec: dict = Field(
        default_factory=dict,
        description="JSONB: CSS/XPath selectors, field mappings",
    )
    spider_entrypoint: str | None = Field(
        None,
        max_length=255,
        description="Optional spider module path",
    )
    use_proxy: bool = False
    rotate_user_agent: bool = True
    custom_headers: dict | None = None
    cookies: dict | None = None
    custom_delay: Decimal | None = Field(
        None, ge=0, description="Seconds between requests"
    )
    max_concurrent: int | None = Field(
        None, ge=1, description="Max concurrent requests"
    )
    sanitizer_config_id: UUID | None = Field(
        None, description="Optional sanitizer config to apply after extraction"
    )
    is_active: bool = True


# ── Update (partial) ────────────────────────────────────────────
class CrawlConfigUpdate(BaseModel):
    """Payload for partially updating a crawl configuration."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    scraper_profile: ScraperProfile | None = None
    fetch_options: dict | None = None
    extraction_spec: dict | None = None
    spider_entrypoint: str | None = None
    use_proxy: bool | None = None
    rotate_user_agent: bool | None = None
    custom_headers: dict | None = None
    cookies: dict | None = None
    custom_delay: Decimal | None = None
    max_concurrent: int | None = None
    sanitizer_config_id: UUID | None = None
    is_active: bool | None = None


# ── Response ─────────────────────────────────────────────────────
class CrawlConfigResponse(BaseModel):
    """Single crawl configuration response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    scraper_profile: ScraperProfile
    fetch_options: dict | None
    extraction_spec: dict
    spider_entrypoint: str | None
    use_proxy: bool
    rotate_user_agent: bool
    custom_headers: dict | None
    cookies: dict | None
    custom_delay: Decimal | None
    max_concurrent: int | None
    sanitizer_config_id: UUID | None
    sanitizer_config: "SanitizerConfigResponse | None" = None
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ── List response ────────────────────────────────────────────────
class CrawlConfigListResponse(BaseModel):
    """Paginated list of crawl configurations."""

    items: list[CrawlConfigResponse]
    total: int


# ── Import for forward reference ────────────────────────────────
from app.schemas.sanitizer_config import SanitizerConfigResponse  # noqa: E402

CrawlConfigResponse.model_rebuild()
