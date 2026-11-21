"""Two-proxy rotation-in-effect proof: exclusion-based selection sequence.

The rotation policy is *exclusion-based random selection* — not
round-robin: each attempt draws a random healthy proxy (weighted by
recent success), the already-tried proxy ID(s) are excluded, and a
fresh draw therefore lands on a *different* proxy until the pool is
exhausted.  These tests pin that ordering contract down with exactly
two seeded proxies, where every step is deterministic:

1. excluding one proxy always selects the other (single-candidate path);
2. a rotation-driven fetch over the real ``ValidProxyService`` closure
   visits both proxies, in order, and never retries the failed one;
3. once the two-proxy pool is exhausted the fetch falls back to direct.
"""

from collections.abc import Collection
from typing import Any, cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enums import ProxyHealthStatus, ProxyProtocol, ScraperProfile
from app.models.valid_proxy import ValidProxy
from app.services.proxy_rotation import (
    ProxyRotationReport,
    fetch_with_proxy_rotation,
    proxy_label,
)
from app.services.valid_proxy_service import ValidProxyService

_PROXIES: tuple[tuple[str, int], ...] = (
    ("203.0.113.10", 8080),
    ("203.0.113.11", 8081),
)


def _pid(proxy: ValidProxy) -> UUID:
    """``proxy.id`` as plain ``uuid.UUID``.

    UUIDMixin annotates ``id`` with SQLAlchemy's UUID sqltype, so the
    raw attribute fails mypy's ``Collection[UUID]`` args — cast the
    runtime value once here.
    """
    return cast(UUID, proxy.id)


@pytest.fixture
async def two_proxies(db_session: AsyncSession) -> list[ValidProxy]:
    """Exactly two healthy, never-checked (weight-neutral) proxies."""
    proxies = [
        ValidProxy(
            ip=ip,
            port=port,
            protocol=ProxyProtocol.HTTP,
            health=ProxyHealthStatus.HEALTHY,
            success_count=0,
            failure_count=0,
        )
        for ip, port in _PROXIES
    ]
    db_session.add_all(proxies)
    await db_session.commit()
    return proxies


class TestTwoProxySelection:
    async def test_excluding_one_healthy_proxy_always_selects_the_other(
        self, db_session: AsyncSession, two_proxies: list[ValidProxy]
    ) -> None:
        """A retry must land on the *other* proxy — both directions."""
        service = ValidProxyService(db_session)
        first, second = two_proxies

        for excluded, expected in ((first, second), (second, first)):
            got = await service.get_random_healthy(exclude_ids={_pid(excluded)})
            assert got is not None
            assert got.id == expected.id
            assert (got.ip, got.port) == (expected.ip, expected.port)

        # Both excluded → pool is dry; rotation falls back to direct.
        assert (
            await service.get_random_healthy(
                exclude_ids={_pid(first), _pid(second)}
            )
            is None
        )

    async def test_rotation_sequence_visits_both_proxies_in_order(
        self, db_session: AsyncSession, two_proxies: list[ValidProxy]
    ) -> None:
        """A proxied fetch walks first-pick → fail → other-pick → success.

        Uses the same ``select_proxy`` closure the worker builds: the
        raw ``fetch`` call always fails on its first invocation and
        succeeds on the second.  Whichever proxy is drawn first, the
        report must show exactly two attempts with two *distinct*
        proxies (the failed one is excluded from the retry), the second
        one succeeding.
        """
        service = ValidProxyService(db_session)

        async def select_proxy(
            tried: Collection[UUID],
        ) -> ValidProxy | None:
            return await service.get_random_healthy(exclude_ids=tried)

        calls: list[int] = []
        sentinel: dict[str, Any] = {}

        def fetch(_kwargs: dict[str, Any]) -> dict[str, Any]:
            calls.append(1)
            if len(calls) == 1:
                message = "connection refused through first proxy"
                raise RuntimeError(message)
            return sentinel

        report = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=select_proxy,
            profile=ScraperProfile.FETCHER,
            max_attempts=3,
            report=report,
        )

        assert response is sentinel
        assert len(calls) == 2  # second attempt succeeded; no direct fetch
        assert not report.fell_back_direct
        assert report.fallback_reason is None

        ok_flags = [entry.ok for entry in report.attempts]
        assert ok_flags == [False, True]
        assert report.attempts[0].error is not None
        assert report.attempts[1].error is None

        # The retry hit a *different* proxy — the exclusion contract.
        attempted = [entry.proxy for entry in report.attempts]
        assert attempted[0] != attempted[1]
        assert set(attempted) == {proxy_label(p) for p in two_proxies}
        assert report.used_proxy == report.attempts[1].proxy

    async def test_exhausted_two_proxy_pool_falls_back_to_direct(
        self, db_session: AsyncSession, two_proxies: list[ValidProxy]
    ) -> None:
        """Both proxies failing: report keeps the story, fetch goes direct.

        Both exhaustion flavours are pinned: a spent retry budget with
        the pool still offering proxies reports
        ``all_proxy_attempts_failed``, exhausting the *pool* mid-budget
        reports ``no_healthy_proxy_available``.
        """
        service = ValidProxyService(db_session)

        async def select_proxy(
            tried: Collection[UUID],
        ) -> ValidProxy | None:
            return await service.get_random_healthy(exclude_ids=tried)

        direct_sentinel: dict[str, Any] = {}

        def fetch(kwargs: dict[str, Any]) -> dict[str, Any]:
            if "proxy" in kwargs:
                message = "both proxies refuse"
                raise RuntimeError(message)
            return direct_sentinel

        # Budget 2 == pool size: every attempt went to a proxy, both
        # failed → "all_proxy_attempts_failed" then the direct fetch.
        spent = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=select_proxy,
            profile=ScraperProfile.FETCHER,
            max_attempts=2,
            report=spent,
        )

        assert response == direct_sentinel
        assert spent.fell_back_direct
        assert spent.fallback_reason == "all_proxy_attempts_failed"
        assert [entry.ok for entry in spent.attempts] == [False, False]
        assert {entry.proxy for entry in spent.attempts} == {
            proxy_label(p) for p in two_proxies
        }

        # Budget 3 > pool size: the third select finds nothing → the
        # loop breaks early with "no_healthy_proxy_available".
        dry = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=select_proxy,
            profile=ScraperProfile.FETCHER,
            max_attempts=3,
            report=dry,
        )

        assert response == direct_sentinel
        assert dry.fell_back_direct
        assert dry.fallback_reason == "no_healthy_proxy_available"
        assert len(dry.attempts) == 2
