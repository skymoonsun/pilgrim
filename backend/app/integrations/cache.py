"""TTL JSON cache used by the scrape endpoints.

Caches responses keyed by ``(config_id, url)`` so repeatedly asking for
the same recipe+URL within the TTL skips the real fetch.  Backends
(``PILGRIM_SCRAPE_CACHE_BACKEND``):

- ``redis``  — shared across process restarts and uvicorn workers.
  Fail-open: Redis errors are logged and every caller proceeds as before.
- ``memory`` — per-process dict with monotonic expiry (tests, Redis-less).
- ``off``    — disabled (``PILGRIM_SCRAPE_CACHE_TTL_SECONDS=0`` disables
  too).
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from app.core.config import get_settings

logger = logging.getLogger(__name__)

# Cap for the per-process memory cache: 2048 (config_id, url) responses is
# ample for a single-operator deployment yet bounds worst-case memory use.
MAX_MEMORY_CACHE_ENTRIES = 2048


class JsonCache(ABC):
    """Abstract TTL cache of JSON-serializable values."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Return the cached value for *key* or ``None``."""

    @abstractmethod
    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        """Store *value* under *key* for *ttl_seconds*."""


class MemoryJsonCache(JsonCache):
    """In-process cache with monotonic-clock expiry.

    Bounded: at most ``max_entries`` keys are kept (FIFO eviction of the
    oldest-inserted entries once the cap is hit) so a wide-open
    config/url space cannot grow memory without limit (each key maps to a
    cached response payload).  Redis has its own ``maxmemory`` policy;
    the in-process backend needs this cap instead.
    """

    def __init__(self, max_entries: int = MAX_MEMORY_CACHE_ENTRIES) -> None:
        self._store: dict[str, tuple[float, Any]] = {}
        self._max_entries = max_entries

    async def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        self._store.pop(key, None)  # re-insert ⇒ refreshed eviction order
        self._store[key] = (time.monotonic() + ttl_seconds, value)
        while len(self._store) > self._max_entries:
            oldest = next(iter(self._store))
            self._store.pop(oldest, None)

    def reset(self) -> None:
        """Drop the whole cache (test helper)."""
        self._store.clear()


class RedisJsonCache(JsonCache):
    """Redis-backed cache; every error is swallowed (fail-open)."""

    def __init__(self) -> None:
        from app.integrations.redis import get_redis

        self._client = get_redis()

    async def get(self, key: str) -> Any | None:
        try:
            raw = await self._client.get(key)
        except Exception as exc:  # noqa: BLE001 — cache must never break I/O
            logger.warning("Scrape cache read failed (fail-open): %s", exc)
            return None
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Scrape cache held invalid JSON for %s", key)
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int) -> None:
        try:
            await self._client.set(key, json.dumps(value), ex=ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Scrape cache write failed (fail-open): %s", exc)


_memory_cache: MemoryJsonCache | None = None


def get_scrape_cache() -> JsonCache | None:
    """Return the configured cache backend, or ``None`` when disabled."""
    settings = get_settings()
    backend = settings.scrape_cache_backend
    if backend == "off" or settings.scrape_cache_ttl_seconds == 0:
        return None
    if backend == "memory":
        global _memory_cache
        if _memory_cache is None:
            _memory_cache = MemoryJsonCache()
        return _memory_cache
    try:
        return RedisJsonCache()
    except Exception as exc:  # noqa: BLE001 — no Redis ⇒ proceed uncached
        logger.warning("Scrape cache backend unavailable (fail-open): %s", exc)
        return None


def reset_memory_cache() -> None:
    """Reset the singleton memory cache (test helper)."""
    global _memory_cache
    if _memory_cache is not None:
        _memory_cache.reset()


def scrape_cache_key(config_id: str, url: str) -> str:
    """Cache key for a (config, url) pair; the URL is hashed, not raw."""
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()
    return f"scrape:resp:{config_id}:{digest}"
