"""IP-based rate limiting for the scrape-trigger endpoints.

Self-written (no new dependency): a fastapi dependency factory that counts
hits per ``bucket:client-ip`` inside the configured window and raises
``RateLimitExceededError`` (→ HTTP 429 with ``Retry-After``) once the cap
is reached.

Backends (``PILGRIM_RATE_LIMIT_BACKEND``):
- ``redis``  — fixed-window INCR/EXPIRE counters shared by every uvicorn
  worker.  Fail-open: if Redis errors, requests pass (a probe must not
  take the scraper down).
- ``memory`` — per-process sliding window; for tests and Redis-less runs.
- ``off``    — disabled entirely.
"""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Any

from fastapi import Request

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError

logger = logging.getLogger(__name__)


class RateBackend(ABC):
    """Abstract counter backend. ``hit`` returns 0 when allowed."""

    @abstractmethod
    async def hit(self, key: str) -> int:
        """Consume one slot for *key*.

        Returns ``0`` when the request is allowed, otherwise the number of
        seconds until the caller should retry.
        """


class MemoryRateBackend(RateBackend):
    """Sliding-window counters kept in process memory."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def hit(self, key: str) -> int:
        now = time.monotonic()
        window = self._hits[key]
        cutoff = now - self.window
        while window and window[0] <= cutoff:
            window.popleft()
        if len(window) >= self.limit:
            retry = int(round(window[0] + self.window - now))
            return max(retry, 1)
        window.append(now)
        return 0

    def reset(self) -> None:
        """Clear all counters (test helper)."""
        self._hits.clear()


class RedisRateBackend(RateBackend):
    """Fixed-window counter shared via Redis (``INCR`` + ``EXPIRE``)."""

    def __init__(self, limit: int, window_seconds: int) -> None:
        self.limit = limit
        self.window = window_seconds

    def _key(self, key: str) -> str:
        return f"rl:{key}:{self.window}"

    async def hit(self, key: str) -> int:
        from app.integrations.redis import get_redis

        client = get_redis()
        redis_key = self._key(key)
        try:
            count = int(await client.incr(redis_key))
            if count == 1:
                await client.expire(redis_key, self.window)
        except Exception as exc:  # noqa: BLE001 — fail-open on any Redis error
            logger.warning(
                "Rate-limit backend unavailable (fail-open): %s", exc
            )
            return 0

        if count > self.limit:
            try:
                ttl = int(await client.ttl(redis_key))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Rate-limit TTL read failed: %s", exc)
                ttl = self.window
            return max(ttl, 1)
        return 0


class NoopRateBackend(RateBackend):
    """Disabled backend — every request passes."""

    async def hit(self, key: str) -> int:
        return 0


_NOOP = NoopRateBackend()

# One sliding-window table per (limit, window) so changing settings via env
# in tests still lands on a shared, resettable instance per shape.
_memory_backends: dict[tuple[int, int], MemoryRateBackend] = {}


def _select_backend(limit: int, window_seconds: int) -> RateBackend:
    settings = get_settings()
    if settings.rate_limit_backend == "off":
        return _NOOP
    if settings.rate_limit_backend == "memory":
        backend = _memory_backends.get((limit, window_seconds))
        if backend is None:
            backend = MemoryRateBackend(limit, window_seconds)
            _memory_backends[(limit, window_seconds)] = backend
        return backend
    return RedisRateBackend(limit, window_seconds)


def reset_memory_backends() -> None:
    """Reset every in-process counter (test helper)."""
    for backend in _memory_backends.values():
        backend.reset()


def rate_limit_scope(bucket: str) -> Callable[..., Any]:
    """Return a FastAPI dependency that rate-limits by client IP.

    *bucket* separates independent budgets (e.g. ``scrape`` vs ``crawl``)
    so the sync playground and async job queue do not exhaust each other.
    """

    async def _dep(request: Request) -> None:
        settings = get_settings()
        limit = settings.rate_limit_limit
        window = settings.rate_limit_window_seconds
        client_ip = request.client.host if request.client else "unknown"
        backend = _select_backend(limit, window)
        retry_after = await backend.hit(f"{bucket}:{client_ip}")
        if retry_after > 0:
            raise RateLimitExceededError(bucket, retry_after)

    return _dep
