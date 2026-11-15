"""Auth gate tests — byte-realm pattern: login → JWT → protected mutations.

Full chain against the real ``app.main.app`` with the in-memory SQLite
session override; the gate itself (``authorize``) and every 401 branch run
for real.
"""

from collections.abc import AsyncIterator, Callable, Iterator
from datetime import UTC, datetime

import jwt as pyjwt
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    create_access_token,
    decode_access_token,
    generate_password,
    hash_password,
    verify_password,
)
from app.db.database import get_async_session
from app.main import app
from app.models.user import User

_PLAIN = "correct-horse-battery"


@pytest.fixture
def switch_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Callable[..., None]]:
    """Set env vars and (un)cache Settings, restoring defaults after."""

    def _set(**env: str) -> None:
        for key, value in env.items():
            monkeypatch.setenv(key, value)
        get_settings.cache_clear()

    yield _set
    get_settings.cache_clear()


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncIterator[AsyncClient]:
    """Async HTTP client over the real app with the SQLite session."""

    async def _override_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[get_async_session] = _override_session
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            yield async_client
    finally:
        app.dependency_overrides.pop(get_async_session, None)


@pytest.fixture
async def seeded_user(db_session: AsyncSession) -> AsyncIterator[User]:
    """User 'operator' hashed with a known password."""
    user = User(username="operator", password=hash_password(_PLAIN))
    db_session.add(user)
    await db_session.commit()
    yield user


class TestPasswordHashing:
    def test_scrypt_hash_roundtrip(self) -> None:
        hashed = hash_password(_PLAIN)
        assert hashed != _PLAIN
        assert hashed.startswith("$scrypt$")
        assert verify_password(_PLAIN, hashed)
        assert not verify_password("wrong", hashed)

    def test_generate_password_is_strong_entropy(self) -> None:
        token = generate_password()
        assert len(token) >= 20
        assert generate_password() != token


class TestTokenClaims:
    def test_roundtrip_preserves_claims(self) -> None:
        token = create_access_token(user_id="1111-2222", username="op")
        payload = decode_access_token(token)
        assert payload["sub"] == "1111-2222"
        assert payload["username"] == "op"
        exp = payload["exp"]
        iat = payload["iat"]
        assert isinstance(exp, int) and isinstance(iat, int)
        assert exp - iat == 3600

    def test_expired_token_rejected_at_decode(self) -> None:
        token = create_access_token(
            user_id="x", username="op", ttl_seconds=-10
        )
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)


class TestLogin:
    async def test_login_success_returns_token(
        self, client: AsyncClient, seeded_user: User
    ) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": _PLAIN},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert list(body) == ["token"]
        assert decode_access_token(body["token"])["sub"] == str(
            seeded_user.id
        )

    async def test_login_wrong_password_401(
        self, client: AsyncClient, seeded_user: User
    ) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": "wrong"},
        )
        assert resp.status_code == 401

    async def test_login_unknown_user_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "whatever"},
        )
        assert resp.status_code == 401

    async def test_login_validation_error(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post("/api/v1/auth/login", json={"username": "x"})
        assert resp.status_code == 422

    async def test_me_with_valid_token(
        self, client: AsyncClient, seeded_user: User
    ) -> None:
        token = create_access_token(
            user_id=str(seeded_user.id), username=seeded_user.username
        )
        resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body == {
            "id": str(seeded_user.id),
            "username": "operator",
            "is_active": True,
        }


class TestReadOpenGate:
    """Default mode: mutations need a token, reads stay public."""

    async def test_mutation_without_token_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/crawl-configs/", json={"name": "open-mode"}
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing bearer token"

    async def test_read_endpoints_stay_public(
        self, db_session: AsyncSession, client: AsyncClient
    ) -> None:
        from app.models.crawl_config import CrawlConfiguration

        db_session.add(CrawlConfiguration(name="listed"))
        await db_session.commit()
        resp = await client.get("/api/v1/crawl-configs/")
        assert resp.status_code == 200
        names = {item["name"] for item in resp.json()["items"]}
        assert "listed" in names

    async def test_login_token_grants_mutation(
        self, db_session: AsyncSession, client: AsyncClient, seeded_user: User
    ) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": _PLAIN},
        )
        token = login.json()["token"]
        resp = await client.post(
            "/api/v1/crawl-configs/",
            json={"name": "via-login"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201


class TestStrictGate:
    @pytest.fixture(autouse=True)
    def strict(self, switch_settings: Callable[..., None]) -> None:
        switch_settings(PILGRIM_AUTH_MODE="strict")

    async def test_get_without_token_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.get("/api/v1/crawl-configs/")
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Missing bearer token"

    async def test_post_without_token_401(
        self, client: AsyncClient
    ) -> None:
        resp = await client.post(
            "/api/v1/crawl-configs/", json={"name": "s"}
        )
        assert resp.status_code == 401

    async def test_invalid_token_401(self, client: AsyncClient) -> None:
        resp = await client.post(
            "/api/v1/crawl-configs/",
            json={"name": "s"},
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "Invalid or expired token"

    async def test_token_from_login_grants_mutation(
        self, client: AsyncClient, seeded_user: User
    ) -> None:
        login = await client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": _PLAIN},
        )
        token = login.json()["token"]
        resp = await client.post(
            "/api/v1/crawl-configs/",
            json={"name": "via-login"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 201

    async def test_login_stays_public_in_strict(
        self, client: AsyncClient, seeded_user: User
    ) -> None:
        resp = await client.post(
            "/api/v1/auth/login",
            json={"username": "operator", "password": _PLAIN},
        )
        assert resp.status_code == 200

    async def test_health_probes_exempt_in_strict(
        self, client: AsyncClient
    ) -> None:
        # /health/ is a no-IO probe; readiness would need real services.
        resp = await client.get("/api/v1/health/")
        assert resp.status_code == 200

    async def test_expired_token_401(self, client: AsyncClient) -> None:
        expired = create_access_token(
            user_id="00000000-0000-0000-0000-000000000000",
            username="x",
            ttl_seconds=-10,
        )
        resp = await client.get(
            "/api/v1/crawl-configs/",
            headers={"Authorization": f"Bearer {expired}"},
        )
        assert resp.status_code == 401

    async def test_unknown_user_token_401(
        self, client: AsyncClient
    ) -> None:
        ghost = create_access_token(
            user_id="00000000-0000-0000-0000-000000000000",
            username="ghost",
        )
        resp = await client.get(
            "/api/v1/crawl-configs/",
            headers={"Authorization": f"Bearer {ghost}"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "User not found"

    async def test_deactivated_user_token_401(
        self, db_session: AsyncSession, client: AsyncClient
    ) -> None:
        inactive = User(
            username="idler",
            password=hash_password("pw"),
            is_active=False,
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        db_session.add(inactive)
        await db_session.commit()
        token = create_access_token(
            user_id=str(inactive.id), username="idler"
        )
        resp = await client.get(
            "/api/v1/crawl-configs/",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 401
        assert resp.json()["detail"] == "User is deactivated"
