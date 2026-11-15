"""Scrape response cache tests — endpoint level with the memory backend.

The real service is stubbed (a counter) so the tests prove pure cache
semantics: first call executes, same (config_id, url) replay hits the cache
with ``cached: true``, errors are never cached, different URL/config
creates a separate entry, and TTL expiry forces a refetch.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.db.database import get_async_session
from app.integrations.cache import (
    MemoryJsonCache,
    get_scrape_cache,
    reset_memory_cache,
    scrape_cache_key,
)
from app.main import app
from app.models.user import User
from app.schemas.crawl import ScrapeResponse
from app.services.scrape_service import ScrapeService

_URL = "https://example.com/page"
_CFG = "00000000-0000-0000-0000-000000000001"
_CFG2 = "00000000-0000-0000-0000-000000000002"


@pytest.fixture(autouse=True)
def clean_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("PILGRIM_SCRAPE_CACHE_BACKEND", "memory")
    monkeypatch.setenv("PILGRIM_SCRAPE_CACHE_TTL_SECONDS", "600")
    get_settings.cache_clear()
    reset_memory_cache()
    yield
    reset_memory_cache()
    get_settings.cache_clear()


@pytest.fixture
async def client_and_calls(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[AsyncClient, list[tuple[str, str]]]]:
    """HTTP client with SQLite session + counted ScrapeService stub."""
    calls: list[tuple[str, str]] = []

    async def fake_execute(
        self: ScrapeService, *, config_id: UUID, url: str
    ) -> ScrapeResponse:
        calls.append((str(config_id), url))
        return ScrapeResponse(
            config_id=config_id,
            url=url,
            http_status=200,
            data={"title": f"payload-{len(calls)}"},
        )

    monkeypatch.setattr(ScrapeService, "execute", fake_execute)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    # POST /scrape sits behind the auth gate — seed operator + token.
    user = User(
        username="cache-operator",
        password=hash_password("pw"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()
    token = create_access_token(user_id=str(user.id), username=user.username)

    app.dependency_overrides[get_async_session] = _override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport,
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as async_client:
            yield async_client, calls
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.fixture
async def client(
    client_and_calls: tuple[AsyncClient, list[tuple[str, str]]],
) -> AsyncIterator[AsyncClient]:
    yield client_and_calls[0]


async def post_scrape(client: AsyncClient, **overrides: str) -> Any:
    body: dict[str, str] = {"config_id": _CFG, "url": _URL}
    body.update(overrides)
    return await client.post("/api/v1/scrape/", json=body)


class TestScrapeCache:
    async def test_first_call_executes_second_is_cached(
        self, client_and_calls: tuple[AsyncClient, list[tuple[str, str]]]
    ) -> None:
        client, calls = client_and_calls
        first = await post_scrape(client)
        assert first.status_code == 200
        assert first.json()["data"] == {"title": "payload-1"}
        assert first.json()["cached"] is False

        second = await post_scrape(client)
        assert second.status_code == 200
        body = second.json()
        assert body["cached"] is True
        assert body["data"] == {"title": "payload-1"}  # same payload replays
        assert calls == [(_CFG, _URL)]  # executed exactly once

    async def test_different_url_is_separate_entry(
        self, client: AsyncClient
    ) -> None:
        await post_scrape(client)
        other = await post_scrape(client, url="https://example.com/other")
        assert other.json()["data"] == {"title": "payload-2"}
        assert other.json()["cached"] is False

    async def test_different_config_is_separate_entry(
        self, client: AsyncClient
    ) -> None:
        await post_scrape(client)
        other = await post_scrape(client, config_id=_CFG2)
        assert other.json()["data"] == {"title": "payload-2"}
        assert other.json()["cached"] is False

    async def test_errors_are_not_cached(
        self, client: AsyncClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def failing_execute(
            self: ScrapeService, *, config_id: UUID, url: str
        ) -> ScrapeResponse:
            return ScrapeResponse(
                config_id=config_id, url=url, error="Fetch error: boom"
            )

        monkeypatch.setattr(ScrapeService, "execute", failing_execute)
        first = await post_scrape(client)
        assert first.json()["cached"] is False
        second = await post_scrape(client)
        assert second.json()["cached"] is False

    async def test_ttl_expiry_forces_refetch(
        self, client_and_calls: tuple[AsyncClient, list[tuple[str, str]]]
    ) -> None:
        client, calls = client_and_calls
        first = await post_scrape(client)
        assert first.json()["data"]["title"] == "payload-1"

        cache = get_scrape_cache()
        assert isinstance(cache, MemoryJsonCache)
        cache._store[scrape_cache_key(_CFG, _URL)] = (
            0.0,  # long expired on the monotonic clock
            {"config_id": _CFG, "url": _URL, "cached": False},
        )

        second = await post_scrape(client)
        assert second.json()["cached"] is False
        assert len(calls) == 2


class TestCacheKey:
    def test_key_separates_configs_and_urls(self) -> None:
        a = scrape_cache_key(_CFG, "https://a.example")
        b = scrape_cache_key(_CFG, "https://b.example")
        assert a != b
        assert scrape_cache_key(_CFG, _URL) == scrape_cache_key(_CFG, _URL)
        assert scrape_cache_key(_CFG, _URL) != scrape_cache_key(_CFG2, _URL)

    def test_key_hashes_raw_url(self) -> None:
        key = scrape_cache_key(_CFG, "https://x.example/p?token=secret")
        assert "token" not in key
