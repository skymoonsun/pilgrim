"""Database enums shared across models."""

from enum import Enum


class ScraperProfile(str, Enum):
    """Maps to a Scrapling fetcher/session choice in workers."""

    FETCHER = "fetcher"
    HTTP_SESSION = "http_session"
    STEALTH = "stealth"
    DYNAMIC = "dynamic"
    SPIDER = "spider"


class CrawlJobStatus(str, Enum):
    """Authoritative status for a crawl job row (not Celery state)."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
