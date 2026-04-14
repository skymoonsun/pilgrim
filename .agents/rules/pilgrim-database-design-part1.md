---
trigger: glob
globs: "**/*.py"
description: "Pilgrim service: database-design — segment 1/3. Mirrors .cursor/rules/database-design.mdc."
---

# Pilgrim — database design (part 1/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/database-design.mdc`.

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

