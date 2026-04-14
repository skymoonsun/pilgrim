---
trigger: glob
globs: "tests/**/*"
description: "Pilgrim service: testing-guidelines — segment 2/4. Mirrors .cursor/rules/testing-guidelines.mdc."
---

# Pilgrim — testing guidelines (part 2/4)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/testing-guidelines.mdc`.

## 3. Integration Testing

### API Endpoint Testing
```python
# File: tests/integration/test_api/test_games_endpoints.py
import pytest
from httpx import AsyncClient
from fastapi import status
from uuid import uuid4

from tests.utils.auth import create_test_token

class TestGamesAPI:
    """Integration tests for Games API endpoints."""
    
    @pytest.fixture
    def auth_headers(self):
        """Create authentication headers for tests."""
        token = create_test_token(user_id="test-user", permissions=["read", "write"])
        return {"Authorization": f"Bearer {token}"}
    
    @pytest.fixture
    def admin_headers(self):
        """Create admin authentication headers."""
        token = create_test_token(user_id="admin-user", permissions=["admin"])
        return {"Authorization": f"Bearer {token}"}
    
    async def test_get_games_success(self, async_client: AsyncClient, test_data):
        """Test successful games retrieval."""
        response = await async_client.get("/api/v1/games/")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert len(data["items"]) > 0
    
    async def test_get_games_with_filters(self, async_client: AsyncClient, test_data):
        """Test games retrieval with search filters."""
        response = await async_client.get(
            "/api/v1/games/",
            params={
                "search": "Test",
                "min_price": 10.0,
                "max_price": 50.0
            }
        )
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        for game in data["items"]:
            assert "Test" in game["title"]
    
    async def test_get_game_by_id_success(self, async_client: AsyncClient, test_data):
        """Test successful game retrieval by ID."""
        game_id = str(test_data["games"][0].id)
        
        response = await async_client.get(f"/api/v1/games/{game_id}")
        
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        
        assert data["id"] == game_id
        assert "title" in data
        assert "created_at" in data
    
    async def test_get_game_by_id_not_found(self, async_client: AsyncClient):
        """Test game not found response."""
        non_existent_id = str(uuid4())
        
        response = await async_client.get(f"/api/v1/games/{non_existent_id}")
        
        assert response.status_code == status.HTTP_404_NOT_FOUND
        data = response.json()
        
        assert data["error"]["code"] == "GAME_NOT_FOUND"
    
    async def test_create_game_success(self, async_client: AsyncClient, auth_headers):
        """Test successful game creation."""
        game_data = {
            "title": "New Test Game",
            "description": "A new game for testing",
            "developer": "Test Developer",
            "steam_app_id": 99999
        }
        
        response = await async_client.post(
            "/api/v1/games/",
            json=game_data,
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_201_CREATED
        data = response.json()
        
        assert data["title"] == game_data["title"]
        assert data["steam_app_id"] == game_data["steam_app_id"]
        assert "id" in data
    
    async def test_create_game_unauthorized(self, async_client: AsyncClient):
        """Test game creation without authentication."""
        game_data = {
            "title": "Unauthorized Game",
            "developer": "Test Developer"
        }
        
        response = await async_client.post("/api/v1/games/", json=game_data)
        
        assert response.status_code == status.HTTP_401_UNAUTHORIZED
    
    async def test_create_game_validation_error(self, async_client: AsyncClient, auth_headers):
        """Test game creation with invalid data."""
        invalid_data = {
            "title": "",  # Empty title should fail validation
            "steam_app_id": "not-a-number"  # Invalid type
        }
        
        response = await async_client.post(
            "/api/v1/games/",
            json=invalid_data,
            headers=auth_headers
        )
        
        assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
        data = response.json()
        
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "details" in data["error"]
    
    async def test_delete_game_admin_only(self, async_client: AsyncClient, admin_headers, test_data):
        """Test game deletion requires admin permissions."""
        game_id = str(test_data["games"][0].id)
        
        response = await async_client.delete(
            f"/api/v1/games/{game_id}",
            headers=admin_headers
        )
        
        assert response.status_code == status.HTTP_204_NO_CONTENT
        
        # Verify game is deleted
        get_response = await async_client.get(f"/api/v1/games/{game_id}")
        assert get_response.status_code == status.HTTP_404_NOT_FOUND
```

### Database Integration Testing
```python
# File: tests/integration/test_database/test_game_repository.py
import pytest
from sqlalchemy import select
from app.models.game import Game
from app.models.price import GamePrice
from tests.utils.factories import GameFactory, GamePriceFactory

class TestGameRepository:
    """Integration tests for game database operations."""
    
    async def test_game_creation_with_relationships(self, async_session):
        """Test creating game with related prices."""
        # Create game
        game = await GameFactory.create(session=async_session)
        
        # Create related prices
        price1 = await GamePriceFactory.create(
            session=async_session,
            game_id=game.id,
            store_id=1,
            price=Decimal("19.99")
        )
        price2 = await GamePriceFactory.create(
            session=async_session,
            game_id=game.id,
            store_id=2,
            price=Decimal("24.99")
        )
        
        await async_session.commit()
        
        # Verify relationships
        result = await async_session.execute(
            select(Game).where(Game.id == game.id)
        )
        retrieved_game = result.scalar_one()
        
        assert len(retrieved_game.prices) == 2
        assert retrieved_game.prices[0].price in [Decimal("19.99"), Decimal("24.99")]
    
    async def test_game_search_performance(self, async_session, test_data):
        """Test game search query performance."""
        import time
        
        start_time = time.time()
        
        # Execute complex search query
        result = await async_session.execute(
            select(Game)
            .join(GamePrice)
            .where(
                Game.title.ilike("%Test%"),
                GamePrice.price < Decimal("50.00"),
                GamePrice.in_stock == True
            )
            .limit(10)
        )
        
        games = result.scalars().all()
        execution_time = time.time() - start_time
        
        # Performance assertion (should complete within 100ms)
        assert execution_time < 0.1
        assert len(games) >= 0  # Verify query executes successfully
    
    async def test_cascade_delete(self, async_session):
        """Test that deleting game cascades to prices."""
        # Create game with prices
        game = await GameFactory.create(session=async_session)
        price = await GamePriceFactory.create(
            session=async_session,
            game_id=game.id
        )
        
        await async_session.commit()
        
        # Delete game
        await async_session.delete(game)
        await async_session.commit()
        
        # Verify price is also deleted
        result = await async_session.execute(
            select(GamePrice).where(GamePrice.id == price.id)
        )
        assert result.scalar_one_or_none() is None
```

