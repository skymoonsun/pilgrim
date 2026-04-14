"""Redis client wrapper for health checks, locks, and caching."""

from __future__ import annotations

import redis.asyncio as aioredis

from app.core.config import get_settings

_pool: aioredis.ConnectionPool | None = None


def _get_pool() -> aioredis.ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = aioredis.ConnectionPool.from_url(
            str(settings.redis_url),
            decode_responses=True,
        )
    return _pool


def get_redis() -> aioredis.Redis:
    """Return an async Redis client backed by a shared connection pool."""
    return aioredis.Redis(connection_pool=_get_pool())


async def ping_redis() -> bool:
    """Ping Redis — raises on failure.  Used by health endpoints."""
    client = get_redis()
    return await client.ping()
