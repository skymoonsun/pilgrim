"""Schemas for the unified activity feed."""

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActivityType(str, Enum):
    CRAWL_JOB = "crawl_job"
    PROXY_FETCH = "proxy_fetch"
    PROXY_VALIDATION = "proxy_validation"


class ActivityItemBase(BaseModel):
    id: UUID
    type: ActivityType
    status: str
    error_message: str | None = None
    created_at: datetime


class CrawlJobActivity(ActivityItemBase):
    type: ActivityType = ActivityType.CRAWL_JOB
    crawl_configuration_id: UUID
    target_url: str
    queue: str
    priority: int
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result_summary: dict | None = None


class ProxyFetchActivity(ActivityItemBase):
    type: ActivityType = ActivityType.PROXY_FETCH
    source_config_id: UUID
    source_name: str | None = None
    proxies_found: int
    proxies_new: int
    proxies_updated: int
    content_length: int
    duration_ms: float


class ProxyValidationActivity(ActivityItemBase):
    type: ActivityType = ActivityType.PROXY_VALIDATION
    source_config_id: UUID
    source_name: str | None = None
    proxies_tested: int
    proxies_healthy: int
    proxies_degraded: int
    proxies_unhealthy: int
    proxies_removed: int
    duration_ms: float


ActivityItem = CrawlJobActivity | ProxyFetchActivity | ProxyValidationActivity


class ActivityListResponse(BaseModel):
    items: list[ActivityItem]
    total: int