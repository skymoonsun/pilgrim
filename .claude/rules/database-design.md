---
paths:
  - "app/models/**/*.py"
  - "app/schemas/**/*.py"
  - "app/db/**/*.py"
  - "alembic/**/*"
---

> Claude Code: modular rules in `.claude/rules/` — [Memory & rules](https://code.claude.com/docs/en/memory). Cursor equivalent: `.cursor/rules/database-design.mdc`.

# Database Design Guidelines - Pilgrim Service

PostgreSQL + **SQLAlchemy 2.0** (async). Crawl execution is **out-of-process** (Celery); the DB stores **configuration**, **job state**, **schedules**, and **domain data** (games, prices, history).

## 1. Core Database Design Principles

### Entity Relationship Design
```python
# File: app/models/base.py
from datetime import datetime
from uuid import uuid4
from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(AsyncAttrs, DeclarativeBase):
    """Base model class for all database entities."""
    pass

class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=func.now(),
        nullable=False,
        index=True  # For sorting queries
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True  # For filtering by update time
    )

class UUIDMixin:
    """Mixin for UUID primary keys."""
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4,
        nullable=False
    )
```

### Core Entity Models
```python
# File: app/models/game.py
from decimal import Decimal
from sqlalchemy import String, Text, Integer, Boolean, Numeric, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .base import Base, TimestampMixin, UUIDMixin

class Game(Base, UUIDMixin, TimestampMixin):
    """Game entity with comprehensive metadata."""
    __tablename__ = "games"

    # Core game information
    title: Mapped[str] = mapped_column(
        String(255), 
        nullable=False, 
        index=True  # For search queries
    )
    normalized_title: Mapped[str] = mapped_column(
        String(255), 
        nullable=False, 
        index=True  # For duplicate detection
    )
    description: Mapped[str | None] = mapped_column(Text)
    short_description: Mapped[str | None] = mapped_column(String(500))
    
    # Game metadata
    developer: Mapped[str | None] = mapped_column(String(100), index=True)
    publisher: Mapped[str | None] = mapped_column(String(100), index=True)
    release_date: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    genre: Mapped[str | None] = mapped_column(String(100), index=True)
    
    # External platform IDs for deduplication
    steam_app_id: Mapped[int | None] = mapped_column(
        Integer, 
        unique=True, 
        nullable=True,
        index=True
    )
    epic_game_id: Mapped[str | None] = mapped_column(
        String(100), 
        unique=True, 
        nullable=True,
        index=True
    )
    gog_game_id: Mapped[str | None] = mapped_column(
        String(100), 
        unique=True, 
        nullable=True,
        index=True
    )
    
    # Game status and quality metrics
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    quality_score: Mapped[Decimal] = mapped_column(
        Numeric(3, 2), 
        default=Decimal('0.0'),
        index=True  # For quality-based filtering
    )
    
    # Relationships
    prices: Mapped[list["GamePrice"]] = relationship(
        "GamePrice", 
        back_populates="game",
        cascade="all, delete-orphan",
        lazy="selectin"  # Optimize for async loading
    )
    
    # Composite indexes for common query patterns
    __table_args__ = (
        Index('idx_game_title_developer', 'title', 'developer'),
        Index('idx_game_active_quality', 'is_active', 'quality_score'),
        Index('idx_game_release_genre', 'release_date', 'genre'),
    )
```

### Store and Configuration Models
```python
# File: app/models/store.py
class Store(Base, TimestampMixin):
    """Store/platform entity."""
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    
    # Store information
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(255))
    country_code: Mapped[str] = mapped_column(String(2), default='US', index=True)
    
    # Store configuration
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    store_type: Mapped[str] = mapped_column(
        String(20), 
        default='web',  # web, api, feed
        index=True
    )
    
    # Rate limiting and crawling configuration
    max_requests_per_hour: Mapped[int] = mapped_column(Integer, default=100)
    min_delay_seconds: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=Decimal('1.0'))
    
    # Relationships
    prices: Mapped[list["GamePrice"]] = relationship("GamePrice", back_populates="store")
    crawl_configs: Mapped[list["CrawlConfiguration"]] = relationship(
        "CrawlConfiguration", 
        back_populates="store"
    )

class Currency(Base):
    """Currency reference table."""
    __tablename__ = "currencies"
    
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(3), nullable=False, unique=True, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    symbol: Mapped[str] = mapped_column(String(5), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
```

### Price Tracking Models
```python
# File: app/models/price.py
class GamePrice(Base, UUIDMixin, TimestampMixin):
    """Game price tracking with history."""
    __tablename__ = "game_prices"

    # Foreign keys
    game_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("games.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    store_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("stores.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    currency_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("currencies.id"), 
        nullable=False,
        index=True
    )
    
    # Price information
    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2), 
        nullable=False,
        index=True  # For price range queries
    )
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    discount_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    
    # Availability and stock
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    stock_level: Mapped[str | None] = mapped_column(String(20))  # low, medium, high
    
    # URLs and metadata
    product_url: Mapped[str] = mapped_column(String(500), nullable=False)
    affiliate_url: Mapped[str | None] = mapped_column(String(500))
    
    # Data quality and freshness
    last_crawled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=func.now(),
        index=True
    )
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    
    # Relationships
    game: Mapped["Game"] = relationship("Game", back_populates="prices")
    store: Mapped["Store"] = relationship("Store", back_populates="prices")
    currency: Mapped["Currency"] = relationship("Currency")
    
    # Composite indexes for efficient queries
    __table_args__ = (
        Index('idx_price_game_store', 'game_id', 'store_id'),
        Index('idx_price_store_updated', 'store_id', 'updated_at'),
        Index('idx_price_game_price_range', 'game_id', 'price'),
        Index('idx_price_active_stock', 'in_stock', 'is_stale'),
        # Unique constraint to prevent duplicate entries
        Index('uq_game_store_price', 'game_id', 'store_id', unique=True),
    )

class PriceHistory(Base, UUIDMixin):
    """Historical price tracking for trend analysis."""
    __tablename__ = "price_history"
    
    game_price_id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        ForeignKey("game_prices.id", ondelete="CASCADE"), 
        nullable=False,
        index=True
    )
    
    # Historical price data
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    recorded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=func.now(),
        index=True
    )
    
    # Change tracking
    price_change: Mapped[Decimal | None] = mapped_column(Numeric(10, 2))
    change_percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    
    __table_args__ = (
        Index('idx_history_game_price_date', 'game_price_id', 'recorded_at'),
        # For large tables, add a migration-only DESC index for time-series reads:
        # CREATE INDEX CONCURRENTLY idx_price_history_series
        #   ON price_history (game_price_id, recorded_at DESC);
    )
```

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

## 3. Migration Patterns

### Alembic Best Practices
```python
# migrations/env.py - Migration environment setup
import asyncio
from logging.config import fileConfig
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config
from alembic import context
from app.core.config import settings
from app.models.base import Base

# Import all models for auto-generation
from app.models.game import Game
from app.models.store import Store, Currency
from app.models.price import GamePrice, PriceHistory
from app.models.proxy_config import ProxyRotationConfig
from app.models.crawl_config import CrawlConfiguration, DataFeed
from app.models.crawl_job import CrawlJob
from app.models.crawl_job_result import CrawlJobResult
from app.models.crawl_schedule import CrawlSchedule

config = context.config
fileConfig(config.config_file_name)
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = settings.database_url
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection, 
        target_metadata=target_metadata,
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()

async def run_async_migrations() -> None:
    """Run migrations in async mode."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()

def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

### Migration File Pattern
```python
# migrations/versions/001_initial_schema.py
"""Initial schema

Revision ID: 001
Revises: 
Create Date: 2024-01-01 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '001'
down_revision = None
branch_labels = None
depends_on = None

def upgrade() -> None:
    # Create currencies table first (referenced by other tables)
    op.create_table('currencies',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('code', sa.String(length=3), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('symbol', sa.String(length=5), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('code')
    )
    op.create_index(op.f('ix_currencies_code'), 'currencies', ['code'])
    op.create_index(op.f('ix_currencies_is_active'), 'currencies', ['is_active'])

    # Insert default currencies
    op.execute("""
        INSERT INTO currencies (code, name, symbol, is_active) VALUES
        ('USD', 'US Dollar', '$', true),
        ('EUR', 'Euro', '€', true),
        ('TRY', 'Turkish Lira', '₺', true),
        ('GBP', 'British Pound', '£', true)
    """)

    # Create other tables...
    # (Continue with stores, games, prices, etc.)

def downgrade() -> None:
    op.drop_table('currencies')
    # Drop other tables in reverse order...
```

## 4. Database Performance Optimization

### Index Strategies
```python
# File: app/models/indexes.py
"""
Database index strategies for optimal query performance.
"""

# Common query patterns and their indexes:

# 1. Game search by title (partial match)
# Index: gin_trgm_idx on normalized_title using gin(normalized_title gin_trgm_ops)
CREATE_TRIGRAM_INDEX = """
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE INDEX CONCURRENTLY idx_games_title_trigram 
ON games USING gin(normalized_title gin_trgm_ops);
"""

# 2. Price queries by game and date range
# Index: (game_id, updated_at) for time-series queries
CREATE_PRICE_TIME_INDEX = """
CREATE INDEX CONCURRENTLY idx_prices_game_time_series 
ON game_prices (game_id, updated_at DESC);
"""

# 3. Active games with recent prices
# Index: (is_active, last_crawled_at) for freshness queries
CREATE_FRESHNESS_INDEX = """
CREATE INDEX CONCURRENTLY idx_prices_active_fresh 
ON game_prices (is_stale, last_crawled_at DESC) 
WHERE in_stock = true;
"""

# 4. Store-specific crawling queries
# Index: (store_id, is_stale, updated_at) for crawl scheduling
CREATE_CRAWL_QUEUE_INDEX = """
CREATE INDEX CONCURRENTLY idx_prices_crawl_queue 
ON game_prices (store_id, is_stale, updated_at) 
WHERE in_stock = true;
"""

# 5. Price history time-series (latest N points per listing)
CREATE_PRICE_HISTORY_TS_INDEX = """
CREATE INDEX CONCURRENTLY idx_price_history_series
ON price_history (game_price_id, recorded_at DESC);
"""

# 6. Crawl job dashboard (by store via config) and queue ops
CREATE_CRAWL_JOB_STATUS_INDEX = """
CREATE INDEX CONCURRENTLY idx_crawl_jobs_status_created
ON crawl_jobs (status, created_at DESC);
"""
```

### Query Optimization Patterns
```python
# File: app/db/query_patterns.py
"""
Optimized query patterns for common operations.
"""
from sqlalchemy import select, and_, or_, func
from sqlalchemy.orm import selectinload, joinedload
from app.models.game import Game
from app.models.price import GamePrice

class OptimizedQueries:
    """Pre-optimized query patterns."""
    
    @staticmethod
    def get_games_with_recent_prices():
        """Get games with their most recent prices."""
        return (
            select(Game)
            .options(
                selectinload(Game.prices)
                .where(GamePrice.is_stale == False)
                .order_by(GamePrice.updated_at.desc())
                .limit(5)  # Only load 5 most recent prices per game
            )
            .where(Game.is_active == True)
        )
    
    @staticmethod
    def get_price_comparison(game_id: str):
        """Get price comparison across all stores for a game."""
        return (
            select(GamePrice)
            .options(joinedload(GamePrice.store))
            .where(
                and_(
                    GamePrice.game_id == game_id,
                    GamePrice.in_stock == True,
                    GamePrice.is_stale == False
                )
            )
            .order_by(GamePrice.price.asc())
        )
    
    @staticmethod
    def get_stale_prices_for_crawling(store_id: int, limit: int = 100):
        """Get stale prices that need crawling for a specific store."""
        return (
            select(GamePrice)
            .options(joinedload(GamePrice.game))
            .where(
                and_(
                    GamePrice.store_id == store_id,
                    or_(
                        GamePrice.is_stale == True,
                        GamePrice.last_crawled_at < func.now() - func.interval('1 hour')
                    )
                )
            )
            .order_by(GamePrice.last_crawled_at.asc())
            .limit(limit)
        )
```

## 5. Data Integrity and Constraints

### Business Logic Constraints
```python
# File: app/models/constraints.py
"""
Business logic constraints and validation rules.
"""
from sqlalchemy import CheckConstraint, event
from sqlalchemy.orm import validates
from decimal import Decimal

class GamePrice(Base):
    # ... other fields ...
    
    # Database-level constraints
    __table_args__ = (
        CheckConstraint('price >= 0', name='check_price_positive'),
        CheckConstraint('original_price IS NULL OR original_price >= price', 
                       name='check_original_price_valid'),
        CheckConstraint('discount_percentage IS NULL OR (discount_percentage >= 0 AND discount_percentage <= 100)', 
                       name='check_discount_percentage_valid'),
    )
    
    @validates('price')
    def validate_price(self, key, value):
        """Validate price is positive."""
        if value < 0:
            raise ValueError("Price must be positive")
        return value
    
    @validates('discount_percentage')
    def validate_discount(self, key, value):
        """Validate discount percentage is between 0-100."""
        if value is not None and not (0 <= value <= 100):
            raise ValueError("Discount percentage must be between 0 and 100")
        return value

# Event listeners for automatic calculations
@event.listens_for(GamePrice, 'before_insert')
@event.listens_for(GamePrice, 'before_update')
def calculate_discount_percentage(mapper, connection, target):
    """Automatically calculate discount percentage."""
    if target.original_price and target.price:
        if target.original_price > target.price:
            discount = (target.original_price - target.price) / target.original_price * 100
            target.discount_percentage = round(Decimal(str(discount)), 2)
        else:
            target.discount_percentage = None
```

Create tables in dependency order (e.g. `proxy_rotation_configs` before `crawl_configurations` if referenced). These guidelines align the schema with **Scrapling** configs, **Celery** job rows, **Beat** schedules, and **price history** analytics.