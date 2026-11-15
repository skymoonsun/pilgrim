"""Proxy-pool logic tests against in-memory SQLite.

Covers ``ValidProxyService`` — the surface behind proxy rotation:

- ``get_random_healthy``: health filtering, protocol filtering,
  ``exclude_ids`` rotation semantics, empty pool → ``None``.
- TTL: ``delete_expired`` removes only proxies past ``expires_at``,
  leaving live and never-expiring (manual) rows alone.
- ``upsert_proxy``: counter bookkeeping on insert vs update.

Never touches PostgreSQL — the schema is replayed on
``sqlite+aiosqlite`` via the ``db_session`` fixture.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

from pytest import MonkeyPatch
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProxyHealthStatus, ProxyProtocol
from app.models.valid_proxy import ValidProxy
from app.services.valid_proxy_service import ValidProxyService

_UTC = UTC


def make_proxy(
    *,
    ip: str = "203.0.113.1",
    port: int = 8080,
    protocol: ProxyProtocol = ProxyProtocol.HTTP,
    health: ProxyHealthStatus = ProxyHealthStatus.HEALTHY,
    expires_at: datetime | None = None,
    **extra: Any,
) -> ValidProxy:
    """Build a detached pool row; the caller adds it to the session."""
    kwargs: dict[str, Any] = {
        "ip": ip,
        "port": port,
        "protocol": protocol,
        "health": health,
        "expires_at": expires_at,
    }
    kwargs.update(extra)
    return ValidProxy(**kwargs)


async def seed(session: AsyncSession, *proxies: ValidProxy) -> None:
    for proxy in proxies:
        session.add(proxy)
    await session.commit()


class TestGetRandomHealthy:
    async def test_only_healthy_rows_are_served(
        self, db_session: AsyncSession
    ) -> None:
        await seed(
            db_session,
            make_proxy(ip="203.0.113.10", health=ProxyHealthStatus.UNHEALTHY),
        )
        service = ValidProxyService(db_session)
        picked = await service.get_random_healthy()
        assert picked is None

    async def test_protocol_filter(
        self, db_session: AsyncSession
    ) -> None:
        await seed(
            db_session,
            make_proxy(ip="203.0.113.10", protocol=ProxyProtocol.HTTP),
            make_proxy(
                ip="203.0.113.11", protocol=ProxyProtocol.SOCKS5
            ),
        )
        service = ValidProxyService(db_session)

        socks = await service.get_random_healthy(ProxyProtocol.SOCKS5)
        assert socks is not None
        assert socks.protocol is ProxyProtocol.SOCKS5

        http = await service.get_random_healthy(ProxyProtocol.HTTP)
        assert http is not None
        assert http.protocol is ProxyProtocol.HTTP

    async def test_protocol_with_no_row_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        await seed(db_session, make_proxy(protocol=ProxyProtocol.HTTP))
        service = ValidProxyService(db_session)
        assert (
            await service.get_random_healthy(ProxyProtocol.SOCKS5) is None
        )

    async def test_exclude_ids_rotation_semantics(
        self, db_session: AsyncSession
    ) -> None:
        first = make_proxy(ip="203.0.113.10")
        second = make_proxy(ip="203.0.113.11", port=8081)
        await seed(db_session, first, second)
        service = ValidProxyService(db_session)

        # Retry that already failed on *first* must land on *second*.
        picked = await service.get_random_healthy(
            exclude_ids=[cast(UUID, first.id)],
        )
        assert picked is not None
        assert picked.id == second.id

    async def test_excluding_everything_exhausts_pool(
        self, db_session: AsyncSession
    ) -> None:
        only = make_proxy(ip="203.0.113.10")
        await seed(db_session, only)
        service = ValidProxyService(db_session)
        picked = await service.get_random_healthy(
            exclude_ids=[cast(UUID, only.id)]
        )
        assert picked is None

    async def test_empty_pool_returns_none(
        self, db_session: AsyncSession
    ) -> None:
        service = ValidProxyService(db_session)
        assert await service.get_random_healthy() is None

    async def test_served_row_is_healthy_among_many(
        self, db_session: AsyncSession, monkeypatch: MonkeyPatch
    ) -> None:
        # Deterministic random(): pin to index 0 so the query still runs.
        await seed(
            db_session,
            make_proxy(ip="203.0.113.10"),
            make_proxy(ip="203.0.113.11", health=ProxyHealthStatus.UNHEALTHY),
        )
        service = ValidProxyService(db_session)
        picked = await service.get_random_healthy()
        assert picked is not None
        assert picked.health is ProxyHealthStatus.HEALTHY


class TestDeleteExpired:
    async def test_only_past_expiry_rows_removed(
        self, db_session: AsyncSession
    ) -> None:
        expired = make_proxy(
            ip="203.0.113.10",
            expires_at=datetime.now(_UTC) - timedelta(minutes=1),
        )
        alive = make_proxy(
            ip="203.0.113.11",
            expires_at=datetime.now(_UTC) + timedelta(hours=1),
        )
        manual = make_proxy(ip="203.0.113.12", expires_at=None)
        await seed(db_session, expired, alive, manual)

        service = ValidProxyService(db_session)
        deleted = await service.delete_expired()

        assert deleted == 1
        remaining = list((await db_session.execute(
            ValidProxy.__table__.select()
        )).fetchall())
        surviving_ids = {row.id for row in remaining}
        assert surviving_ids == {alive.id, manual.id}

    async def test_expiring_in_this_instance_boundary(
        self, db_session: AsyncSession
    ) -> None:
        # expires_at < now is strict: an expiry set *after* now survives.
        row = make_proxy(
            ip="203.0.113.10",
            expires_at=datetime.now(_UTC) + timedelta(seconds=30),
        )
        await seed(db_session, row)

        service = ValidProxyService(db_session)
        assert await service.delete_expired() == 0
        assert await service.get_random_healthy() is not None


class TestUpsertProxy:
    async def test_first_insert_counts_as_healthy_check(
        self, db_session: AsyncSession
    ) -> None:
        service = ValidProxyService(db_session)
        proxy = await service.upsert_proxy(
            source_config_id=uuid4(),
            ip="203.0.113.10",
            port=8080,
            protocol=ProxyProtocol.HTTP,
            health=ProxyHealthStatus.HEALTHY,
        )
        assert proxy.success_count == 1
        assert proxy.failure_count == 0
        assert proxy.last_checked_at is not None
        assert proxy.last_success_at is not None

    async def test_second_insert_updates_same_row(
        self, db_session: AsyncSession
    ) -> None:
        service = ValidProxyService(db_session)
        source = uuid4()
        first = await service.upsert_proxy(
            source_config_id=source,
            ip="203.0.113.10",
            port=8080,
            protocol=ProxyProtocol.HTTP,
        )
        second = await service.upsert_proxy(
            source_config_id=source,
            ip="203.0.113.10",
            port=8080,
            protocol=ProxyProtocol.HTTP,
        )
        assert first.id == second.id
        assert second.success_count == 2

    async def test_unhealthy_update_increments_failures(
        self, db_session: AsyncSession
    ) -> None:
        service = ValidProxyService(db_session)
        source = uuid4()
        await service.upsert_proxy(
            source_config_id=source,
            ip="203.0.113.10",
            port=8080,
            protocol=ProxyProtocol.HTTP,
        )
        downgraded = await service.upsert_proxy(
            source_config_id=source,
            ip="203.0.113.10",
            port=8080,
            protocol=ProxyProtocol.HTTP,
            health=ProxyHealthStatus.UNHEALTHY,
        )
        assert downgraded.health is ProxyHealthStatus.UNHEALTHY
        assert downgraded.failure_count == 1
        assert downgraded.success_count == 1
