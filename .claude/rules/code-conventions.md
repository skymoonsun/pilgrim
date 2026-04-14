---
paths:
  - "**/*.py"
---

> Claude Code: modular rules in `.claude/rules/` — [Memory & rules](https://code.claude.com/docs/en/memory). Cursor equivalent: `.cursor/rules/code-conventions.mdc`.

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

## 5. Service Layer Rules

### Service Class Structure
```python
# File: app/services/game_service.py
import logging
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.game import Game, GamePrice
from app.schemas.game import GameCreate, GameUpdate, GameResponse

logger = logging.getLogger(__name__)

class GameService:
    """Service class for game-related operations."""
    
    def __init__(self, session: AsyncSession):
        self.session = session
    
    async def create_game(self, game_data: GameCreate) -> Game:
        """Create a new game."""
        try:
            game = Game(**game_data.model_dump())
            self.session.add(game)
            await self.session.commit()
            await self.session.refresh(game)
            
            logger.info(f"Created game: {game.id} - {game.title}")
            return game
            
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Error creating game: {e}")
            raise
    
    async def get_game_by_id(
        self, 
        game_id: UUID, 
        include_prices: bool = False
    ) -> Optional[Game]:
        """Get game by ID with optional price loading."""
        try:
            query = select(Game).where(Game.id == game_id)
            
            if include_prices:
                query = query.options(selectinload(Game.prices))
            
            result = await self.session.execute(query)
            return result.scalar_one_or_none()
            
        except Exception as e:
            logger.error(f"Error fetching game {game_id}: {e}")
            raise
    
    async def search_games(
        self,
        title_query: Optional[str] = None,
        store_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100
    ) -> list[Game]:
        """Search games with filters."""
        try:
            query = select(Game)
            
            if title_query:
                query = query.where(Game.title.ilike(f"%{title_query}%"))
            
            if store_id:
                query = query.join(GamePrice).where(GamePrice.store_id == store_id)
            
            query = query.offset(skip).limit(limit)
            
            result = await self.session.execute(query)
            return list(result.scalars().all())
            
        except Exception as e:
            logger.error(f"Error searching games: {e}")
            raise
```

### Error Handling Patterns
```python
# ✅ Consistent error handling
class GameServiceError(Exception):
    """Base exception for game service errors."""
    pass

class GameNotFoundError(GameServiceError):
    """Raised when game is not found."""
    pass

class DuplicateGameError(GameServiceError):
    """Raised when trying to create duplicate game."""
    pass

# Service method implementation
async def get_game_by_id(self, game_id: UUID) -> Game:
    try:
        result = await self.session.execute(
            select(Game).where(Game.id == game_id)
        )
        game = result.scalar_one_or_none()
        
        if not game:
            raise GameNotFoundError(f"Game with ID {game_id} not found")
        
        return game
        
    except GameNotFoundError:
        raise  # Re-raise custom exceptions
    except Exception as e:
        logger.error(f"Database error fetching game {game_id}: {e}")
        raise GameServiceError(f"Failed to fetch game: {e}")
```

## 6. Web scraping (Scrapling-first)

- Implement fetch/parse in **`app/crawlers/`** (factory, sessions, spiders). See [.cursor/rules/scraping-strategies.mdc](scraping-strategies.mdc).
- Prefer **Scrapling** fetchers (`Fetcher`, `StealthyFetcher`, `DynamicFetcher`, async sessions) over raw BeautifulSoup/Selenium.
- **`httpx`** is for **JSON/API** clients or tests—not the default HTML pipeline.

```python
# File: app/crawlers/factory.py (illustrative)
from scrapling.fetchers import Fetcher, AsyncDynamicSession

def fetch_static(url: str) -> object:
    return Fetcher.get(url)

async def fetch_dynamic(url: str) -> object:
    async with AsyncDynamicSession(headless=True, network_idle=True) as session:
        return await session.fetch(url)
```

## 7. Configuration and environment

Use **`pydantic-settings`** (`BaseSettings` from `pydantic_settings`) and the full pattern in [.cursor/rules/config-environment.mdc](config-environment.mdc). Keep **one** `get_settings()` cached accessor.

```python
# File: app/core/config.py (abbreviated)
from functools import lru_cache

from pydantic import Field, PostgresDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Pilgrim Service"
    database_url: PostgresDsn = Field(validation_alias="DATABASE_URL")
    redis_url: str = Field(validation_alias="REDIS_URL")

    @field_validator("database_url", mode="after")
    @classmethod
    def postgres_async_driver(cls, v: PostgresDsn) -> PostgresDsn:
        s = str(v)
        if not s.startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use postgresql+asyncpg:// for the API/workers")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
```

## 8. Logging Rules

### Structured Logging
```python
# File: app/core/logging.py
import logging
import sys
from typing import Any, Dict

import structlog

def configure_logging() -> None:
    """Configure structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="ISO"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.UnicodeDecoder(),
            structlog.processors.JSONRenderer()
        ],
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

# Usage in services
logger = structlog.get_logger(__name__)

async def process_game_data(game_id: str):
    logger.info("Processing game data", game_id=game_id)
    
    try:
        # Processing logic
        logger.info("Game data processed successfully", game_id=game_id)
    except Exception as e:
        logger.error(
            "Failed to process game data", 
            game_id=game_id, 
            error=str(e),
            exc_info=True
        )
        raise
```

## 9. Testing Rules

### Test Structure
```python
# File: tests/test_services/test_game_service.py
import pytest
from uuid import uuid4

from app.services.game_service import GameService, GameNotFoundError
from app.schemas.game import GameCreate

class TestGameService:
    """Test cases for GameService."""
    
    @pytest.fixture
    async def game_service(self, async_session):
        """Create GameService instance."""
        return GameService(session=async_session)
    
    @pytest.fixture
    def sample_game_data(self):
        """Sample game data for testing."""
        return GameCreate(
            title="Test Game",
            description="A test game",
            developer="Test Developer",
            steam_app_id=12345
        )
    
    async def test_create_game_success(self, game_service, sample_game_data):
        """Test successful game creation."""
        # Act
        game = await game_service.create_game(sample_game_data)
        
        # Assert
        assert game.title == sample_game_data.title
        assert game.steam_app_id == sample_game_data.steam_app_id
        assert game.id is not None
    
    async def test_get_game_by_id_not_found(self, game_service):
        """Test game not found scenario."""
        # Act & Assert
        with pytest.raises(GameNotFoundError):
            await game_service.get_game_by_id(uuid4())

# Mock usage
@pytest.fixture
def mock_httpx_client():
    """Mock httpx client for testing."""
    with patch('httpx.AsyncClient') as mock:
        yield mock
```

## 10. File and Directory Naming

### Directory structure
```
app/
├── api/
│   └── v1/
│       └── endpoints/
├── core/
│   ├── config.py
│   ├── security.py
│   └── logging.py
├── crawlers/
│   ├── factory.py
│   ├── extraction.py
│   ├── spiders/
│   └── playwright/
├── workers/
│   ├── celery_app.py
│   └── tasks/
├── integrations/
│   └── redis.py
├── db/
├── models/
├── schemas/
├── services/
└── utils/
docker/
├── Dockerfile
└── compose/
    ├── docker-compose.yml
    └── docker-compose.override.yml.example
```

### File naming conventions
- **Snake_case**: `game_service.py`, `crawl_configuration.py`
- **Singular names**: `game.py` (not `games.py`) for model files
- **Descriptive names**: `price_processing_service.py`
- **Docker**: `Dockerfile` at repo root or under `docker/`; compose files `docker-compose.yml`, `docker-compose.prod.yml`
- **Celery**: `celery_app.py` in `app/workers/`; tasks in `app/workers/tasks/<area>.py`

## 11. Celery, Redis, Scrapling, and Docker

### Celery tasks
- Define tasks in **`app/workers/tasks/`**; import them in **`celery_app.include`**.
- Use explicit **`name="pilgrim.<domain>.<verb>"`** and **`queue=`** per [.cursor/rules/celery-scheduler.mdc](celery-scheduler.mdc).
- Task arguments: JSON-safe types only; reload ORM entities inside the task.
- Use **`bind=True`** when you need `self.request` / retries.

### Redis
- Access Redis via a small client wrapper in **`app/integrations/redis.py`** (connection pool, key prefixes).
- Use Redis for locks, rate-limit counters, and short-lived Celery result metadata—not canonical job state (PostgreSQL is).

### Scrapling in workers
- Browser-heavy code runs only in **worker** images (see [.cursor/rules/docker-infrastructure.mdc](docker-infrastructure.mdc)).
- Do not import `DynamicFetcher` / `AsyncStealthySession` in the API process unless documented and tested.

### Docker conventions
- **Docker-first local dev:** run migrations, tests, and the app via Compose (`docker compose`); see [.cursor/rules/docker-infrastructure.mdc](docker-infrastructure.mdc) §11.
- **API** image: slim; no browser.
- **Worker** image: includes `scrapling[fetchers]` and `scrapling install` artifacts as needed.
- **Beat**: same image as worker, different `command`.

## 12. Git commit conventions

### Commit Message Format
```
<type>(<scope>): <subject>

<body>

<footer>
```

### Types
- **feat**: New feature
- **fix**: Bug fix
- **docs**: Documentation changes
- **style**: Code style changes (formatting, etc.)
- **refactor**: Code refactoring
- **test**: Adding or updating tests
- **chore**: Maintenance tasks

### Examples
```
feat(api): add game price comparison endpoint

Add new endpoint to compare game prices across multiple stores.
Includes pagination and filtering options.

Closes #123

fix(crawl): handle timeout errors in price extraction

Add proper error handling for network timeouts during
web scraping operations.

docs(readme): update installation instructions

Update README with latest Docker setup requirements.
```

## 13. Admin UI integration rules

### SQLAlchemy Model Admin Integration
**MANDATORY**: Her yeni SQLAlchemy model oluştururken admin interface için gerekli adımları takip et:

#### 1. Enum Fields - SQLAlchemy Enum Kullanımı
```python
# ✅ Correct - Use SQLAlchemy Enum for dropdown support
from sqlalchemy import Enum as SQLEnum

class MyModel(Base):
    status: Mapped[MyStatusEnum] = mapped_column(
        SQLEnum(MyStatusEnum),
        nullable=False,
        default=MyStatusEnum.ACTIVE
    )

# ❌ Wrong - String will show as text input
class MyModel(Base):
    status: Mapped[MyStatusEnum] = mapped_column(
        String(20),  # This won't create dropdown
        nullable=False,
        default=MyStatusEnum.ACTIVE
    )
```

#### 2. Admin Configuration - Model İçin Admin Class Oluşturma
```python
# File: app/admin/config.py

# ✅ Her yeni model için admin class ekle
class MyModelAdmin(ModelView, model=MyModel):
    """Admin interface for MyModel."""
    
    # Listeleme sayfası kolonları
    column_list = [
        MyModel.id, MyModel.name, MyModel.status, 
        MyModel.is_active, MyModel.created_at
    ]
    
    # Arama yapılabilir alanlar
    column_searchable_list = [MyModel.name]
    
    # Sıralanabilir alanlar
    column_sortable_list = [MyModel.name, MyModel.created_at, MyModel.status]
    
    # Filtrelenebilir alanlar (enum'lar dahil)
    column_filters = [MyModel.status, MyModel.is_active]
    
    # Form alanları (oluşturma/düzenleme)
    form_columns = [
        MyModel.name, MyModel.description, MyModel.status,
        MyModel.is_active, MyModel.config_data
    ]
    
    # Genel ayarlar
    can_create = True
    can_edit = True
    can_delete = False  # Genelde delete'i kısıtla
    
    # UI display settings
    name = "My Model"
    name_plural = "My Models"
    icon = "fa-solid fa-cog"  # Font Awesome icon

# setup_admin function'ına ekleme ZORUNLU
def setup_admin(app: FastAPI, engine: AsyncEngine) -> Admin:
    admin = Admin(...)
    
    # ✅ Yeni admin view'ı ekle
    admin.add_view(MyModelAdmin)
    
    return admin
```

#### 3. Enum Definition Pattern
```python
# ✅ Enum'ları models dosyasında tanımla
class MyStatusEnum(str, Enum):
    """Model status enumeration."""
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"
    ERROR = "error"

# ✅ Enum choices helper (isteğe bağlı)
# File: app/admin/form_widgets.py
MY_STATUS_CHOICES = [
    ("active", "Active"),
    ("inactive", "Inactive"), 
    ("pending", "Pending"),
    ("error", "Error")
]
```

#### 4. Migration Pattern for Enums
```python
# ✅ Migration'da enum type'ı oluştur
def upgrade() -> None:
    # Enum type'ı oluştur
    op.execute("CREATE TYPE mystatusenum AS ENUM ('active', 'inactive', 'pending', 'error')")
    
    # Column'ı güncelle
    op.alter_column('my_table', 'status',
                   existing_type=sa.VARCHAR(length=20),
                   type_=sa.Enum('active', 'inactive', 'pending', 'error', name='mystatusenum'),
                   existing_nullable=False)

def downgrade() -> None:
    # Reverse işlemler
    op.alter_column('my_table', 'status',
                   existing_type=sa.Enum('active', 'inactive', 'pending', 'error', name='mystatusenum'),
                   type_=sa.VARCHAR(length=20),
                   existing_nullable=False)
    
    op.execute("DROP TYPE mystatusenum")
```

### Admin UI Development Checklist

#### Model Oluştururken:
- [ ] Enum alanları için `SQLEnum` kullandım
- [ ] Admin class oluşturdum (`app/admin/config.py`)
- [ ] `setup_admin` function'ına view ekledim
- [ ] Migration'da enum type'ları doğru oluşturdum
- [ ] Container restart edip admin UI'da test ettim

#### Enum Eklerken:
- [ ] `str, Enum` inheritance kullandım
- [ ] Model'de `SQLEnum` kullandım
- [ ] Migration'da enum type oluşturdım
- [ ] Admin UI'da dropdown olarak göründüğünü doğruladım

#### Admin Configuration Best Practices:
- [ ] `column_list` - Önemli alanları listele
- [ ] `column_searchable_list` - Arama yapılabilir text alanları
- [ ] `column_filters` - Enum ve boolean alanları
- [ ] `form_columns` - Form'da gösterilecek alanlar
- [ ] `can_create/edit/delete` - İzinleri uygun şekilde ayarla
- [ ] `name/name_plural/icon` - UI görünümü için

### Admin UI Testing Requirements

```python
# ✅ Admin UI enum test örneği
def test_admin_enum_dropdown():
    """Test that enum fields show as dropdowns in admin."""
    response = requests.get("http://localhost:8000/admin/my-model/create")
    
    # Enum field dropdown kontrolü
    assert 'select name="status"' in response.text
    assert 'option value="active"' in response.text
    assert 'option value="inactive"' in response.text
```

### Error Prevention Rules

#### ❌ Common Mistakes to Avoid:
```python
# String kullanımı - dropdown olmaz
status: Mapped[str] = mapped_column(String(20))

# Enum import etmemek
from sqlalchemy import Enum  # ❌ Wrong import

# Admin class'ı setup_admin'e eklememek
def setup_admin(...):
    # admin.add_view(MyModelAdmin)  # ❌ Commented out

# Migration'da enum type oluşturmamak
op.alter_column('table', 'enum_field',
               type_=sa.Enum(...))  # ❌ Type doesn't exist
```

#### ✅ Correct Patterns:
```python
# Doğru enum kullanımı
from sqlalchemy import Enum as SQLEnum
status: Mapped[MyEnum] = mapped_column(SQLEnum(MyEnum))

# Doğru admin setup
admin.add_view(MyModelAdmin)

# Doğru migration
op.execute("CREATE TYPE myenum AS ENUM (...)")
op.alter_column(..., type_=sa.Enum(..., name='myenum'))
```

Following these conventions will ensure consistent and maintainable code throughout the project. Cursor AI will also generate code that adheres to these standards.