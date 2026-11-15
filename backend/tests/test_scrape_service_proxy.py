"""Mocked end-to-end tests for the sync scrape path's proxy rotation.

``ScrapeService.execute`` (``POST /api/v1/scrape``) used to fetch
directly even when the config had ``use_proxy = true`` — the proxy
rotation documented for the async ``run_job`` path was missing here.
These tests lock in the parity: the fetch is routed through
``proxy_rotation.fetch_with_proxy_rotation`` against fakes (no
PostgreSQL, no Redis, no Scrapling — the DB services and the factory's
``create_fetcher`` are patched at the module boundary), so that

- a healthy proxy serves the fetch,
- a failed attempt rotates to a *different* proxy,
- an empty/exhausted pool falls back to a direct fetch, the response
  still succeeds, and the credential-free ``proxy`` story is attached,
- the app-owned ``fetch_options.proxy_retries`` key is stripped before
  ``create_fetcher`` yet still drives the rotation budget,
- the raw config's ``fetch_options`` dict is never mutated, and
- proxy credentials never surface in the attempt records.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

from app.models.enums import ProxyProtocol, ScraperProfile
from app.models.valid_proxy import ValidProxy
from app.schemas.crawl import ScrapeResponse
from app.services.scrape_service import ScrapeService

TARGET_URL = "https://example.com/page"

# ── Fakes ───────────────────────────────────────────────────────────


class _RecordingFetcher:
    """Scrapling fetcher double: records every ``get()`` call."""

    def __init__(
        self,
        fail_proxies: set[str] | None = None,
        fail_get: Any = None,
    ) -> None:
        self.fail_proxies = fail_proxies or set()
        self._fail_get = fail_get
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, dict(kwargs)))
        if self._fail_get is not None:
            return self._fail_get(url, **kwargs)
        proxy = kwargs.get("proxy")
        if proxy in self.fail_proxies:
            raise ConnectionError(f"proxy {proxy} unreachable")
        return SimpleNamespace(status=200, html="<html></html>")


class _FakeProxyService:
    """Serves healthy proxies in order, honouring exclusions."""

    def __init__(self, proxies: list[ValidProxy]) -> None:
        self.proxies = proxies
        self.exclusion_calls: list[set[UUID]] = []

    async def get_random_healthy(
        self,
        protocol: ProxyProtocol | None = None,
        *,
        exclude_ids: Any = None,
    ) -> ValidProxy | None:
        self.exclusion_calls.append(set(exclude_ids or ()))
        for proxy in self.proxies:
            if proxy.id not in (exclude_ids or ()):
                return proxy
        return None


def _fake_config_service(config: Any) -> Any:
    """Build a ``CrawlConfigService`` replacement returning *config*."""

    class _Service:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def get_by_id(self, config_id: UUID) -> Any:
            return config

    return _Service


def make_proxy(**overrides: Any) -> ValidProxy:
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


def make_config(*, use_proxy: bool = True) -> Any:
    return SimpleNamespace(
        id=uuid4(),
        scraper_profile=ScraperProfile.FETCHER,
        fetch_options={"timeout": 30, "proxy_retries": 3},
        extraction_spec={"fields": {}},  # → extract_data returns {}
        use_proxy=use_proxy,
    )


async def _run_execute(
    config: Any,
    proxies: list[ValidProxy],
    *,
    fail_proxies: set[str] | None = None,
    fail_get: Any = None,
) -> tuple[ScrapeResponse, _RecordingFetcher, _FakeProxyService, dict[str, Any]]:
    """Execute ``ScrapeService.execute`` against fakes; return doubles."""
    fetcher = _RecordingFetcher(fail_proxies, fail_get)
    proxy_service = _FakeProxyService(proxies)
    captured: dict[str, Any] = {}

    def _create_fetcher(*args: Any, **kwargs: Any) -> Any:
        captured["args"] = args
        captured["kwargs"] = dict(kwargs)
        return fetcher

    with (
        patch(
            "app.services.scrape_service.CrawlConfigService",
            new=_fake_config_service(config),
        ),
        patch(
            "app.services.scrape_service.ValidProxyService",
            new=lambda session_arg: proxy_service,
        ),
        patch(
            "app.crawlers.factory.create_fetcher",
            new=_create_fetcher,
        ),
    ):
        response = await ScrapeService(
            session=None,  # type: ignore[arg-type]  # DB layer is faked
        ).execute(config_id=config.id, url=TARGET_URL)

    return response, fetcher, proxy_service, captured


# ── Proxy rotation on the sync path ─────────────────────────────────


class TestScrapeServiceProxyRotation:
    async def test_use_proxy_fetches_through_healthy_pool(self) -> None:
        proxy = make_proxy()
        response, fetcher, proxy_service, _ = await _run_execute(
            make_config(use_proxy=True), [proxy]
        )

        # The fetch really went through the proxy.
        assert fetcher.calls == [
            (TARGET_URL, {"proxy": "http://203.0.113.10:8080"})
        ]
        assert response.error is None
        assert response.data == {}

        # The response itself carries the credential-free proxy story.
        story = response.proxy
        assert story is not None
        assert story["enabled"] is True
        assert story["used"] == "http://203.0.113.10:8080"
        assert story["fell_back_direct"] is False
        assert story["fallback_reason"] is None
        assert [attempt["ok"] for attempt in story["attempts"]] == [True]
        assert proxy_service.exclusion_calls == [set()]

    async def test_failed_proxy_rotates_to_next_then_succeeds(self) -> None:
        first = make_proxy(ip="203.0.113.1")
        second = make_proxy(ip="203.0.113.2")
        response, fetcher, proxy_service, _ = await _run_execute(
            make_config(use_proxy=True),
            [first, second],
            fail_proxies={"http://203.0.113.1:8080"},
        )

        # Both proxies were used, in rotation order, and the second
        # selection excluded the failed first proxy.
        assert [kwargs.get("proxy") for _, kwargs in fetcher.calls] == [
            "http://203.0.113.1:8080",
            "http://203.0.113.2:8080",
        ]
        assert proxy_service.exclusion_calls[1] == {first.id}

        story = response.proxy
        assert story is not None
        assert story["used"] == "http://203.0.113.2:8080"
        assert [attempt["ok"] for attempt in story["attempts"]] == [False, True]
        assert story["fell_back_direct"] is False
        assert response.error is None and response.data == {}

    async def test_empty_pool_falls_back_to_direct_fetch(self) -> None:
        response, fetcher, proxy_service, _ = await _run_execute(
            make_config(use_proxy=True), []
        )

        # No healthy proxy existed: the fetch went direct, once, and
        # still succeeded.
        assert proxy_service.exclusion_calls == [set()]
        assert fetcher.calls == [(TARGET_URL, {})]
        assert response.error is None
        assert response.data == {}

        story = response.proxy
        assert story is not None
        assert story["used"] is None
        assert story["fell_back_direct"] is True
        assert story["fallback_reason"] == "no_healthy_proxy_available"
        assert story["attempts"] == []

    async def test_failed_proxy_then_exhausted_pool_falls_back_to_direct(
        self,
    ) -> None:
        only = make_proxy(ip="203.0.113.1")
        response, fetcher, _, _ = await _run_execute(
            make_config(use_proxy=True),
            [only],
            fail_proxies={"http://203.0.113.1:8080"},
        )

        # One proxied attempt, then a direct retry without proxy kwargs.
        assert fetcher.calls[0] == (
            TARGET_URL, {"proxy": "http://203.0.113.1:8080"},
        )
        assert fetcher.calls[1] == (TARGET_URL, {})

        story = response.proxy
        assert story is not None
        assert story["used"] is None
        assert story["fell_back_direct"] is True
        assert story["fallback_reason"] == "no_healthy_proxy_available"
        assert story["attempts"][0]["ok"] is False

    async def test_use_proxy_false_fetches_directly(self) -> None:
        response, fetcher, proxy_service, _ = await _run_execute(
            make_config(use_proxy=False), [make_proxy()]
        )

        assert fetcher.calls == [(TARGET_URL, {})]
        # The proxy pool must not even be consulted.
        assert proxy_service.exclusion_calls == []
        # No proxy story when rotation is disabled.
        assert response.error is None
        assert response.data == {}
        assert response.proxy is None


# ── App-owned fetch-option keys on the sync path ────────────────────


class TestSyncPathStripAndBudget:
    async def test_proxy_retries_drives_rotation_but_never_reaches_create_fetcher(
        self,
    ) -> None:
        """The stripped options build the fetcher; the raw ones budget rotation."""
        first = make_proxy(ip="203.0.113.1")
        second = make_proxy(ip="203.0.113.2")
        config = SimpleNamespace(
            id=uuid4(),
            scraper_profile=ScraperProfile.HTTP_SESSION,
            fetch_options={"timeout": 30, "proxy_retries": 1},
            extraction_spec={"fields": {}},
            use_proxy=True,
        )
        response, fetcher, _, captured = await _run_execute(
            config,
            [first, second],
            fail_proxies={"http://203.0.113.1:8080"},
        )

        # ``create_fetcher`` saw only genuine Scrapling kwargs — the
        # app-owned key never reached the strict-kwargs constructor.
        assert captured["kwargs"]["fetch_options"] == {"timeout": 30}
        assert captured["kwargs"]["profile"] == ScraperProfile.HTTP_SESSION

        # The RAW options still governed the rotation budget: with
        # ``proxy_retries``=1 the single failing proxy yields exactly
        # one proxied attempt followed by the direct fallback — the
        # second healthy proxy is never tried.
        assert [
            kwargs.get("proxy") for _, kwargs in fetcher.calls
        ] == ["http://203.0.113.1:8080", None]

        # The config's fetch_options were not mutated in place.
        assert config.fetch_options == {"timeout": 30, "proxy_retries": 1}

        story = response.proxy
        assert story is not None
        assert story["fell_back_direct"] is True
        assert story["attempts"][0]["ok"] is False

    async def test_every_fetch_failing_keeps_proxy_story_on_error_response(
        self,
    ) -> None:
        """Failed scrapes still tell the proxy story, like failed jobs."""

        def _fail_on_get(url: str, **kwargs: Any) -> Any:
            if kwargs:
                raise ConnectionError("proxy broken")
            raise RuntimeError("target unreachable")

        only = make_proxy(ip="203.0.113.1")
        response, fetcher, _, _ = await _run_execute(
            make_config(use_proxy=True),
            [only],
            fail_get=_fail_on_get,
        )

        assert response.error == "Fetch error: target unreachable"
        assert response.data is None
        assert len(fetcher.calls) == 2

        story = response.proxy
        assert story is not None
        assert story["used"] is None
        assert story["fell_back_direct"] is True
        assert story["attempts"][0]["ok"] is False
        assert story["attempts"][0]["proxy"] == "http://203.0.113.1:8080"

    async def test_failed_attempt_error_is_credential_free(self) -> None:
        """Credentials leaking through a fetch exception are masked.

        The proxied attempt's exception is never raised — it is
        sanitized into the proxy story; only the direct (proxyless)
        fallback's error surfaces in ``response.error``.  (The
        failed-attempt WARNING log channel on the rotation helper is
        still raw on this base branch — masking it is PR #5's scope,
        fix/proxy-log-redaction.)
        """
        secret = make_proxy(
            ip="203.0.113.9",
            username="secret_user",
            password="hunter2",
        )

        def _leaky_on_proxy(url: str, **kwargs: Any) -> Any:
            if kwargs:  # proxied attempt — leaky client exception
                raise ConnectionError(
                    "cannot connect to "
                    f"{secret.protocol.value}://{secret.username}:"
                    f"{secret.password}@{secret.ip}:{secret.port}"
                )
            raise RuntimeError("target unreachable")  # direct fallback

        response, _, _, _ = await _run_execute(
            make_config(use_proxy=True),
            [secret],
            fail_get=_leaky_on_proxy,
        )

        story = response.proxy
        assert story is not None
        attempt_error = story["attempts"][0]["error"]
        assert attempt_error is not None
        assert "secret_user" not in attempt_error
        assert "hunter2" not in attempt_error
        # The credential-free label is what identifies the proxy.
        assert story["attempts"][0]["proxy"] == (
            "http://203.0.113.9:8080 (authenticated)"
        )
        # The raised error belongs to the direct fallback, not to the
        # leaky proxied attempt.
        assert response.error == "Fetch error: target unreachable"


# ── Response schema surface ─────────────────────────────────────────


class TestScrapeResponseProxyField:
    def test_proxy_field_defaults_to_none(self) -> None:
        model = ScrapeResponse(
            config_id=uuid4(), url="https://example.com"
        )
        assert model.proxy is None
