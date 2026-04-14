---
trigger: glob
globs: "**/*.py"
description: "Pilgrim service: database-design — segment 3/3. Mirrors .cursor/rules/database-design.mdc."
---

# Pilgrim — database design (part 3/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/database-design.mdc`.

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