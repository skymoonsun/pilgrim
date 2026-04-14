"""Models package — import all models so Alembic can discover them."""

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import CrawlJobStatus, ScraperProfile
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_job import CrawlJob
from app.models.crawl_job_result import CrawlJobResult
from app.models.crawl_schedule import CrawlSchedule
from app.models.seed_version import SeedVersion

__all__ = [
    "Base",
    "TimestampMixin",
    "UUIDMixin",
    "ScraperProfile",
    "CrawlJobStatus",
    "CrawlConfiguration",
    "CrawlJob",
    "CrawlJobResult",
    "CrawlSchedule",
    "SeedVersion",
]
