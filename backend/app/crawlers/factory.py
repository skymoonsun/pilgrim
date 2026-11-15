"""Scrapling fetcher adapter layer (scrapling >= 0.5).

Workers, the synchronous scrape service and the AI service all call
``create_fetcher(profile, fetch_options)`` and then treat the returned
object the same way: ``fetcher.get(url, **request_kwargs)``.  The factory
shields them from scrapling >= 0.5's very different per-profile API:

===================  ==========================================================
Profile              scrapling >= 0.5 backend
===================  ==========================================================
``fetcher``          ``Fetcher`` — classmethod ``Fetcher.get`` (curl_cffi)
``http_session``     ``FetcherSession`` — strict constructor kwargs, requests
                     go through the entered session
``stealth``          ``StealthyFetcher`` — classmethod ``fetch`` (Patchright
                     browser), request-level kwargs
``dynamic``          ``StealthyFetcher`` as well — scrapling >= 0.5 removed
                     the plain Playwright backend, so the ``dynamic`` profile
                     is served by the same stealthy backend (see scrapling's
                     "Migrating to v0.5" guide)
``spider``           ``Fetcher`` — spiders are used through their own classes
===================  ==========================================================

Why *adapters*, not raw scrapling classes
-----------------------------------------

1. scrapling >= 0.5 turned ``Fetcher``/``StealthyFetcher`` constructors
   into deprecated no-ops and moved every option to **request-level
   kwargs** (``Fetcher.get(url, **opts)`` / ``StealthyFetcher.fetch(url,
   **opts)``).  The caller's contract is ``.get(url)`` *with* config-level
   ``fetch_options`` — so the adapter carries the options and merges them
   into per-request kwargs (request kwargs win over config options).
2. ``FetcherSession`` (the one class whose constructor kwargs still work)
   lost its public ``.get()`` — requests must go through the entered
   session (``with session: session.get(...)``).
3. ``DynamicFetcher`` no longer exists in ``scrapling.fetchers`` — an
   import of it fails with ``ImportError``.

The adapters **subclass the real scrapling classes**, so callers (and
regression tests from other branches) may keep asserting e.g.
``isinstance(fetcher, FetcherSession)``.

Options validation
------------------

``fetch_options`` are a user-supplied JSONB dict on ``CrawlConfiguration``
and might contain keys a given profile's scrapling request API does not
accept.  :func:`prepare_fetch_options` white-lists them per profile
family and **drops unknown keys with a warning** instead of letting
scrapling raise a ``TypeError`` deep inside a crawl job.  App-owned meta
keys (``proxy_retries`` — consumed via
:mod:`app.services.proxy_rotation`) are stripped silently.

All scrapling imports stay **lazy** (inside the adapter builders, cached
per profile) so the slim API image can import this module — and start —
without ``scrapling[fetchers]`` installed.

Note on units: Pilgrim documents ``fetch_options.timeout`` in *seconds*;
scrapling's static backends use seconds, the browser backends use
milliseconds, so the browser adapters receive ``timeout * 1000``.
"""

from __future__ import annotations

import logging
from typing import Any

from app.models.enums import ScraperProfile

logger = logging.getLogger(__name__)

#: ``fetch_options`` keys Pilgrim consumes itself and never forwards to
#: scrapling.  ``proxy_retries`` (the proxy-rotation budget) is read from
#: the *raw* options by ``app.services.proxy_rotation.resolve_proxy_attempts``.
APP_OWNED_FETCH_KEYS: frozenset[str] = frozenset({"proxy_retries"})

# Keyword surfaces mirrored from scrapling >= 0.5's own typing:
# ``RequestParams`` (curl_cffi backends) and ``StealthSession`` (browser).
# ``tests/test_crawlers_factory.py`` asserts these stay in sync with the
# *installed* scrapling — update on scrapling upgrades.
_STATIC_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "impersonate",
        "http3",
        "stealthy_headers",
        "proxies",
        "proxy",
        "proxy_auth",
        "proxy_rotator",
        "timeout",
        "headers",
        "retries",
        "retry_delay",
        "follow_redirects",
        "max_redirects",
        "verify",
        "cert",
        "selector_config",
        "params",
        "cookies",
        "auth",
    }
)

# ``FetcherSession``'s constructor kwargs (the request-only keys
# ``params``/``cookies``/``auth`` are applied at fetch time instead).
_SESSION_CONSTRUCTOR_KEYS: frozenset[str] = frozenset(
    {
        "impersonate",
        "http3",
        "stealthy_headers",
        "proxies",
        "proxy",
        "proxy_auth",
        "proxy_rotator",
        "timeout",
        "headers",
        "retries",
        "retry_delay",
        "follow_redirects",
        "max_redirects",
        "verify",
        "cert",
        "selector_config",
    }
)

_BROWSER_REQUEST_KEYS: frozenset[str] = frozenset(
    {
        "max_pages",
        "headless",
        "disable_resources",
        "network_idle",
        "load_dom",
        "pierce_shadow",
        "wait_selector",
        "wait_selector_state",
        "cookies",
        "google_search",
        "wait",
        "timezone_id",
        "page_action",
        "page_setup",
        "proxy",
        "proxy_rotator",
        "extra_headers",
        "timeout",
        "init_script",
        "user_data_dir",
        "selector_config",
        "additional_args",
        "locale",
        "useragent",
        "extra_flags",
        "blocked_domains",
        "block_ads",
        "retries",
        "retry_delay",
        "record_requests",
        "max_recorded_requests",
        "executable_path",
        "dns_over_https",
        "real_chrome",
        "allow_webgl",
        "hide_canvas",
        "block_webrtc",
        "solve_cloudflare",
    }
)

_BROWSER_PROFILES = frozenset({ScraperProfile.STEALTH, ScraperProfile.DYNAMIC})


def prepare_fetch_options(
    profile: ScraperProfile,
    fetch_options: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str]]:
    """Clean *fetch_options* for *profile* before they touch scrapling.

    Returns ``(clean_options, dropped_keys)``:

    - app-owned keys (:data:`APP_OWNED_FETCH_KEYS`) are stripped silently,
    - keys that the profile's scrapling request API does not accept are
      dropped and reported (warning here, ``dropped_keys`` for the caller),
    - browser profiles get their ``timeout`` converted seconds →
      milliseconds (Pilgrim documents ``timeout`` in seconds for every
      profile; scrapling's browser backends expect ms).

    Pure and scrapling-free — unknown profiles raise ``ValueError``
    without importing anything.
    """
    if profile not in set(ScraperProfile):
        raise ValueError(f"Unknown scraper profile: {profile}")

    raw = dict(fetch_options or {})
    app_keys = sorted(key for key in raw if key in APP_OWNED_FETCH_KEYS)
    for key in app_keys:
        raw.pop(key)

    allowed = (
        _BROWSER_REQUEST_KEYS if profile in _BROWSER_PROFILES else _STATIC_REQUEST_KEYS
    )

    clean: dict[str, Any] = {}
    dropped: list[str] = []
    for key, value in raw.items():
        if key in allowed:
            clean[key] = value
        else:
            dropped.append(key)

    if dropped:
        logger.warning(
            "Dropping fetch_options keys %s — not valid for the '%s' "
            "profile's scrapling request API (valid: %s)",
            dropped,
            profile.value,
            ", ".join(sorted(allowed)),
        )
    if app_keys:
        logger.debug(
            "Stripped app-owned fetch_options keys %s before scrapling",
            app_keys,
        )

    if profile in _BROWSER_PROFILES:
        timeout = clean.get("timeout")
        if isinstance(timeout, (int, float)) and not isinstance(timeout, bool):
            clean["timeout"] = timeout * 1000

    return clean, dropped


# Adapter classes are built lazily (they subclass scrapling classes, so
# they cannot exist until scrapling is importable) and cached per profile.
_ADAPTER_CACHE: dict[ScraperProfile, type] = {}


def _reset_adapter_cache() -> None:
    """Force adapter classes to be re-built on the next ``create_fetcher``.

    Test hook: tests monkeypatch ``scrapling.fetchers.*`` stubs and need
    adapter classes re-created against them.
    """
    _ADAPTER_CACHE.clear()


def _adapter_class(profile: ScraperProfile) -> type:
    cached = _ADAPTER_CACHE.get(profile)
    if cached is not None:
        return cached

    if profile in (ScraperProfile.FETCHER, ScraperProfile.SPIDER):
        from scrapling.fetchers import Fetcher

        class _StaticFetcherAdapter(Fetcher):
            """Uniform ``.get`` for the static (curl_cffi) profile.

            The 0.5 ``Fetcher`` constructor is a deprecated no-op; config
            options are carried here and merged into the request-level
            kwargs of the classmethod ``Fetcher.get`` instead.
            """

            def __init__(self, base_options: dict[str, Any]) -> None:
                self._base_options = dict(base_options)

            def get(self, url: str, **kwargs: Any) -> Any:  # type: ignore[override]
                # The instance-method override of the classmethod
                # ``Fetcher.get`` is deliberate: the adapter's whole point
                # is one uniform ``.get(url, **kwargs)`` surface, and
                # options travel as request-level kwargs.
                return Fetcher.get(url, **{**self._base_options, **kwargs})

        adapter_cls: type = _StaticFetcherAdapter

    elif profile == ScraperProfile.HTTP_SESSION:
        from scrapling.fetchers import FetcherSession

        class _SessionFetcherAdapter(FetcherSession):
            """Uniform ``.get`` for the session-based profile.

            ``FetcherSession`` keeps working constructor kwargs in 0.5,
            but has no public ``.get`` — requests go through the entered
            session (a fresh curl_cffi client per fetch call).  Keys that
            the constructor does not accept (``params``/``cookies``/
            ``auth``) ride along into ``session.get`` instead.
            """

            def __init__(self, base_options: dict[str, Any]) -> None:
                session_kwargs = {
                    key: value
                    for key, value in base_options.items()
                    if key in _SESSION_CONSTRUCTOR_KEYS
                }
                super().__init__(**session_kwargs)
                self._request_options = {
                    key: value
                    for key, value in base_options.items()
                    if key not in _SESSION_CONSTRUCTOR_KEYS
                }

            def get(self, url: str, **kwargs: Any) -> Any:
                with self as session_logic:
                    return session_logic.get(url, **{**self._request_options, **kwargs})

        adapter_cls = _SessionFetcherAdapter

    elif profile in _BROWSER_PROFILES:
        from scrapling.fetchers import StealthyFetcher

        class _BrowserFetcherAdapter(StealthyFetcher):
            """Uniform ``.get`` for the browser profiles.

            ``StealthyFetcher`` exposes ``fetch()`` (no ``.get()``) as a
            classmethod with request-level kwargs; config options are
            carried here and merged into every fetch.
            """

            def __init__(self, base_options: dict[str, Any]) -> None:
                self._base_options = dict(base_options)

            def get(self, url: str, **kwargs: Any) -> Any:
                return StealthyFetcher.fetch(url, **{**self._base_options, **kwargs})

        adapter_cls = _BrowserFetcherAdapter

    else:  # pragma: no cover — prepare_fetch_options rejects first
        raise ValueError(f"Unknown scraper profile: {profile}")

    _ADAPTER_CACHE[profile] = adapter_cls
    return adapter_cls


def create_fetcher(
    profile: ScraperProfile,
    fetch_options: dict[str, Any] | None = None,
) -> Any:
    """Return an adapter configured for *profile* with a uniform surface.

    The caller treats the result as ``fetcher.get(url, **request_kwargs)``:

    - ``fetch_options`` (config-level, e.g. ``{"timeout": 30,
      "impersonate": "chrome131"}``) are validated per profile and merged
      into every request; ``request_kwargs`` win over config options.
    - The proxy-rotation flow passes ``proxy`` / ``proxy_auth`` (static
      profiles) or a ``proxy`` dict (browser profiles) as request kwargs
      via this very same surface.

    All scrapling imports happen lazily so the API process can start
    without ``scrapling[fetchers]`` installed.
    """
    base_options, _dropped = prepare_fetch_options(profile, fetch_options)

    if profile == ScraperProfile.DYNAMIC:
        logger.info(
            "Profile 'dynamic' maps to StealthyFetcher — scrapling >= 0.5 "
            "removed the plain Playwright dynamic backend."
        )
    if profile == ScraperProfile.SPIDER:
        logger.warning(
            "Spider profile requested via create_fetcher — "
            "returning a static Fetcher; use Spider classes for crawls."
        )

    return _adapter_class(profile)(base_options)
