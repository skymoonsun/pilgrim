---
trigger: glob
globs: "**/*.py"
description: "Pilgrim service: code-conventions — segment 2/3. Mirrors .cursor/rules/code-conventions.mdc."
---

# Pilgrim — code conventions (part 2/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/code-conventions.mdc`.

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

