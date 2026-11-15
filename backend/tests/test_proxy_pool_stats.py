"""Proxy pool polish tests — /proxies/stats payload + weighted selection."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProxyHealthStatus, ProxyProtocol
from app.models.valid_proxy import ValidProxy
from app.services.proxy_pool_stats import success_weight
from app.services.valid_proxy_service import ValidProxyService


def make_proxy(
    *,
    ip: str = "203.0.113.1",
    port: int = 8080,
    protocol: ProxyProtocol = ProxyProtocol.HTTP,
    health: ProxyHealthStatus = ProxyHealthStatus.HEALTHY,
    expires_at: datetime | None = None,
    **extra: object,
) -> ValidProxy:
    kwargs: dict[str, object] = {
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


class TestSuccessWeight:
    def test_full_success_proxy_wins(self) -> None:
        p = make_proxy(success_count=9, failure_count=1)
        assert success_weight(p) == pytest.approx(0.9)

    def test_unchecked_proxy_is_neutral(self) -> None:
        p = make_proxy(success_count=0, failure_count=0)
        assert success_weight(p) == 0.5

    def test_failure_only_proxy_keeps_floor(self) -> None:
        p = make_proxy(success_count=0, failure_count=50)
        assert success_weight(p) == pytest.approx(0.01)

    def test_zero_success_ratio_is_floored(self) -> None:
        p = make_proxy(success_count=0, failure_count=2)
        assert success_weight(p) > 0


class TestGetRandomHealthyWeighted:
    async def test_weighted_pick_prefers_successful_proxies(
        self, db_session: AsyncSession
    ) -> None:
        """100%-success proxy is picked ~always over 1%-floor survivor."""
        await seed(
            db_session,
            make_proxy(
                ip="203.0.113.10",
                success_count=100,
                failure_count=0,
                last_checked_at=datetime.now(UTC),
            ),
            make_proxy(
                ip="203.0.113.11",
                port=8081,
                success_count=0,
                failure_count=100,
                last_checked_at=datetime.now(UTC),
            ),
        )
        service = ValidProxyService(db_session)
        picks = [await service.get_random_healthy() for _ in range(20)]
        # 100 successes (weight 1.0) vs floor 0.01 ⇒ failing one ≈ 1% each.
        chosen_ips = []
        for picked in picks:
            assert picked is not None
            chosen_ips.append(picked.ip)
        assert "203.0.113.10" in set(chosen_ips)
        assert set(chosen_ips).issubset({"203.0.113.10", "203.0.113.11"})

    async def test_failure_only_survivor_still_selectable(
        self, db_session: AsyncSession
    ) -> None:
        await seed(
            db_session,
            make_proxy(
                ip="203.0.113.10",
                success_count=0,
                failure_count=7,
            ),
            make_proxy(
                ip="203.0.113.11",
                port=8081,
                success_count=0,
                failure_count=3,
            ),
        )
        service = ValidProxyService(db_session)
        picked = await service.get_random_healthy()
        assert picked is not None  # floor weight → never a dead pick


class TestPoolStats:
    async def test_counts_by_health_and_ttl_window(
        self, db_session: AsyncSession
    ) -> None:
        now = datetime.now(UTC)
        await seed(
            db_session,
            make_proxy(ip="203.0.113.10"),  # healthy, no TTL (manual)
            make_proxy(ip="203.0.113.11", health=ProxyHealthStatus.UNHEALTHY),
            make_proxy(
                ip="203.0.113.12",
                expires_at=now + timedelta(minutes=30),
            ),
            make_proxy(
                ip="203.0.113.13",
                expires_at=now + timedelta(hours=5),
            ),
            make_proxy(
                ip="203.0.113.14",
                expires_at=now - timedelta(minutes=5),  # already expired
            ),
        )
        service = ValidProxyService(db_session)
        stats = await service.get_pool_stats(ttl_window_seconds=3600)
        assert stats == {
            "total": 5,
            "healthy": 4,
            "unhealthy": 1,
            "expiring_soon": 1,  # 30-min row; 5h and expired rows excluded
            "ttl_window_seconds": 3600,
        }

    async def test_window_boundary_is_inclusive(
        self, db_session: AsyncSession
    ) -> None:
        now = datetime.now(UTC)
        await seed(
            db_session,
            make_proxy(
                ip="203.0.113.10",
                expires_at=now + timedelta(seconds=3600),
            ),
        )
        service = ValidProxyService(db_session)
        stats = await service.get_pool_stats(ttl_window_seconds=3600)
        assert stats["expiring_soon"] == 1

    async def test_empty_pool(self, db_session: AsyncSession) -> None:
        service = ValidProxyService(db_session)
        stats = await service.get_pool_stats()
        assert stats["total"] == 0
        assert stats["healthy"] == 0
        assert stats["unhealthy"] == 0
        assert stats["expiring_soon"] == 0

    async def test_weighted_selection_coexists_with_stats(
        self, db_session: AsyncSession
    ) -> None:
        await seed(
            db_session,
            make_proxy(ip="203.0.113.10", success_count=4, failure_count=1),
        )
        service = ValidProxyService(db_session)
        stats = await service.get_pool_stats()
        assert stats["healthy"] == 1
        picked = await service.get_random_healthy()
        assert picked is not None
        assert picked.ip == "203.0.113.10"
        assert picked.success_count == 4
