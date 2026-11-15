"""Cross-profile fetcher surface tests — the scrapling >= 0.5 port.

Locks in the fixes for the API drift found during the PR #3 review:

- every ``ScraperProfile`` gets a working, callable ``.get`` from
  ``create_fetcher`` (``StealthyFetcher`` has no ``.get`` and
  ``DynamicFetcher`` no longer exists in scrapling >= 0.5),
- config-level ``fetch_options`` actually reach the scrapling request
  (the >= 0.5 ``Fetcher``/``StealthyFetcher`` constructors are deprecated
  no-ops, so options must travel as request-level kwargs),
- app-owned fetch_options keys (``proxy_retries``) never reach scrapling,
- unknown fetch_options keys are dropped with a warning, never a
  ``TypeError`` in the middle of a crawl job,
- the per-profile keyword white-lists match the *installed* scrapling
  (an installed-version smoke that fails loudly on upgrades).
"""

from __future__ import annotations

import inspect
import logging
from collections.abc import Iterator
from typing import Any

import pytest

import app.crawlers.factory as factory
from app.models.enums import ScraperProfile

# ── Fixes / helpers ──────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _fresh_adapter_cache() -> Iterator[None]:
    """Re-build adapter classes between tests.

    Adapter classes are cached per profile because they subclass
    ``scrapling`` classes — tests that monkeypatch ``scrapling.fetchers``
    need fresh subclassing against the stubs.
    """
    factory._reset_adapter_cache()
    yield
    factory._reset_adapter_cache()


def _recording_fetcher_stub() -> tuple[type, list[tuple[str, dict[str, Any]]]]:
    """A scrapling ``Fetcher`` stand-in with a recording classmethod get."""
    calls: list[tuple[str, dict[str, Any]]] = []

    class _RecordingFetcher:
        @classmethod
        def get(cls, url: str, **kwargs: Any) -> str:
            calls.append((url, kwargs))
            return "fetcher-response"

    return _RecordingFetcher, calls


def _recording_stealthy_stub() -> tuple[type, list[tuple[str, dict[str, Any]]]]:
    """A scrapling ``StealthyFetcher`` stand-in recording fetch calls."""
    calls: list[tuple[str, dict[str, Any]]] = []

    class _RecordingStealthy:
        @classmethod
        def fetch(cls, url: str, **kwargs: Any) -> str:
            calls.append((url, kwargs))
            return "browser-response"

    return _RecordingStealthy, calls


# ── Installed-version smoke ──────────────────────────────────────────


def test_installed_scrapling_is_0_5_or_newer() -> None:
    """The port targets scrapling >= 0.5; anything older must fail loudly."""
    scrapling = pytest.importorskip("scrapling")
    version: str = scrapling.__version__
    major, minor = (int(part) for part in version.split(".")[:2])
    assert (major, minor) >= (0, 5), (
        "pilgrim targets scrapling >= 0.5 — update app/crawlers/factory.py "
        "when supporting a different major behaviour."
    )


def test_scrapling_0_5_fetcher_surface_matches_expectations() -> None:
    """The exact drift found in review: fetch-methods per scrapling class."""
    pytest.importorskip("scrapling.fetchers")
    from scrapling.fetchers import Fetcher, StealthyFetcher

    assert callable(Fetcher.get)
    assert callable(StealthyFetcher.fetch)
    # The 0.5.1 drift: browser fetchers speak ``fetch``, not ``.get``.
    assert not hasattr(StealthyFetcher, "get")
    # The 0.5.1 drift: the plain Playwright fetcher is gone.
    with pytest.raises(ImportError):
        from scrapling.fetchers import DynamicFetcher as _DynamicFetcher  # noqa: F401


# ── Each profile: real fetcher, real fetch method ────────────────────


@pytest.mark.parametrize("profile", list(ScraperProfile))
def test_every_profile_returns_object_with_callable_get(
    profile: ScraperProfile,
) -> None:
    """The required per-profile create_fetcher + fetch-method assertion."""
    pytest.importorskip("scrapling.fetchers")

    fetcher = factory.create_fetcher(profile, {})

    get_method = getattr(fetcher, "get", None)
    assert callable(get_method), f"{profile} produced no callable .get"


def test_all_profiles_are_known_to_the_factory() -> None:
    """An app-level guard: no enum member may fall through the factory."""
    expected = {
        ScraperProfile.FETCHER,
        ScraperProfile.HTTP_SESSION,
        ScraperProfile.STEALTH,
        ScraperProfile.DYNAMIC,
        ScraperProfile.SPIDER,
    }
    assert set(ScraperProfile) == expected


def test_http_session_profile_keeps_a_working_session_instance() -> None:
    """HTTP_SESSION: isinstance + options applied + a real (refused) request.

    Against scrapling 0.5.1, ``FetcherSession`` instances have **no**
    ``.get`` — the pre-fix code crashed with ``AttributeError`` at fetch
    time.  The adapter must route through the entered session instead.
    """
    pytest.importorskip("scrapling.fetchers")
    from scrapling.fetchers import FetcherSession

    fetcher = factory.create_fetcher(ScraperProfile.HTTP_SESSION, {"timeout": 5})

    # isinstance stays true for callers/tests that check the real class
    # (assign to a variable first so mypy keeps ``fetcher`` as ``Any``).
    fetcher_is_real_session = isinstance(fetcher, FetcherSession)
    assert fetcher_is_real_session
    # Config options really reached the strict constructor.
    assert getattr(fetcher, "_default_timeout") == 5

    try:
        response = fetcher.get("http://127.0.0.1:9/__probe__")  # closed port
    except Exception as exc:  # noqa: BLE001 — any refusal is fine
        # Regression guard: the *drift* failure mode was AttributeError.
        assert not isinstance(exc, AttributeError), repr(exc)
    else:
        # Exotic environments may still connect; the request must have
        # reached scrapling's session API rather than AttributeErrors.
        assert response is not None


def test_fetch_options_reach_the_real_curl_cffi_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """fetch_options are NOT silently ignored (0.5 constructor no-op)."""
    pytest.importorskip("scrapling.fetchers")
    from scrapling.fetchers import requests as requests_module

    captured: list[tuple[str, dict[str, Any]]] = []

    class _ProbeClient:
        def get(self, url: str, **kwargs: Any) -> str:
            captured.append((url, kwargs))
            return "probe-ok"

    monkeypatch.setattr(requests_module, "__FetcherClientInstance__", _ProbeClient())

    fetcher = factory.create_fetcher(
        ScraperProfile.FETCHER,
        {"timeout": 20, "stealthy_headers": False},
    )
    result = fetcher.get("https://example.com/page")

    assert result == "probe-ok"
    url, kwargs = captured[0]
    assert url == "https://example.com/page"
    assert kwargs["timeout"] == 20
    assert kwargs["stealthy_headers"] is False


# ── Profile → real backend dispatch (stubbed) ────────────────────────


def test_fetcher_profile_merges_options_into_request_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub, calls = _recording_fetcher_stub()
    monkeypatch.setattr("scrapling.fetchers.Fetcher", stub)

    fetcher = factory.create_fetcher(ScraperProfile.FETCHER, {"timeout": 30})
    response = fetcher.get("https://example.com", proxy="http://203.0.113.1:8080")

    assert response == "fetcher-response"
    assert isinstance(fetcher, stub)  # adapters subclass the real class
    assert calls == [
        (
            "https://example.com",
            {"timeout": 30, "proxy": "http://203.0.113.1:8080"},
        )
    ]


def test_request_kwargs_win_over_fetch_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub, calls = _recording_fetcher_stub()
    monkeypatch.setattr("scrapling.fetchers.Fetcher", stub)

    fetcher = factory.create_fetcher(ScraperProfile.FETCHER, {"proxy": "http://cfg:1"})
    fetcher.get("https://example.com", proxy="http://rotation:2")

    _, kwargs = calls[0]
    # Proxy rotation's per-attempt proxy must override a static config proxy.
    assert kwargs["proxy"] == "http://rotation:2"


def test_stealth_profile_maps_to_the_real_fetch_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub, calls = _recording_stealthy_stub()
    monkeypatch.setattr("scrapling.fetchers.StealthyFetcher", stub)

    fetcher = factory.create_fetcher(ScraperProfile.STEALTH, {"timeout": 30})
    response = fetcher.get(
        "https://example.com",
        proxy={"server": "http://203.0.113.1:8080"},
    )

    assert response == "browser-response"
    assert isinstance(fetcher, stub)
    # fetch(), not .get() — and Pilgrim's seconds → scrapling's ms.
    assert calls == [
        (
            "https://example.com",
            {"timeout": 30_000, "proxy": {"server": "http://203.0.113.1:8080"}},
        )
    ]


def test_dynamic_profile_runs_on_the_stealthy_backend(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub, calls = _recording_stealthy_stub()
    monkeypatch.setattr("scrapling.fetchers.StealthyFetcher", stub)

    with caplog.at_level(logging.INFO, logger="app.crawlers.factory"):
        fetcher = factory.create_fetcher(ScraperProfile.DYNAMIC, {"headless": True})
        fetcher.get("https://example.com")

    assert isinstance(fetcher, stub)
    assert calls == [("https://example.com", {"headless": True})]
    assert any("dynamic" in msg and "StealthyFetcher" in msg for msg in caplog.messages)


def test_spider_profile_warns_and_uses_the_static_backend(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    stub, calls = _recording_fetcher_stub()
    monkeypatch.setattr("scrapling.fetchers.Fetcher", stub)

    with caplog.at_level(logging.WARNING, logger="app.crawlers.factory"):
        fetcher = factory.create_fetcher(ScraperProfile.SPIDER, {})
        fetcher.get("https://example.com")

    assert calls == [("https://example.com", {})]
    assert any("Spider" in record.message for record in caplog.records)


def test_unknown_profile_raises_value_error() -> None:
    bogus = "bogus"
    with pytest.raises(ValueError, match="Unknown scraper profile"):
        factory.prepare_fetch_options(
            bogus,  # type: ignore[arg-type]
            None,
        )
    with pytest.raises(ValueError, match="Unknown scraper profile"):
        factory.create_fetcher(
            bogus,  # type: ignore[arg-type]
            None,
        )


# ── fetch_options hygiene ────────────────────────────────────────────


def test_app_owned_keys_are_stripped_silently(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clean, dropped = factory.prepare_fetch_options(
        ScraperProfile.HTTP_SESSION,
        {"proxy_retries": 3, "timeout": 5},
    )

    assert clean == {"timeout": 5}
    assert dropped == []
    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert warnings == []


def test_unknown_keys_are_dropped_with_a_warning(
    caplog: pytest.LogCaptureFixture,
) -> None:
    clean, dropped = factory.prepare_fetch_options(
        ScraperProfile.DYNAMIC,
        {"wait_selector": "main", "cdp_url": "http://old:9222", "bogus": 1},
    )

    assert clean == {"wait_selector": "main"}
    assert sorted(dropped) == ["bogus", "cdp_url"]
    assert any("cdp_url" in record.message for record in caplog.records)


def test_options_are_filtered_per_profile_family() -> None:
    static_clean, static_dropped = factory.prepare_fetch_options(
        ScraperProfile.FETCHER,
        {"impersonate": "chrome131", "headless": True},
    )
    assert static_clean == {"impersonate": "chrome131"}
    assert static_dropped == ["headless"]

    browser_clean, browser_dropped = factory.prepare_fetch_options(
        ScraperProfile.STEALTH,
        {"impersonate": "chrome131", "useragent": "UA/1.0"},
    )
    assert browser_clean == {"useragent": "UA/1.0"}
    assert browser_dropped == ["impersonate"]


def test_browser_timeout_is_converted_seconds_to_milliseconds() -> None:
    clean, _ = factory.prepare_fetch_options(ScraperProfile.DYNAMIC, {"timeout": 60})
    assert clean == {"timeout": 60_000}

    static_clean, _ = factory.prepare_fetch_options(
        ScraperProfile.FETCHER, {"timeout": 60}
    )
    assert static_clean == {"timeout": 60}


# ── White-lists stay in sync with the installed scrapling ────────────


def test_option_whitelists_match_installed_scrapling() -> None:
    """Installed-version smoke: keep the mirrors honest across upgrades."""
    pytest.importorskip("scrapling")
    from scrapling.engines._browsers._types import (
        GetRequestParams,
        StealthSession,
    )
    from scrapling.fetchers import FetcherSession

    def _all_annotations(typed_dict: Any) -> set[str]:
        collected: set[str] = set()
        for base in typed_dict.__mro__:
            collected |= set(getattr(base, "__annotations__", {}) or {})
        return collected

    assert _all_annotations(GetRequestParams) == factory._STATIC_REQUEST_KEYS
    assert _all_annotations(StealthSession) == factory._BROWSER_REQUEST_KEYS

    session_params = {
        name
        for name, param in inspect.signature(FetcherSession.__init__).parameters.items()
        if name != "self"
    }
    assert session_params == factory._SESSION_CONSTRUCTOR_KEYS
