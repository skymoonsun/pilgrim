"""Unit tests for the pure proxy-rotation building blocks.

``app.services.proxy_rotation`` is intentionally free of Scrapling and
database imports, so these tests run entirely in memory.
"""

import json
from collections.abc import Collection
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.models.enums import ProxyProtocol, ScraperProfile
from app.models.valid_proxy import ValidProxy
from app.services.proxy_rotation import (
    DEFAULT_PROXY_ATTEMPTS,
    MAX_PROXY_ATTEMPTS,
    MIN_PROXY_ATTEMPTS,
    ProxyRotationReport,
    build_fetch_proxy_kwargs,
    fetch_with_proxy_rotation,
    proxy_label,
    resolve_proxy_attempts,
)


def make_proxy(**overrides: Any) -> ValidProxy:
    """Return an in-memory ValidProxy (never persisted to a database)."""
    kwargs: dict[str, Any] = {
        "id": uuid4(),
        "ip": "203.0.113.10",
        "port": 8080,
        "protocol": ProxyProtocol.HTTP,
        "username": None,
        "password": None,
    }
    kwargs.update(overrides)
    return ValidProxy(**kwargs)


class _StaticPool:
    """Fake ``select_proxy`` callable serving a fixed proxy list."""

    def __init__(self, proxies: list[ValidProxy]) -> None:
        self.proxies = proxies
        self.exclusion_calls: list[set[UUID]] = []

    async def __call__(self, exclude: Collection[UUID]) -> ValidProxy | None:
        self.exclusion_calls.append(set(exclude))
        for proxy in self.proxies:
            if proxy.id not in exclude:
                return proxy
        return None


class TestResolveProxyAttempts:
    def test_defaults_when_options_missing(self) -> None:
        assert resolve_proxy_attempts(None) == DEFAULT_PROXY_ATTEMPTS
        assert resolve_proxy_attempts({}) == DEFAULT_PROXY_ATTEMPTS

    def test_reads_proxy_retries(self) -> None:
        assert resolve_proxy_attempts({"proxy_retries": 2}) == 2

    def test_clamps_to_sane_range(self) -> None:
        assert resolve_proxy_attempts({"proxy_retries": 0}) == MIN_PROXY_ATTEMPTS
        assert resolve_proxy_attempts({"proxy_retries": 99}) == MAX_PROXY_ATTEMPTS

    def test_non_numeric_falls_back_to_default(self) -> None:
        assert (
            resolve_proxy_attempts({"proxy_retries": "many"}) == DEFAULT_PROXY_ATTEMPTS
        )


class TestProxyLabel:
    def test_plain_proxy_label(self) -> None:
        assert proxy_label(make_proxy()) == "http://203.0.113.10:8080"

    def test_masks_credentials(self) -> None:
        proxy = make_proxy(username="alice", password="s3cret")
        label = proxy_label(proxy)
        assert "203.0.113.10:8080" in label
        assert "alice" not in label
        assert "s3cret" not in label
        assert "authenticated" in label

    def test_respects_protocol(self) -> None:
        proxy = make_proxy(protocol=ProxyProtocol.SOCKS5)
        assert proxy_label(proxy) == "socks5://203.0.113.10:8080"


class TestBuildFetchProxyKwargs:
    def test_static_profile_uses_url_plus_auth_tuple(self) -> None:
        proxy = make_proxy(username="user", password="pass")
        kwargs = build_fetch_proxy_kwargs(proxy, ScraperProfile.FETCHER)
        assert kwargs == {
            "proxy": "http://203.0.113.10:8080",
            "proxy_auth": ("user", "pass"),
        }

    def test_static_profile_keeps_credentials_out_of_url(self) -> None:
        proxy = make_proxy(username="user", password="pass")
        kwargs = build_fetch_proxy_kwargs(proxy, ScraperProfile.FETCHER)
        assert "user:pass" not in kwargs["proxy"]

    def test_static_profile_without_credentials(self) -> None:
        kwargs = build_fetch_proxy_kwargs(make_proxy(), ScraperProfile.HTTP_SESSION)
        assert kwargs == {"proxy": "http://203.0.113.10:8080"}

    def test_spider_profile_is_static(self) -> None:
        kwargs = build_fetch_proxy_kwargs(make_proxy(), ScraperProfile.SPIDER)
        assert kwargs == {"proxy": "http://203.0.113.10:8080"}

    def test_browser_profile_uses_server_dict(self) -> None:
        proxy = make_proxy(
            protocol=ProxyProtocol.SOCKS5, username="user", password="pass"
        )
        kwargs = build_fetch_proxy_kwargs(proxy, ScraperProfile.STEALTH)
        assert kwargs == {
            "proxy": {
                "server": "socks5://203.0.113.10:8080",
                "username": "user",
                "password": "pass",
            }
        }

    def test_browser_profile_only_allows_scrapling_keys(self) -> None:
        kwargs = build_fetch_proxy_kwargs(
            make_proxy(username="user", password="pass"),
            ScraperProfile.DYNAMIC,
        )
        assert set(kwargs["proxy"]) == {"server", "username", "password"}

    def test_browser_profile_without_credentials(self) -> None:
        kwargs = build_fetch_proxy_kwargs(make_proxy(), ScraperProfile.DYNAMIC)
        assert kwargs == {"proxy": {"server": "http://203.0.113.10:8080"}}


class TestFetchWithProxyRotation:
    async def test_first_proxy_succeeds(self) -> None:
        proxy = make_proxy()
        seen_kwargs: list[dict] = []

        def fetch(kwargs: dict) -> str:
            seen_kwargs.append(kwargs)
            return "response"

        pool = _StaticPool([proxy])
        report = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=pool,
            profile=ScraperProfile.FETCHER,
            max_attempts=3,
            report=report,
        )

        assert response == "response"
        assert report.used_proxy == "http://203.0.113.10:8080"
        assert report.fell_back_direct is False
        assert [entry.ok for entry in report.attempts] == [True]
        assert seen_kwargs == [{"proxy": "http://203.0.113.10:8080"}]

    async def test_rotates_to_a_different_proxy_on_failure(self) -> None:
        first = make_proxy(ip="203.0.113.1")
        second = make_proxy(ip="203.0.113.2")
        fetch_urls: list[str] = []

        def fetch(kwargs: dict) -> str:
            fetch_urls.append(kwargs["proxy"])
            if kwargs["proxy"] == "http://203.0.113.1:8080":
                raise ConnectionError("proxy timed out")
            return "ok"

        pool = _StaticPool([first, second])
        report = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=pool,
            profile=ScraperProfile.FETCHER,
            max_attempts=3,
            report=report,
        )

        assert response == "ok"
        assert fetch_urls == [
            "http://203.0.113.1:8080",
            "http://203.0.113.2:8080",
        ]
        # The failed proxy must be excluded from the retry selection.
        assert pool.exclusion_calls[1] == {first.id}
        assert report.used_proxy == "http://203.0.113.2:8080"
        assert [entry.ok for entry in report.attempts] == [False, True]
        assert report.attempts[0].error == "proxy timed out"
        assert report.fell_back_direct is False

    async def test_empty_pool_falls_back_to_direct(self) -> None:
        async def select_proxy(exclude: Collection[UUID]) -> None:
            return None

        report = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=lambda kwargs: "direct-ok",
            select_proxy=select_proxy,
            profile=ScraperProfile.FETCHER,
            max_attempts=3,
            report=report,
        )

        assert response == "direct-ok"
        assert report.fell_back_direct is True
        assert report.fallback_reason == "no_healthy_proxy_available"
        assert report.attempts == []
        assert report.used_proxy is None

    async def test_exhausted_pool_falls_back_to_direct(self) -> None:
        only_proxy = make_proxy()

        def fetch(kwargs: dict) -> str:
            if kwargs:
                raise ConnectionError("proxy unreachable")
            return "direct-ok"

        pool = _StaticPool([only_proxy])
        report = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=pool,
            profile=ScraperProfile.FETCHER,
            max_attempts=3,
            report=report,
        )

        assert response == "direct-ok"
        assert report.fell_back_direct is True
        assert report.fallback_reason == "no_healthy_proxy_available"
        assert len(report.attempts) == 1
        assert report.attempts[0].ok is False

    async def test_all_proxy_attempts_failed_falls_back_to_direct(
        self,
    ) -> None:
        proxies = [make_proxy(ip="203.0.113.1"), make_proxy(ip="203.0.113.2")]

        def fetch(kwargs: dict) -> str:
            if kwargs:
                raise ConnectionError("all proxies are bad")
            return "direct-ok"

        pool = _StaticPool(proxies)
        report = ProxyRotationReport()
        response = await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=pool,
            profile=ScraperProfile.FETCHER,
            max_attempts=2,
            report=report,
        )

        assert response == "direct-ok"
        assert report.fell_back_direct is True
        assert report.fallback_reason == "all_proxy_attempts_failed"
        assert report.used_proxy is None
        assert len(report.attempts) == 2
        assert all(entry.ok is False for entry in report.attempts)

    async def test_respects_max_attempts_bound(self) -> None:
        # Pool would happily serve new proxies; the attempt budget must cap
        # the loop (no infinite rotation). The final direct fetch also
        # fails, so the last error propagates to the caller.
        def fetch(kwargs: dict) -> str:
            if kwargs:
                raise ConnectionError("proxy nope")
            raise ConnectionError("direct down")

        async def select_proxy(exclude: Collection[UUID]) -> ValidProxy:
            return make_proxy(ip="203.0.113.99")  # always a fresh one

        report = ProxyRotationReport()
        with pytest.raises(ConnectionError, match="direct down"):
            await fetch_with_proxy_rotation(
                fetch=fetch,
                select_proxy=select_proxy,
                profile=ScraperProfile.FETCHER,
                max_attempts=2,
                report=report,
            )
        assert len(report.attempts) == 2

    async def test_direct_fetch_failure_raises_but_keeps_report(self) -> None:
        def fetch(kwargs: dict) -> str:
            raise RuntimeError("target is down")

        report = ProxyRotationReport()
        with pytest.raises(RuntimeError, match="target is down"):
            await fetch_with_proxy_rotation(
                fetch=fetch,
                select_proxy=_StaticPool([make_proxy()]),
                profile=ScraperProfile.FETCHER,
                max_attempts=2,
                report=report,
            )

        # The caller still gets the report for its activity log.
        assert report.fell_back_direct is True
        assert report.attempts[0].ok is False

    async def test_report_is_json_safe_and_credential_free(self) -> None:
        proxy = make_proxy(username="alice", password="s3cret")

        def fetch(kwargs: dict) -> str:
            if kwargs:
                raise ConnectionError("proxy http://alice:s3cret@host exploded")
            return "direct-ok"

        report = ProxyRotationReport()
        await fetch_with_proxy_rotation(
            fetch=fetch,
            select_proxy=_StaticPool([proxy]),
            profile=ScraperProfile.FETCHER,
            max_attempts=1,
            report=report,
        )

        summary = report.summary()
        json.dumps(summary)  # must not raise
        assert summary["enabled"] is True
        assert summary["fell_back_direct"] is True
        # Credentials are masked everywhere, including error strings.
        assert "alice" not in json.dumps(summary)
        assert "s3cret" not in json.dumps(summary)
        assert summary["attempts"][0]["proxy"] == (
            "http://203.0.113.10:8080 (authenticated)"
        )
        assert summary["attempts"][0]["error"] == ("proxy http://***:***@host exploded")
