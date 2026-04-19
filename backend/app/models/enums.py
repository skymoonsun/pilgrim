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


class ScheduleStatus(str, Enum):
    """Lifecycle status for a crawl schedule."""

    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    ERROR = "error"


class CallbackMethod(str, Enum):
    """HTTP method for outbound callbacks."""

    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"


class ProxyFormatType(str, Enum):
    """Format of a proxy list source."""

    RAW_TEXT = "raw_text"
    JSON = "json"
    XML = "xml"
    CSV = "csv"


class ProxyProtocol(str, Enum):
    """Supported proxy protocols."""

    HTTP = "http"
    HTTPS = "https"
    SOCKS4 = "socks4"
    SOCKS5 = "socks5"


class ProxyHealthStatus(str, Enum):
    """Health status of a validated proxy."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class ScheduleType(str, Enum):
    """Type of schedule — determines what gets triggered."""

    CRAWL = "crawl"
    PROXY_SOURCE = "proxy_source"
