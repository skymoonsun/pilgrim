"""Regression tests: app-owned fetch-option keys are stripped at every
user-reachable ``create_fetcher`` call site.

PR #6 covered the worker path (``pilgrim.scrape.run_job``); these tests
lock in the two remaining raw sites:

- ``ScrapeService.execute`` — the sync scrape endpoint
  (``POST /api/v1/scrape``), which forwards the stored config's
  ``fetch_options``,
- ``AIService.verify_extraction_spec`` — the AI verification pipeline
  (``POST /api/v1/ai/verify-spec``), which forwards the request body's
  ``fetch_options``.

With ``fetch_options`` carrying an app-owned key (``proxy_retries``),
the dict handed to ``create_fetcher`` must no longer contain it —
Scrapling's strict-kwargs constructors raise ``TypeError`` on it —
while the caller's dict stays unmutated.  Real Scrapling kwargs
(``timeout``, ``impersonate``) pass through unchanged, and the
stripped dict still builds a real ``FetcherSession``.

No PostgreSQL/Redis/network: the DB layer, the factory's
``create_fetcher`` and ``get_settings`` are patched at module
boundaries; the shared helpers live in
``app.crawlers.fetch_options`` (the worker task module re-exports
them for backwards compatibility).
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import UUID, uuid4

import pytest

from app.crawlers.fetch_options import (
    APP_OWNED_FETCH_KEYS,
    strip_app_owned_keys,
)
from app.models.enums import ScraperProfile
from app.services.ai_service import AIService
from app.services.scrape_service import ScrapeService

RAW_OPTIONS: dict[str, Any] = {
    "timeout": 30,
    "proxy_retries": 3,
    "impersonate": "chrome_131",
}
STRIPPED_OPTIONS: dict[str, Any] = {"timeout": 30, "impersonate": "chrome_131"}


class _FakePage:
    """Scrapling response double: carries status + HTML, records ``get``."""

    def __init__(self) -> None:
        self.status = 200
        self.html = "<html>" + "x" * 600 + "</html>"
        self.html_content = self.html
        self.requested_url: str | None = None

    def get(self, url: str, **kwargs: Any) -> _FakePage:
        self.requested_url = url
        return self


def _fake_config_service(config: Any) -> Any:
    """Build a ``CrawlConfigService`` replacement returning *config*."""

    class _Service:
        def __init__(self, session: Any) -> None:
            self.session = session

        async def get_by_id(self, config_id: UUID) -> Any:
            return config

    return _Service


# ── Shared helper location + semantics ──────────────────────────────


class TestSharedStripHelper:
    def test_worker_module_reexports_are_canonical(self) -> None:
        """Services and the worker module must use the same helpers.

        The helper lives in ``app.crawlers.fetch_options`` (importable
        by the request-scoped services); the worker task module keeps a
        re-export so PR #6's imports keep working.
        """
        import app.workers.tasks.scrape as worker_scrape

        assert worker_scrape.strip_app_owned_keys is strip_app_owned_keys
        assert worker_scrape.APP_OWNED_FETCH_KEYS is APP_OWNED_FETCH_KEYS

    def test_proxy_retries_is_the_only_app_owned_key(self) -> None:
        assert APP_OWNED_FETCH_KEYS == frozenset({"proxy_retries"})

    def test_strips_only_app_owned_keys(self) -> None:
        assert strip_app_owned_keys(RAW_OPTIONS) == STRIPPED_OPTIONS

    def test_none_and_empty_options(self) -> None:
        assert strip_app_owned_keys(None) == {}
        assert strip_app_owned_keys({}) == {}

    def test_input_dict_is_not_mutated(self) -> None:
        raw = dict(RAW_OPTIONS)
        strip_app_owned_keys(raw)
        assert raw == RAW_OPTIONS


# ── ScrapeService.execute (sync scrape endpoint) ────────────────────


class TestScrapeServiceStripsAppOwnedKeys:
    async def test_execute_passes_stripped_options_to_create_fetcher(
        self,
    ) -> None:
        config = SimpleNamespace(
            id=uuid4(),
            scraper_profile=ScraperProfile.HTTP_SESSION,
            fetch_options=dict(RAW_OPTIONS),
            extraction_spec={"fields": {}},
        )
        captured: dict[str, Any] = {}
        page = _FakePage()

        def _recorder_fetcher(*args: Any, **kwargs: Any) -> _FakePage:
            captured["args"] = args
            captured["kwargs"] = dict(kwargs)
            return page

        with (
            patch(
                "app.services.scrape_service.CrawlConfigService",
                new=_fake_config_service(config),
            ),
            patch("app.crawlers.factory.create_fetcher", new=_recorder_fetcher),
        ):
            response = await ScrapeService(
                session=None,  # type: ignore[arg-type]  # DB layer is faked
            ).execute(config_id=config.id, url="https://example.com/page")

        # The dict that reached create_fetcher carries no app-owned key.
        assert captured["kwargs"]["fetch_options"] == STRIPPED_OPTIONS
        assert captured["kwargs"]["profile"] == ScraperProfile.HTTP_SESSION
        # The raw config options stay untouched.
        assert config.fetch_options == RAW_OPTIONS
        # The fetch itself ran and the extraction stage succeeded too.
        assert page.requested_url == "https://example.com/page"
        assert response.error is None
        assert response.data == {}


# ── AIService.verify_extraction_spec (AI verification endpoint) ─────


class TestVerifyExtractionSpecStripsAppOwnedKeys:
    async def test_verify_passes_stripped_options_to_create_fetcher(
        self,
    ) -> None:
        raw_options = dict(RAW_OPTIONS)
        captured: dict[str, Any] = {}
        page = _FakePage()

        def _recorder_fetcher(*args: Any, **kwargs: Any) -> _FakePage:
            captured["args"] = args
            captured["kwargs"] = dict(kwargs)
            return page

        settings = SimpleNamespace(
            ai_enabled=True,
            ai_max_verification_iterations=3,
            ai_max_html_chars=20000,
        )

        with (
            patch(
                "app.services.ai_service.get_settings",
                new=lambda: settings,
            ),
            patch("app.crawlers.factory.create_fetcher", new=_recorder_fetcher),
        ):
            result = await AIService().verify_extraction_spec(
                url="https://example.com/page",
                extraction_spec={"fields": {}},
                scraper_profile=ScraperProfile.HTTP_SESSION,
                fetch_options=raw_options,
                max_iterations=0,  # verify only — no LLM refinement
            )

        # The dict that reached create_fetcher carries no app-owned key.
        assert captured["kwargs"]["fetch_options"] == STRIPPED_OPTIONS
        # The caller's dict stays untouched.
        assert raw_options == RAW_OPTIONS
        # The fetch + verification pipeline completed.
        assert page.requested_url == "https://example.com/page"
        assert result.iterations_performed == 0


# ── Real Scrapling constructor (strict kwargs) ──────────────────────


class TestStrippedOptionsBuildRealFetchers:
    def test_stripped_service_options_build_a_real_fetcher_session(self) -> None:
        """The dict shape reaching both call sites must be constructor-safe.

        ``timeout``/``impersonate`` (the pass-through keys captured at
        ``ScrapeService.execute`` and
        ``AIService.verify_extraction_spec``) must build a real
        ``FetcherSession`` on scrapling 0.5, while the raw
        ``proxy_retries`` key keeps being rejected — the strict-kwargs
        ``TypeError`` that killed every http_session fetch before the
        stripping existed. If a future Scrapling version accepts the
        key, the raises-check can be dropped; the stripping must stay.
        """
        pytest.importorskip("scrapling.fetchers")
        from scrapling.fetchers import FetcherSession

        from app.crawlers.factory import create_fetcher

        fetcher = create_fetcher(ScraperProfile.HTTP_SESSION, STRIPPED_OPTIONS)
        assert isinstance(fetcher, FetcherSession)

        # The raw key must still be rejected by the constructor, exactly
        # as observed on scrapling 0.5.1 when the bug was found.
        with pytest.raises(TypeError, match="proxy_retries"):
            FetcherSession(proxy_retries=3)  # type: ignore[call-arg]
