"""Rate limit tests — backend maths + endpoint 429 behaviour.

No real services: the endpoint client overrides the DB session with the
in-memory SQLite fixture and the Celery ``apply_async`` with a stub, while
the limiter runs on the ``memory`` backend via env-overridden settings.
"""

from collections.abc import AsyncIterator, Iterator
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import RateLimitExceededError
from app.core.rate_limit import (
    MemoryRateBackend,
    _memory_backends,
    rate_limit_scope,
    reset_memory_backends,
)
from app.core.security import create_access_token, hash_password
from app.db.database import get_async_session
from app.main import app
from app.models.user import User
from app.workers.tasks.scrape import run_crawl_job


@pytest.fixture(autouse=True)
def clean_counters() -> Iterator[None]:
    reset_memory_backends()
    yield
    reset_memory_backends()


@pytest.fixture
async def client(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncClient]:
    """Authenticated HTTP client (SQLite session + stubbed Celery).

    Reads are public but mutations sit behind the auth gate, so the
    limiter (which runs after the gate) is only reachable with a token.
    """

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    async def _fake_apply_async(*args: object, **kwargs: object) -> None:
        return None

    # Seeded operator + token for the gate.
    user = User(
        username="rate-limiter",
        password=hash_password("pw"),
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )
    db_session.add(user)
    await db_session.commit()

    token = create_access_token(user_id=str(user.id), username=user.username)
    headers = {"Authorization": f"Bearer {token}"}

    monkeypatch.setattr(run_crawl_job, "apply_async", _fake_apply_async)
    app.dependency_overrides[get_async_session] = _override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://test", headers=headers
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_async_session, None)


def fake_request(host: str = "testclient") -> SimpleNamespace:
    """Minimal ``Request`` stand-in: only ``client.host`` is consulted."""
    return SimpleNamespace(client=SimpleNamespace(host=host))


class TestMemoryBackend:
    async def test_allows_up_to_limit_then_blocks(self) -> None:
        backend = MemoryRateBackend(limit=3, window_seconds=60)
        assert await backend.hit("k") == 0
        assert await backend.hit("k") == 0
        assert await backend.hit("k") == 0
        retry = await backend.hit("k")
        assert retry > 0  # seconds until the window frees up

    async def test_keys_are_independent(self) -> None:
        backend = MemoryRateBackend(limit=1, window_seconds=60)
        assert await backend.hit("a") == 0
        assert await backend.hit("a") > 0
        assert await backend.hit("b") == 0

    async def test_window_slide_frees_slots(self) -> None:
        backend = MemoryRateBackend(limit=1, window_seconds=2)
        assert await backend.hit("k") == 0
        assert await backend.hit("k") > 0
        # Simulate the window passing by backdating the recorded hit.
        first = backend._hits["k"]
        first[0] -= 3
        assert await backend.hit("k") == 0

    async def test_retry_after_is_within_window(self) -> None:
        backend = MemoryRateBackend(limit=1, window_seconds=60)
        await backend.hit("k")
        retry = await backend.hit("k")
        assert 1 <= retry <= 60


class TestOffBackend:
    async def test_off_never_blocks_any_amount(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_BACKEND", "off")
        get_settings.cache_clear()
        try:
            dep = rate_limit_scope("scrape")
            for _ in range(10):
                await dep(fake_request())
        finally:
            get_settings.cache_clear()


class TestDependency:
    async def test_dep_raises_app_exception_after_cap(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_BACKEND", "memory")
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_LIMIT", "2")
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_WINDOW_SECONDS", "60")
        get_settings.cache_clear()
        try:
            dep = rate_limit_scope("pytest")
            request = fake_request()
            await dep(request)
            await dep(request)
            with pytest.raises(RateLimitExceededError) as excinfo:
                await dep(request)
            assert excinfo.value.retry_after > 0
            assert "pytest" in str(excinfo.value)
        finally:
            get_settings.cache_clear()

    async def test_dep_keys_by_client_ip(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_BACKEND", "memory")
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_LIMIT", "1")
        monkeypatch.setenv("PILGRIM_RATE_LIMIT_WINDOW_SECONDS", "60")
        get_settings.cache_clear()
        try:
            dep = rate_limit_scope("pytest-ip")
            await dep(fake_request("203.0.113.9"))
            await dep(fake_request("203.0.113.10"))
            backend = _memory_backends[(1, 60)]
            assert set(backend._hits) == {
                "pytest-ip:203.0.113.9",
                "pytest-ip:203.0.113.10",
            }
        finally:
            get_settings.cache_clear()


@pytest.fixture
def capped_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[None]:
    monkeypatch.setenv("PILGRIM_RATE_LIMIT_BACKEND", "memory")
    monkeypatch.setenv("PILGRIM_SCRAPE_CACHE_BACKEND", "memory")
    monkeypatch.setenv("PILGRIM_RATE_LIMIT_LIMIT", "1")
    monkeypatch.setenv("PILGRIM_RATE_LIMIT_WINDOW_SECONDS", "60")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


class TestScrapeEndpoint:
    async def test_429_after_limit(
        self, capped_settings: Iterator[None], client: AsyncClient
    ) -> None:
        body = {
            "config_id": "00000000-0000-0000-0000-000000000000",
            "url": "https://example.com/page",
        }
        first = await client.post("/api/v1/scrape/", json=body)
        assert first.status_code == 404  # config missing, but gate passed
        second = await client.post("/api/v1/scrape/", json=body)
        assert second.status_code == 429
        assert second.json()["error"]["code"] == "RATE_LIMIT_EXCEEDED"
        assert int(second.headers["Retry-After"]) > 0


class TestCrawlEndpoint:
    async def test_429_after_limit(
        self, capped_settings: Iterator[None], client: AsyncClient
    ) -> None:
        body = {
            "config_id": "00000000-0000-0000-0000-000000000000",
            "url": "https://example.com/page",
        }
        first = await client.post("/api/v1/crawl/jobs", json=body)
        # 404 (missing config) — the request reached the handler, i.e. it
        # passed the gate *and* the limiter; a 202 needs a real config row.
        assert first.status_code == 404
        second = await client.post("/api/v1/crawl/jobs", json=body)
        assert second.status_code == 429

    async def test_budget_is_scoped_per_bucket(
        self, capped_settings: Iterator[None], client: AsyncClient
    ) -> None:
        """Spending the scrape budget does not consume the crawl budget."""
        scrape_body = {
            "config_id": "00000000-0000-0000-0000-000000000000",
            "url": "https://example.com/a",
        }
        await client.post("/api/v1/scrape/", json=scrape_body)
        blocked = await client.post("/api/v1/scrape/", json=scrape_body)
        assert blocked.status_code == 429

        crawl_body = {
            "config_id": "00000000-0000-0000-0000-000000000000",
            "url": "https://example.com/b",
        }
        fresh = await client.post("/api/v1/crawl/jobs", json=crawl_body)
        # Reached its handler (own budget untouched by the scrape hits).
        assert fresh.status_code == 404
