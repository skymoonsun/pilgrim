"""Health check endpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.integrations.redis import ping_redis

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, str]:
    """Liveness probe — always returns healthy if the process is up."""
    return {"status": "healthy", "service": "Pilgrim", "version": "0.1.0"}


@router.get("/readiness")
async def readiness_check(
    session: AsyncSession = Depends(get_async_session),
) -> dict[str, str]:
    """Readiness probe — verifies DB and Redis connectivity."""
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        )

    try:
        await ping_redis()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="redis_unavailable",
        )

    return {"status": "ready"}


@router.get("/liveness")
async def liveness_check() -> dict[str, str]:
    """Lightweight liveness check (no I/O)."""
    return {"status": "alive"}
