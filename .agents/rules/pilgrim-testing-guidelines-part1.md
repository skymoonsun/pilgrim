---
trigger: glob
globs: "tests/**/*"
description: "Pilgrim service: testing-guidelines — segment 1/4. Mirrors .cursor/rules/testing-guidelines.mdc."
---

# Pilgrim — testing guidelines (part 1/4)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/testing-guidelines.mdc`.

# Testing Guidelines - Pilgrim Service

FastAPI tests use **async** fixtures and **httpx.AsyncClient**. Crawling runs in **Celery workers** — do not assert Scrapling in API tests unless using **eager** mode or a **worker test** target.

## 1. Test Project Structure

### Test Organization
```
tests/
├── conftest.py                    # Pytest configuration and fixtures
├── unit/                         # Unit tests
│   ├── test_services/
│   │   ├── test_game_service.py
│   │   ├── test_crawl_service.py
│   │   └── test_auth_service.py
│   ├── test_utils/
│   │   ├── test_price_utils.py
│   │   └── test_validators.py
│   └── test_models/
│       ├── test_game_models.py
│       └── test_price_models.py
├── integration/                  # Integration tests
│   ├── test_api/
│   │   ├── test_games_endpoints.py
│   │   ├── test_stores_endpoints.py
│   │   └── test_auth_endpoints.py
│   ├── test_database/
│   │   ├── test_game_repository.py
│   │   └── test_price_repository.py
│   └── test_crawling/
│       ├── test_steam_scraper.py
│       └── test_epic_scraper.py
│   ├── test_workers/
│   │   ├── test_crawl_tasks.py   # Celery task unit tests (mock Scrapling)
│   │   └── test_beat_enqueue.py
│   └── test_redis/
│       └── test_proxy_pool.py
├── e2e/                          # End-to-end tests
│   ├── test_crawl_workflow.py
│   └── test_price_update_flow.py
└── fixtures/                     # Test data fixtures
    ├── games.json
    ├── stores.json
    └── html_responses/
        ├── steam_game_page.html
        └── epic_game_page.html
```

### Core Test Configuration
```python
# File: tests/conftest.py
import asyncio
import pytest
import pytest_asyncio
from typing import AsyncGenerator, Generator
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import get_settings
from app.db.database import get_async_session
from app.main import app
from app.models.base import Base
from tests.utils.test_data import create_test_data

# Test database URL
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()

@pytest_asyncio.fixture
async def async_engine():
    """Create async test database engine."""
    engine = create_async_engine(
        TEST_DATABASE_URL,
        poolclass=StaticPool,
        connect_args={
            "check_same_thread": False,
        },
        echo=False,  # Set to True for SQL debugging
    )
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    
    yield engine
    
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    
    await engine.dispose()

@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncGenerator[AsyncSession, None]:
    """Create async test database session."""
    async_session_maker = sessionmaker(
        async_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    async with async_session_maker() as session:
        yield session

@pytest_asyncio.fixture
async def async_client(async_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Create async test client with database dependency override."""
    def get_test_session():
        return async_session
    
    app.dependency_overrides[get_async_session] = get_test_session
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client
    
    app.dependency_overrides.clear()

@pytest_asyncio.fixture
async def test_data(async_session: AsyncSession):
    """Create test data in the database."""
    return await create_test_data(async_session)
```

## 2. Unit Testing Patterns

### Service Layer Testing
```python
# File: tests/unit/test_services/test_game_service.py
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from decimal import Decimal

from app.services.game_service import GameService, GameNotFoundError
from app.schemas.game import GameCreate, GameSearchQuery
from app.models.game import Game
from tests.utils.factories import GameFactory, GamePriceFactory

class TestGameService:
    """Test cases for GameService."""
    
    @pytest_asyncio.fixture
    async def game_service(self, async_session):
        """Create GameService instance with test session."""
        return GameService(session=async_session)
    
    @pytest.fixture
    def sample_game_data(self):
        """Sample game data for testing."""
        return GameCreate(
            title="Test Game",
            description="A test game for unit testing",
            developer="Test Developer",
            publisher="Test Publisher",
            steam_app_id=12345
        )
    
    async def test_create_game_success(self, game_service, sample_game_data):
        """Test successful game creation."""
        # Act
        game = await game_service.create_game(sample_game_data)
        
        # Assert
        assert game.title == sample_game_data.title
        assert game.developer == sample_game_data.developer
        assert game.steam_app_id == sample_game_data.steam_app_id
        assert game.id is not None
        assert game.created_at is not None
    
    async def test_create_game_duplicate_steam_id(self, game_service, sample_game_data, test_data):
        """Test creating game with duplicate Steam ID raises error."""
        # Arrange - Create a game with same Steam ID
        existing_game = await GameFactory.create(steam_app_id=sample_game_data.steam_app_id)
        
        # Act & Assert
        with pytest.raises(ValueError, match="Steam App ID already exists"):
            await game_service.create_game(sample_game_data)
    
    async def test_get_game_by_id_success(self, game_service, test_data):
        """Test successful game retrieval by ID."""
        # Arrange
        game_id = test_data["games"][0].id
        
        # Act
        game = await game_service.get_game_by_id(game_id, include_prices=True)
        
        # Assert
        assert game is not None
        assert game.id == game_id
        assert hasattr(game, 'prices')  # Prices should be loaded
    
    async def test_get_game_by_id_not_found(self, game_service):
        """Test game not found scenario."""
        # Arrange
        non_existent_id = uuid4()
        
        # Act & Assert
        with pytest.raises(GameNotFoundError):
            await game_service.get_game_by_id(non_existent_id)
    
    async def test_search_games_by_title(self, game_service, test_data):
        """Test game search by title."""
        # Arrange
        search_params = GameSearchQuery(search="Test")
        
        # Act
        games, total = await game_service.search_games(
            search_params=search_params,
            skip=0,
            limit=10
        )
        
        # Assert
        assert total > 0
        assert len(games) > 0
        assert all("Test" in game.title for game in games)
    
    async def test_search_games_with_price_filter(self, game_service, test_data):
        """Test game search with price filters."""
        # Arrange
        search_params = GameSearchQuery(
            min_price=10.0,
            max_price=50.0
        )
        
        # Act
        games, total = await game_service.search_games(
            search_params=search_params,
            skip=0,
            limit=10
        )
        
        # Assert
        for game in games:
            if game.prices:
                assert any(
                    Decimal('10.0') <= price.price <= Decimal('50.0') 
                    for price in game.prices
                )
    
    @patch('app.services.game_service.logger')
    async def test_create_game_database_error(self, mock_logger, game_service, sample_game_data):
        """Test game creation with database error."""
        # Arrange
        with patch.object(game_service.session, 'commit', side_effect=Exception("DB Error")):
            # Act & Assert
            with pytest.raises(Exception):
                await game_service.create_game(sample_game_data)
            
            # Verify rollback was called
            mock_logger.error.assert_called()
```

### Utility Function Testing
```python
# File: tests/unit/test_utils/test_price_utils.py
import pytest
from decimal import Decimal
from app.utils.price_utils import (
    clean_price_text, 
    convert_currency, 
    calculate_discount_percentage,
    parse_turkish_price
)

class TestPriceUtils:
    """Test cases for price utility functions."""
    
    @pytest.mark.parametrize("input_text,expected", [
        ("$19.99", "19.99"),
        ("€25,00", "25.00"),
        ("₺29,99", "29.99"),
        ("19.99 TL", "19.99"),
        ("FREE", "0.00"),
        ("N/A", None),
        ("", None),
    ])
    def test_clean_price_text(self, input_text, expected):
        """Test price text cleaning with various formats."""
        result = clean_price_text(input_text)
        
        if expected is None:
            assert result is None
        else:
            assert result == Decimal(expected)
    
    def test_parse_turkish_price_formats(self):
        """Test Turkish price format parsing."""
        test_cases = [
            ("29,99 ₺", Decimal("29.99")),
            ("1.299,99 TL", Decimal("1299.99")),
            ("₺ 45,50", Decimal("45.50")),
            ("2.500,00 TL", Decimal("2500.00")),
        ]
        
        for input_text, expected in test_cases:
            result = parse_turkish_price(input_text)
            assert result == expected
    
    def test_calculate_discount_percentage(self):
        """Test discount percentage calculation."""
        original = Decimal("100.00")
        discounted = Decimal("75.00")
        
        result = calculate_discount_percentage(original, discounted)
        
        assert result == Decimal("25.00")
    
    def test_calculate_discount_percentage_no_discount(self):
        """Test discount calculation when no discount exists."""
        original = Decimal("50.00")
        discounted = Decimal("50.00")
        
        result = calculate_discount_percentage(original, discounted)
        
        assert result == Decimal("0.00")
    
    async def test_convert_currency_success(self):
        """Test currency conversion with mocked exchange rates."""
        with patch('app.utils.price_utils.get_exchange_rate') as mock_rate:
            mock_rate.return_value = Decimal("0.85")
            
            result = await convert_currency(
                amount=Decimal("100.00"),
                from_currency="USD",
                to_currency="EUR"
            )
            
            assert result == Decimal("85.00")
```

