---
trigger: glob
globs: "**/*.py"
description: "Pilgrim service: database-design — segment 2/3. Mirrors .cursor/rules/database-design.mdc."
---

# Pilgrim — database design (part 2/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/database-design.mdc`.

## 2. Crawling configuration, jobs, schedules, proxies (Scrapling + Celery)

### Scrapling profile enum (use `SQLEnum` for admin dropdowns)
```python
# File: app/models/enums.py
from enum import Enum


class ScraperProfile(str, Enum):
    """Maps to Scrapling fetcher/session choice in workers."""

    FETCHER = "fetcher"
    HTTP_SESSION = "http_session"
    STEALTH = "stealth"
    DYNAMIC = "dynamic"
    SPIDER = "spider"
```

### Crawl configuration (Scrapling-specific fields)
```python
# File: app/models/crawl_config.py
from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ScraperProfile


class CrawlConfiguration(Base, UUIDMixin, TimestampMixin):
    """Versioned crawl recipe: how workers fetch and extract for a store."""

    __tablename__ = "crawl_configurations"

    store_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    scraper_profile: Mapped[ScraperProfile] = mapped_column(
        SQLEnum(ScraperProfile, name="scraper_profile_enum"),
        nullable=False,
        default=ScraperProfile.FETCHER,
        index=True,
    )

    # Scrapling: timeouts, retries, adaptive/auto_save flags, session hints
    fetch_options: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # Selectors, JSONPath, spider rules, post-processing steps
    extraction_spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # Optional Scrapling spider module path or registry key
    spider_entrypoint: Mapped[str | None] = mapped_column(String(255), nullable=True)

    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    proxy_rotation_config_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_rotation_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    rotate_user_agent: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_headers: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    custom_delay: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    max_concurrent: Mapped[int | None] = mapped_column(Integer)

    store: Mapped["Store"] = relationship("Store", back_populates="crawl_configs")
    proxy_rotation_config: Mapped["ProxyRotationConfig | None"] = relationship(
        "ProxyRotationConfig", back_populates="crawl_configs"
    )
    crawl_jobs: Mapped[list["CrawlJob"]] = relationship(
        "CrawlJob", back_populates="crawl_configuration"
    )
    schedules: Mapped[list["CrawlSchedule"]] = relationship(
        "CrawlSchedule", back_populates="crawl_configuration"
    )
```

### Crawl job row (authoritative status; Celery task id is auxiliary)
```python
# File: app/models/crawl_job.py
from enum import Enum
from uuid import UUID

from sqlalchemy import Enum as SQLEnum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CrawlJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CrawlJob(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "crawl_jobs"

    crawl_configuration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    status: Mapped[CrawlJobStatus] = mapped_column(
        SQLEnum(CrawlJobStatus, name="crawl_job_status_enum"),
        nullable=False,
        default=CrawlJobStatus.QUEUED,
        index=True,
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    queue: Mapped[str] = mapped_column(String(64), nullable=False, default="crawl_default", index=True)
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    crawl_configuration: Mapped["CrawlConfiguration"] = relationship(
        "CrawlConfiguration", back_populates="crawl_jobs"
    )
    results: Mapped[list["CrawlJobResult"]] = relationship(
        "CrawlJobResult", back_populates="crawl_job", cascade="all, delete-orphan"
    )
```

### Per-URL or per-item extraction outcomes (optional normalization)
```python
# File: app/models/crawl_job_result.py
from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CrawlJobResult(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "crawl_job_results"

    crawl_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    source_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)

    crawl_job: Mapped["CrawlJob"] = relationship("CrawlJob", back_populates="results")
```

### Schedule rows consumed by Celery Beat (or synced from code)
```python
# File: app/models/crawl_schedule.py
from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CrawlSchedule(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "crawl_schedules"

    crawl_configuration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    cron_expression: Mapped[str | None] = mapped_column(String(128), nullable=True)
    interval_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    default_queue: Mapped[str] = mapped_column(String(64), nullable=False, default="crawl_default")
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)

    crawl_configuration: Mapped["CrawlConfiguration"] = relationship(
        "CrawlConfiguration", back_populates="schedules"
    )

    __table_args__ = (
        # Exactly one of cron_expression or interval_seconds should be set (enforce in app or CHECK)
    )
```

### Proxy rotation configuration (pool metadata; live pool often in Redis)
```python
# File: app/models/proxy_config.py
from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProxyRotationConfig(Base, UUIDMixin, TimestampMixin):
    __tablename__ = "proxy_rotation_configs"

    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    redis_pool_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    strategy: Mapped[str] = mapped_column(
        String(32), nullable=False, default="round_robin"  # round_robin, random, least_used
    )
    max_failures_before_ban: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    crawl_configs: Mapped[list["CrawlConfiguration"]] = relationship(
        "CrawlConfiguration", back_populates="proxy_rotation_config"
    )
```

### Legacy bulk feeds (unchanged role)
```python
# File: app/models/crawl_config.py (continued)
class DataFeed(Base, UUIDMixin, TimestampMixin):
    """Data feed configuration for bulk imports."""
    __tablename__ = "data_feeds"
    
    store_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("stores.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # Feed metadata
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    feed_type: Mapped[str] = mapped_column(
        String(10), 
        nullable=False,  # xml, json, csv
        index=True
    )
    feed_url: Mapped[str | None] = mapped_column(String(500))
    
    # Processing configuration
    field_mappings: Mapped[str] = mapped_column(Text, nullable=False)  # JSON
    is_compressed: Mapped[bool] = mapped_column(Boolean, default=False)
    compression_type: Mapped[str | None] = mapped_column(String(10))  # zip, gzip
    
    # Schedule and status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    schedule_cron: Mapped[str | None] = mapped_column(String(50))
    last_processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    
    # Relationships
    store: Mapped["Store"] = relationship("Store")
```

