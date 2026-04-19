"""Models package — import all models so Alembic can discover them."""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import (
    CallbackMethod,
    CrawlJobStatus,
    ProxyFormatType,
    ProxyHealthStatus,
    ProxyProtocol,
    ScraperProfile,
    ScheduleStatus,
)
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_job import CrawlJob
from app.models.crawl_job_result import CrawlJobResult
from app.models.crawl_schedule import CrawlSchedule
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.models.callback_config import CallbackConfig
from app.models.callback_log import CallbackLog
from app.models.email_notification_config import EmailNotificationConfig
from app.models.email_notification_log import EmailNotificationLog
from app.models.proxy_source_config import ProxySourceConfig
from app.models.valid_proxy import ValidProxy
from app.models.seed_version import SeedVersion

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "ScraperProfile",
    "CrawlJobStatus",
    "ScheduleStatus",
    "CallbackMethod",
    "ProxyFormatType",
    "ProxyProtocol",
    "ProxyHealthStatus",
    "CrawlConfiguration",
    "CrawlJob",
    "CrawlJobResult",
    "CrawlSchedule",
    "ScheduleConfigLink",
    "ScheduleUrlTarget",
    "CallbackConfig",
    "CallbackLog",
    "EmailNotificationConfig",
    "EmailNotificationLog",
    "ProxySourceConfig",
    "ValidProxy",
    "SeedVersion",
]
