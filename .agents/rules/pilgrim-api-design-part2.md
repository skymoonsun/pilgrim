---
trigger: glob
globs: "app/api/**/*.py"
description: "Pilgrim service: api-design — segment 2/3. Mirrors .cursor/rules/api-design.mdc."
---

# Pilgrim — api design (part 2/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/api-design.mdc`.

## 3. Error Handling Patterns

### Custom Exception Handlers
```python
# File: app/core/exceptions.py
"""Custom exceptions for the application."""

class AppException(Exception):
    """Base application exception."""
    def __init__(self, message: str, code: str = None):
        self.message = message
        self.code = code
        super().__init__(self.message)

class GameNotFoundError(AppException):
    """Raised when a game is not found."""
    def __init__(self, game_id: str):
        super().__init__(f"Game with ID {game_id} not found", "GAME_NOT_FOUND")

class DuplicateGameError(AppException):
    """Raised when trying to create a duplicate game."""
    def __init__(self, identifier: str):
        super().__init__(f"Game with identifier {identifier} already exists", "DUPLICATE_GAME")

class InvalidPriceError(AppException):
    """Raised when price data is invalid."""
    def __init__(self, message: str):
        super().__init__(f"Invalid price data: {message}", "INVALID_PRICE")

class CrawlingError(AppException):
    """Raised when crawling operations fail."""
    def __init__(self, url: str, reason: str):
        super().__init__(f"Failed to crawl {url}: {reason}", "CRAWLING_ERROR")

class RateLimitExceededError(AppException):
    """Raised when rate limits are exceeded."""
    def __init__(self, store_name: str, retry_after: int):
        super().__init__(
            f"Rate limit exceeded for {store_name}. Retry after {retry_after} seconds", 
            "RATE_LIMIT_EXCEEDED"
        )
        self.retry_after = retry_after
```

### Global Exception Handler
```python
# File: app/core/error_handlers.py
from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError
import logging

logger = logging.getLogger(__name__)

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle custom application exceptions."""
    logger.error(f"Application error: {exc.message}", extra={"code": exc.code})
    
    status_map = {
        "GAME_NOT_FOUND": status.HTTP_404_NOT_FOUND,
        "DUPLICATE_GAME": status.HTTP_409_CONFLICT,
        "INVALID_PRICE": status.HTTP_400_BAD_REQUEST,
        "CRAWLING_ERROR": status.HTTP_502_BAD_GATEWAY,
        "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
    }
    
    response_status = status_map.get(exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    response_data = {
        "error": {
            "code": exc.code,
            "message": exc.message,
            "type": "application_error"
        }
    }
    
    # Add retry_after header for rate limiting
    headers = {}
    if hasattr(exc, 'retry_after'):
        headers["Retry-After"] = str(exc.retry_after)
    
    return JSONResponse(
        status_code=response_status,
        content=response_data,
        headers=headers
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handle request validation errors."""
    logger.warning(f"Validation error: {exc.errors()}")
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "type": "validation_error",
                "details": exc.errors()
            }
        }
    )

async def database_exception_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    """Handle database integrity errors."""
    logger.error(f"Database integrity error: {str(exc)}")
    
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "DATABASE_CONSTRAINT_ERROR",
                "message": "Database constraint violation",
                "type": "database_error"
            }
        }
    )

async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error(f"Unexpected error: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "type": "server_error"
            }
        }
    )
```

## 4. Authentication & Authorization

### JWT Authentication
```python
# File: app/core/security.py
from datetime import datetime, timedelta
from typing import Optional
import jwt
from passlib.context import CryptContext
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def create_access_token(
    data: dict, 
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create JWT access token."""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.jwt_expire_minutes)
    
    to_encode.update({"exp": expire, "iat": datetime.utcnow()})
    
    return jwt.encode(
        to_encode, 
        settings.secret_key, 
        algorithm=settings.jwt_algorithm
    )

def verify_jwt_token(token: str) -> dict:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(
            token, 
            settings.secret_key, 
            algorithms=[settings.jwt_algorithm]
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token"
        )

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify password against hash."""
    return pwd_context.verify(plain_password, hashed_password)

def hash_password(password: str) -> str:
    """Hash password."""
    return pwd_context.hash(password)
```

### Auth Endpoints
```python
# File: app/api/v1/endpoints/auth.py
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.schemas.auth import Token, UserCreate, UserResponse
from app.services.auth_service import AuthService
from app.core.security import create_access_token

router = APIRouter()

@router.post("/login", response_model=Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_async_session)
) -> Token:
    """Login and get access token."""
    auth_service = AuthService(session)
    
    user = await auth_service.authenticate_user(
        email=form_data.username,
        password=form_data.password
    )
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    access_token_expires = timedelta(minutes=settings.jwt_expire_minutes)
    access_token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "permissions": user.permissions
        },
        expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=settings.jwt_expire_minutes * 60
    )

@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserResponse)
async def register(
    user_data: UserCreate,
    session: AsyncSession = Depends(get_async_session)
) -> UserResponse:
    """Register a new user."""
    auth_service = AuthService(session)
    
    user = await auth_service.create_user(user_data)
    return UserResponse.model_validate(user)
```

