---
trigger: glob
globs: "app/api/**/*.py"
description: "Pilgrim service: api-design — segment 1/3. Mirrors .cursor/rules/api-design.mdc."
---

# Pilgrim — api design (part 1/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/api-design.mdc`.

# API Design Guidelines - Pilgrim Service

Control plane: **FastAPI** + **PostgreSQL**. Execution: **Celery** workers + **Redis**. Enqueue work from the API; poll **crawl job** rows for authoritative status.

## 1. FastAPI Project Structure

### API Organization
```python
# File: app/api/__init__.py
"""API package initialization."""

# File: app/api/deps.py
"""Common dependencies for API endpoints."""
from typing import AsyncGenerator
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.database import get_async_session
from app.core.security import verify_jwt_token

security = HTTPBearer()

async def get_current_user(
    token: str = Depends(security),
    session: AsyncSession = Depends(get_async_session)
) -> dict:
    """Get current authenticated user."""
    try:
        payload = verify_jwt_token(token.credentials)
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid authentication credentials"
            )
        return {"user_id": user_id, "permissions": payload.get("permissions", [])}
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials"
        )

async def get_admin_user(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Require admin permissions."""
    if "admin" not in current_user.get("permissions", []):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin permissions required"
        )
    return current_user
```

### Router Structure
```python
# File: app/api/v1/__init__.py
from fastapi import APIRouter
from .endpoints import (
    auth,
    crawl,
    crawl_configs,
    datafeed,
    games,
    health,
    schedules,
    stores,
    tasks,
)

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["authentication"])
api_router.include_router(games.router, prefix="/games", tags=["games"])
api_router.include_router(stores.router, prefix="/stores", tags=["stores"])
api_router.include_router(crawl_configs.router, prefix="/crawl-configs", tags=["crawl-configs"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(crawl.router, prefix="/crawl", tags=["crawling"])
api_router.include_router(tasks.router, prefix="/tasks", tags=["celery-tasks"])
api_router.include_router(datafeed.router, prefix="/datafeed", tags=["data-feeds"])
api_router.include_router(health.router, prefix="/health", tags=["health"])
```

## 2. RESTful API Design Patterns

### Games API Endpoints
```python
# File: app/api/v1/endpoints/games.py
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session, get_current_user
from app.schemas.game import (
    GameResponse, GameCreate, GameUpdate, GameListResponse,
    GamePriceResponse, GameSearchQuery
)
from app.services.game_service import GameService
from app.core.pagination import PaginationParams, paginate

router = APIRouter()

@router.get("/", response_model=GameListResponse)
async def get_games(
    pagination: PaginationParams = Depends(),
    search: Optional[str] = Query(None, description="Search in game titles"),
    genre: Optional[str] = Query(None, description="Filter by genre"),
    developer: Optional[str] = Query(None, description="Filter by developer"),
    store_id: Optional[int] = Query(None, description="Filter games available in store"),
    min_price: Optional[float] = Query(None, ge=0, description="Minimum price filter"),
    max_price: Optional[float] = Query(None, ge=0, description="Maximum price filter"),
    session: AsyncSession = Depends(get_async_session)
) -> GameListResponse:
    """
    Get games with optional filtering and pagination.
    
    - **search**: Search term for game titles (supports partial matching)
    - **genre**: Filter by game genre
    - **developer**: Filter by game developer
    - **store_id**: Show only games available in specific store
    - **min_price/max_price**: Price range filtering
    """
    game_service = GameService(session)
    
    search_params = GameSearchQuery(
        search=search,
        genre=genre,
        developer=developer,
        store_id=store_id,
        min_price=min_price,
        max_price=max_price
    )
    
    games, total = await game_service.search_games(
        search_params=search_params,
        skip=pagination.skip,
        limit=pagination.limit
    )
    
    return GameListResponse(
        items=[GameResponse.model_validate(game) for game in games],
        total=total,
        page=pagination.page,
        per_page=pagination.limit,
        pages=(total + pagination.limit - 1) // pagination.limit
    )

@router.get("/{game_id}", response_model=GameResponse)
async def get_game(
    game_id: UUID = Path(..., description="Game unique identifier"),
    include_prices: bool = Query(False, description="Include current prices"),
    session: AsyncSession = Depends(get_async_session)
) -> GameResponse:
    """Get a specific game by ID."""
    game_service = GameService(session)
    
    game = await game_service.get_game_by_id(
        game_id=game_id, 
        include_prices=include_prices
    )
    
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with ID {game_id} not found"
        )
    
    return GameResponse.model_validate(game)

@router.post("/", status_code=status.HTTP_201_CREATED, response_model=GameResponse)
async def create_game(
    game_data: GameCreate,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user)
) -> GameResponse:
    """Create a new game entry."""
    game_service = GameService(session)
    
    try:
        game = await game_service.create_game(game_data)
        return GameResponse.model_validate(game)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

@router.put("/{game_id}", response_model=GameResponse)
async def update_game(
    game_id: UUID = Path(..., description="Game unique identifier"),
    game_data: GameUpdate = ...,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_current_user)
) -> GameResponse:
    """Update an existing game."""
    game_service = GameService(session)
    
    game = await game_service.update_game(game_id, game_data)
    if not game:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with ID {game_id} not found"
        )
    
    return GameResponse.model_validate(game)

@router.delete("/{game_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_game(
    game_id: UUID = Path(..., description="Game unique identifier"),
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_admin_user)
) -> None:
    """Delete a game (admin only)."""
    game_service = GameService(session)
    
    success = await game_service.delete_game(game_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Game with ID {game_id} not found"
        )

@router.get("/{game_id}/prices", response_model=list[GamePriceResponse])
async def get_game_prices(
    game_id: UUID = Path(..., description="Game unique identifier"),
    store_id: Optional[int] = Query(None, description="Filter by store"),
    only_in_stock: bool = Query(True, description="Show only in-stock items"),
    session: AsyncSession = Depends(get_async_session)
) -> list[GamePriceResponse]:
    """Get current prices for a game across all stores."""
    game_service = GameService(session)
    
    prices = await game_service.get_game_prices(
        game_id=game_id,
        store_id=store_id,
        only_in_stock=only_in_stock
    )
    
    return [GamePriceResponse.model_validate(price) for price in prices]

@router.get("/{game_id}/price-history")
async def get_price_history(
    game_id: UUID = Path(..., description="Game unique identifier"),
    store_id: Optional[int] = Query(None, description="Filter by store"),
    days: int = Query(30, ge=1, le=365, description="Number of days of history"),
    session: AsyncSession = Depends(get_async_session)
):
    """Get price history for a game."""
    game_service = GameService(session)
    
    history = await game_service.get_price_history(
        game_id=game_id,
        store_id=store_id,
        days=days
    )
    
    return {"game_id": game_id, "history": history}
```

### Stores API Endpoints
```python
# File: app/api/v1/endpoints/stores.py
@router.get("/", response_model=list[StoreResponse])
async def get_stores(
    active_only: bool = Query(True, description="Show only active stores"),
    country_code: Optional[str] = Query(None, description="Filter by country"),
    session: AsyncSession = Depends(get_async_session)
) -> list[StoreResponse]:
    """Get all stores with optional filtering."""
    store_service = StoreService(session)
    
    stores = await store_service.get_stores(
        active_only=active_only,
        country_code=country_code
    )
    
    return [StoreResponse.model_validate(store) for store in stores]

@router.post("/{store_id}/crawl-config", status_code=status.HTTP_201_CREATED)
async def create_crawl_config(
    store_id: int = Path(..., description="Store ID"),
    config_data: CrawlConfigCreate = ...,
    session: AsyncSession = Depends(get_async_session),
    current_user: dict = Depends(get_admin_user)
):
    """Create crawling configuration for a store."""
    crawl_service = CrawlConfigService(session)
    
    config = await crawl_service.create_config(store_id, config_data)
    return {"message": "Crawl configuration created", "config_id": config.id}
```

