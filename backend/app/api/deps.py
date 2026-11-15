"""Shared FastAPI dependencies."""

from collections.abc import AsyncGenerator

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import authorize, get_current_user  # noqa: F401 — re-export
from app.db.database import get_async_session  # noqa: F401 — re-export

# Re-export for convenience so endpoints import from one place.
__all__ = ["get_async_session", "authorize", "get_current_user"]

