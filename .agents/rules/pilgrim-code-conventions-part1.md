---
trigger: glob
globs: "**/*.py"
description: "Pilgrim service: code-conventions — segment 1/3. Mirrors .cursor/rules/code-conventions.mdc."
---

# Pilgrim — code conventions (part 1/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/code-conventions.mdc`.

# Code Conventions - Pilgrim Service

This document defines code writing rules and standards for the Pilgrim Service project. All developers and AI assistants must follow these conventions.

## 1. General Python Rules

### Code Format and Style
```python
# Use Python 3.11+ syntax
# Follow PEP 8 standards
# Use Black formatter for automatic formatting
# Line length: 88 characters (Black default)

# ✅ Correct
async def get_game_prices(
    game_id: str,
    store_ids: list[int] | None = None,
    include_discounts: bool = True
) -> list[GamePriceResponse]:
    """Retrieve game prices from specified stores."""
    pass

# ❌ Wrong
def get_game_prices(game_id,store_ids=None,include_discounts=True):
    pass
```

### Import Order
```python
# 1. Standard library imports
import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional, Union
from uuid import UUID

# 2. Third-party imports
import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# 3. Local imports
from app.core.config import settings
from app.db.database import get_async_session
from app.models.game import Game
from app.schemas.game import GameResponse
from app.services.crawl_service import CrawlService
```

### Type Hinting (Mandatory)
```python
# ✅ Use type hints for every function, method and variable
async def process_game_data(
    raw_data: dict[str, Any],
    store_id: int,
    session: AsyncSession
) -> GamePriceCreate:
    game_title: str = raw_data.get("title", "")
    price_value: float = float(raw_data.get("price", 0.0))
    return GamePriceCreate(title=game_title, price=price_value)

# ❌ Don't write without type hints
async def process_game_data(raw_data, store_id, session):
    pass
```

## 2. FastAPI Conventions

### API Router Structure
```python
# File: app/api/v1/endpoints/games.py
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/games", tags=["games"])

@router.get("/", response_model=list[GameResponse])
async def get_games(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Number of records to return"),
    store_id: int | None = Query(None, description="Filter by store ID"),
    session: AsyncSession = Depends(get_async_session)
) -> list[GameResponse]:
    """
    Retrieve games with optional filtering.
    
    - **skip**: Number of records to skip for pagination
    - **limit**: Maximum number of records to return
    - **store_id**: Optional store ID filter
    """
    # Implementation here
    pass

@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: UUID = Path(..., description="Game unique identifier"),
    session: AsyncSession = Depends(get_async_session)
) -> GameResponse:
    """Get a specific game by ID."""
    # Implementation here
    pass
```

### HTTP Status Codes
```python
from fastapi import status

# ✅ Use explicit status codes
@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_game():
    pass

@router.get("/{game_id}")
async def get_game():
    # Use HTTPException for 404
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with ID {game_id} not found"
        )
```

### Dependency Injection
```python
# ✅ Consistent pattern for service dependencies
async def get_crawl_service() -> CrawlService:
    return CrawlService(http_client=httpx.AsyncClient())

async def get_game_service(
    session: AsyncSession = Depends(get_async_session)
) -> GameService:
    return GameService(session=session)

@router.post("/crawl")
async def crawl_game_data(
    request: CrawlRequest,
    crawl_service: CrawlService = Depends(get_crawl_service),
    game_service: GameService = Depends(get_game_service)
):
    pass
```

## 3. Pydantic Schema Rules

### Model Structure
```python
# File: app/schemas/game.py
from datetime import datetime
from decimal import Decimal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator

class GameBase(BaseModel):
    """Base game schema with common fields."""
    title: str = Field(..., min_length=1, max_length=255, description="Game title")
    description: str | None = Field(None, max_length=2000)
    release_date: datetime | None = None
    developer: str | None = Field(None, max_length=100)
    publisher: str | None = Field(None, max_length=100)

class GameCreate(GameBase):
    """Schema for creating a new game."""
    steam_app_id: int | None = None
    epic_game_id: str | None = None

class GameUpdate(BaseModel):
    """Schema for updating a game."""
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=2000)
    # Partial updates with Optional fields

class GameResponse(GameBase):
    """Schema for game API responses."""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime

# Price schemas
class GamePriceBase(BaseModel):
    price: Decimal = Field(..., ge=0, decimal_places=2)
    no_discount_price: Decimal | None = Field(None, ge=0, decimal_places=2)
    currency_code: str = Field(..., min_length=3, max_length=3)
    in_stock: bool = True

    @field_validator("currency_code")
    @classmethod
    def validate_currency(cls, v: str) -> str:
        if not v.isupper():
            raise ValueError("Currency code must be uppercase")
        return v

class GamePriceCreate(GamePriceBase):
    game_id: UUID
    store_id: int

class GamePriceResponse(GamePriceBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    game_id: UUID
    store_id: int
    created_at: datetime
    discount_percentage: float | None = None
```

### Validation Patterns
```python
# ✅ Pydantic v2: use field_validator / model_validator + ConfigDict
from pydantic import field_validator, model_validator

@field_validator("email")
@classmethod
def validate_email_format(cls, v: str) -> str:
    return v

@field_validator("price")
@classmethod
def validate_positive_price(cls, v: float) -> float:
    if v < 0:
        raise ValueError("Price must be positive")
    return v

# ✅ Use Field parameters for field validation
price: Decimal = Field(
    ...,
    ge=0,
    decimal_places=2,
    description="Game price in store currency"
)
```

## 4. SQLAlchemy Model Rules

### Model Definitions
```python
# File: app/models/game.py
from datetime import datetime
from decimal import Decimal
from uuid import uuid4

from sqlalchemy import (
    Boolean, Column, DateTime, ForeignKey, Integer, 
    Numeric, String, Text, func
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncAttrs
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(AsyncAttrs, DeclarativeBase):
    """Base model class."""
    pass

class TimestampMixin:
    """Mixin for created_at and updated_at timestamps."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=func.now(),
        nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        onupdate=func.now(),
        nullable=False
    )

class Game(Base, TimestampMixin):
    """Game model."""
    __tablename__ = "games"

    # Primary key
    id: Mapped[UUID] = mapped_column(
        UUID(as_uuid=True), 
        primary_key=True, 
        default=uuid4
    )
    
    # Basic fields
    title: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    release_date: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    
    # External IDs
    steam_app_id: Mapped[int | None] = mapped_column(Integer, nullable=True, unique=True)
    epic_game_id: Mapped[str | None] = mapped_column(String(100), nullable=True, unique=True)
    
    # Relationships
    prices: Mapped[list["GamePrice"]] = relationship(
        "GamePrice", 
        back_populates="game",
        cascade="all, delete-orphan"
    )
    
    def __repr__(self) -> str:
        return f"<Game(id={self.id}, title='{self.title}')>"

class Store(Base, TimestampMixin):
    """Store model."""
    __tablename__ = "stores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    base_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    prices: Mapped[list["GamePrice"]] = relationship("GamePrice", back_populates="store")
    crawl_configs: Mapped[list["CrawlConfiguration"]] = relationship(
        "CrawlConfiguration", 
        back_populates="store"
    )

class GamePrice(Base, TimestampMixin):
    """Game price model."""
    __tablename__ = "game_prices"

    id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    
    # Foreign keys
    game_id: Mapped[UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("games.id"), nullable=False)
    store_id: Mapped[int] = mapped_column(Integer, ForeignKey("stores.id"), nullable=False)
    currency_id: Mapped[int] = mapped_column(Integer, ForeignKey("currencies.id"), nullable=False)
    
    # Price fields
    price: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False)
    no_discount_price: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    in_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # URLs
    product_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    affiliate_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    
    # Relationships
    game: Mapped["Game"] = relationship("Game", back_populates="prices")
    store: Mapped["Store"] = relationship("Store", back_populates="prices")
    currency: Mapped["Currency"] = relationship("Currency")
    
    # Indexes
    __table_args__ = (
        # Composite index for queries
        {"extend_existing": True}
    )
```

