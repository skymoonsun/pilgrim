---
trigger: glob
globs: "tests/**/*"
description: "Pilgrim service: testing-guidelines — segment 3/4. Mirrors .cursor/rules/testing-guidelines.mdc."
---

# Pilgrim — testing guidelines (part 3/4)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/testing-guidelines.mdc`.

## 4. External Service Mocking

### HTTP Mocking for Scraping
```python
# File: tests/integration/test_crawling/test_steam_scraper.py
import pytest
from unittest.mock import patch, AsyncMock
import httpx
from httpx import Response

from app.services.crawl_service import SteamScraper
from tests.fixtures.html_responses import STEAM_GAME_PAGE_HTML

class TestSteamScraper:
    """Test Steam scraping functionality with mocked HTTP responses."""
    
    @pytest.fixture
    def steam_scraper(self):
        """Create SteamScraper instance."""
        return SteamScraper()
    
    @pytest.fixture
    def mock_steam_response(self):
        """Mock Steam page response."""
        return STEAM_GAME_PAGE_HTML
    
    async def test_scrape_steam_game_success(self, steam_scraper, mock_steam_response):
        """Test successful Steam game scraping."""
        with patch('httpx.AsyncClient.get') as mock_get:
            # Setup mock response
            mock_response = AsyncMock(spec=Response)
            mock_response.text = mock_steam_response
            mock_response.url.path = "/app/123456"
            mock_response.status_code = 200
            mock_get.return_value = mock_response
            
            # Execute scraping
            result = await steam_scraper.scrape_game_page(
                "https://store.steampowered.com/app/123456"
            )
            
            # Verify results
            assert result.title == "Test Game"
            assert result.price == Decimal("19.99")
            assert result.currency == "USD"
            assert result.in_stock is True
            
            # Verify HTTP call was made
            mock_get.assert_called_once()
    
    async def test_scrape_steam_age_verification(self, steam_scraper):
        """Test Steam age verification handling."""
        with patch('httpx.AsyncClient.get') as mock_get, \
             patch('httpx.AsyncClient.post') as mock_post:
            
            # First response - age verification
            age_response = AsyncMock(spec=Response)
            age_response.url.path = "/agecheck/app/123456"
            age_response.text = "<html>Age verification required</html>"
            
            # Second response - actual game page
            game_response = AsyncMock(spec=Response)
            game_response.url.path = "/app/123456"
            game_response.text = STEAM_GAME_PAGE_HTML
            
            mock_get.side_effect = [age_response, game_response]
            mock_post.return_value = AsyncMock()
            
            # Execute scraping
            result = await steam_scraper.scrape_game_page(
                "https://store.steampowered.com/app/123456"
            )
            
            # Verify age verification was handled
            assert mock_post.called
            assert result.title == "Test Game"
    
    async def test_scrape_steam_rate_limited(self, steam_scraper):
        """Test handling of rate limiting."""
        with patch('httpx.AsyncClient.get') as mock_get:
            # Setup rate limit response
            mock_response = AsyncMock(spec=Response)
            mock_response.status_code = 429
            mock_response.headers = {"Retry-After": "60"}
            mock_get.side_effect = httpx.HTTPStatusError(
                "Rate limited", 
                request=AsyncMock(), 
                response=mock_response
            )
            
            # Execute and verify exception
            with pytest.raises(httpx.HTTPStatusError) as exc_info:
                await steam_scraper.scrape_game_page(
                    "https://store.steampowered.com/app/123456"
                )
            
            assert exc_info.value.response.status_code == 429
```

### Database Transaction Testing
```python
# File: tests/integration/test_database/test_transactions.py
import pytest
from sqlalchemy.exc import IntegrityError
from app.services.game_service import GameService
from app.schemas.game import GameCreate

class TestDatabaseTransactions:
    """Test database transaction handling."""
    
    async def test_rollback_on_constraint_violation(self, async_session):
        """Test that transactions rollback on constraint violations."""
        game_service = GameService(async_session)
        
        # Create first game
        game_data1 = GameCreate(
            title="Test Game 1",
            steam_app_id=12345
        )
        await game_service.create_game(game_data1)
        
        # Try to create second game with same Steam ID
        game_data2 = GameCreate(
            title="Test Game 2",
            steam_app_id=12345  # Duplicate Steam ID
        )
        
        # Should raise constraint violation
        with pytest.raises(ValueError):
            await game_service.create_game(game_data2)
        
        # Verify session is still usable
        game_data3 = GameCreate(
            title="Test Game 3",
            steam_app_id=54321  # Different Steam ID
        )
        
        # This should succeed
        game3 = await game_service.create_game(game_data3)
        assert game3.title == "Test Game 3"
```

## 5. End-to-End Testing

### Full Workflow Testing
```python
# File: tests/e2e/test_crawl_workflow.py
import pytest
from unittest.mock import patch
from httpx import AsyncClient

from tests.utils.mock_responses import MockHTTPResponses

class TestCrawlWorkflow:
    """End-to-end tests for crawling workflow."""
    
    @pytest.fixture
    def mock_responses(self):
        """Setup mock HTTP responses for different stores."""
        return MockHTTPResponses()
    
    async def test_complete_crawl_workflow(
        self, 
        async_client: AsyncClient, 
        admin_headers, 
        test_data,
        mock_responses
    ):
        """Test complete crawling workflow from trigger to completion."""
        
        # Step 1: Trigger crawl job
        crawl_request = {
            "store_ids": [1, 2],
            "game_urls": [
                "https://store.steampowered.com/app/123456",
                "https://www.epicgames.com/store/game/test-game"
            ]
        }
        
        with patch('httpx.AsyncClient.get', side_effect=mock_responses.get_response):
            response = await async_client.post(
                "/api/v1/crawl/trigger",
                json=crawl_request,
                headers=admin_headers
            )
        
        assert response.status_code == 202
        job_data = response.json()
        job_id = job_data["job_id"]
        
        # Step 2: Check job status
        status_response = await async_client.get(
            f"/api/v1/crawl/jobs/{job_id}",
            headers=admin_headers
        )
        
        assert status_response.status_code == 200
        status_data = status_response.json()
        assert status_data["status"] in ["running", "completed"]
        
        # Step 3: Verify prices were updated
        games_response = await async_client.get("/api/v1/games/")
        games_data = games_response.json()
        
        # Verify at least one game has updated prices
        updated_games = [
            game for game in games_data["items"] 
            if game.get("last_price_update") is not None
        ]
        assert len(updated_games) > 0
```

## 6. Test Utilities and Factories

### Test Data Factories
```python
# File: tests/utils/factories.py
import factory
from decimal import Decimal
from datetime import datetime
from factory import Faker, LazyAttribute
from app.models.game import Game
from app.models.price import GamePrice
from app.models.store import Store

class GameFactory(factory.Factory):
    """Factory for creating test games."""
    
    class Meta:
        model = Game
    
    title = Faker('name')
    description = Faker('text', max_nb_chars=200)
    developer = Faker('company')
    publisher = Faker('company')
    steam_app_id = Faker('random_int', min=100000, max=999999)
    is_active = True
    quality_score = Decimal('0.85')
    
    @classmethod
    async def create(cls, session=None, **kwargs):
        """Create and save game to database."""
        game = cls.build(**kwargs)
        if session:
            session.add(game)
            await session.commit()
            await session.refresh(game)
        return game

class StoreFactory(factory.Factory):
    """Factory for creating test stores."""
    
    class Meta:
        model = Store
    
    name = Faker('company')
    display_name = LazyAttribute(lambda obj: obj.name)
    base_url = Faker('url')
    is_active = True
    store_type = 'web'
    max_requests_per_hour = 100
    min_delay_seconds = Decimal('1.0')
    
    @classmethod
    async def create(cls, session=None, **kwargs):
        """Create and save store to database."""
        store = cls.build(**kwargs)
        if session:
            session.add(store)
            await session.commit()
            await session.refresh(store)
        return store

class GamePriceFactory(factory.Factory):
    """Factory for creating test game prices."""
    
    class Meta:
        model = GamePrice
    
    price = Faker('pydecimal', left_digits=3, right_digits=2, positive=True)
    currency_id = 1  # Default to USD
    in_stock = True
    product_url = Faker('url')
    is_stale = False
    
    @classmethod
    async def create(cls, session=None, **kwargs):
        """Create and save game price to database."""
        price = cls.build(**kwargs)
        if session:
            session.add(price)
            await session.commit()
            await session.refresh(price)
        return price
```

### Mock Response Utilities
```python
# File: tests/utils/mock_responses.py
from typing import Dict, Any
import json

class MockHTTPResponses:
    """Utility for managing mock HTTP responses."""
    
    def __init__(self):
        self.responses = {
            "store.steampowered.com": self._steam_response,
            "epicgames.com": self._epic_response,
        }
    
    def get_response(self, url: str) -> Dict[str, Any]:
        """Get mock response for URL."""
        for domain, response_func in self.responses.items():
            if domain in url:
                return response_func(url)
        
        # Default response
        return {
            "status_code": 404,
            "text": "<html>Not Found</html>"
        }
    
    def _steam_response(self, url: str) -> Dict[str, Any]:
        """Mock Steam response."""
        return {
            "status_code": 200,
            "text": """
                <html>
                    <div class="game_purchase_price">$19.99</div>
                    <div class="apphub_AppName">Test Game</div>
                    <div class="discount_percent">-25%</div>
                </html>
            """
        }
    
    def _epic_response(self, url: str) -> Dict[str, Any]:
        """Mock Epic Games response."""
        return {
            "status_code": 200,
            "text": """
                <html>
                    <div data-testid="price-display">€24.99</div>
                    <h1 data-testid="hero-title">Epic Test Game</h1>
                </html>
            """
        }
```

