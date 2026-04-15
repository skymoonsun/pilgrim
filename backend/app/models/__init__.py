"""Models package — import all models so Alembic can discover them."""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import CallbackMethod, CrawlJobStatus, ScraperProfile, ScheduleStatus
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_job import CrawlJob
from app.models.crawl_job_result import CrawlJobResult
from app.models.crawl_schedule import CrawlSchedule
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.models.callback_config import CallbackConfig
from app.models.callback_log import CallbackLog
from app.models.seed_version import SeedVersion

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "ScraperProfile",
    "CrawlJobStatus",
    "ScheduleStatus",
    "CallbackMethod",
    "CrawlConfiguration",
    "CrawlJob",
    "CrawlJobResult",
    "CrawlSchedule",
    "ScheduleConfigLink",
    "ScheduleUrlTarget",
    "CallbackConfig",
    "CallbackLog",
    "SeedVersion",
]
