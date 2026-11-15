"""Proxy rotation helpers for crawl workers.

``run_crawl_job`` uses this module when a ``CrawlConfiguration`` has
``use_proxy = true``: each fetch picks a random healthy proxy from the
``ValidProxy`` pool, rotates to a *different* proxy on failure, and — when
the pool has nothing left to offer — falls back to a direct (proxyless)
request. Every decision is recorded in a :class:`ProxyRotationReport` so
the job's activity log stays transparent about which proxy was used, how
many attempts were made, and what the outcome was.

Design notes
------------

- The Scrapling fetcher is **injected** as a callable so this module stays
  importable (and testable) without the heavy ``scrapling[fetchers]``
  extras installed.
- Proxy credentials never appear in reports, labels or log lines — see
  :func:`proxy_label`.
- Attempt kwargs follow Scrapling 0.4's request-level proxy API: static
  (curl_cffi) profiles take ``proxy`` + ``proxy_auth`` keyword arguments,
  while browser (Playwright) profiles take a single ``proxy`` dict with the
  keys ``server``, ``username`` and ``password``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Collection
from dataclasses import dataclass, field
from typing import Any, cast
from uuid import UUID

from app.models.enums import ProxyProtocol, ScraperProfile
from app.models.valid_proxy import ValidProxy

logger = logging.getLogger(__name__)

# ── Retry budget ────────────────────────────────────────────────────
# Distinct proxies a single fetch may try before falling back to a
# direct request. Configurable per crawl config via
# ``fetch_options.proxy_retries``; clamped to keep free-proxy pools from
# hammering the target site.
DEFAULT_PROXY_ATTEMPTS = 3
MIN_PROXY_ATTEMPTS = 1
MAX_PROXY_ATTEMPTS = 5

# Cap on how much of a fetch error is stored per attempt in the activity
# log — keeps ``result_summary`` JSONB rows small.
_MAX_ERROR_CHARS = 500

# Scraper profiles running on curl_cffi (static HTTP fetchers), which take
# ``proxy`` + ``proxy_auth`` request kwargs. Browser profiles (Playwright)
# take a single ``proxy`` dict instead.
_STATIC_PROFILES = frozenset(
    {ScraperProfile.FETCHER, ScraperProfile.HTTP_SESSION, ScraperProfile.SPIDER}
)


def resolve_proxy_attempts(fetch_options: dict[str, Any] | None) -> int:
    """Return how many distinct proxies one fetch may try.

    Reads ``proxy_retries`` from the crawl config's ``fetch_options``
    JSONB and clamps it to ``[MIN_PROXY_ATTEMPTS, MAX_PROXY_ATTEMPTS]``.
    Anything non-numeric falls back to ``DEFAULT_PROXY_ATTEMPTS``.
    """
    raw = (fetch_options or {}).get("proxy_retries", DEFAULT_PROXY_ATTEMPTS)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return DEFAULT_PROXY_ATTEMPTS
    return max(MIN_PROXY_ATTEMPTS, min(MAX_PROXY_ATTEMPTS, value))


def proxy_label(proxy: ValidProxy) -> str:
    """Return a human-readable, credential-free label for *proxy*.

    Only the protocol, IP and port are ever exposed — usernames and
    passwords must not reach activity logs or worker stdout.
    """
    protocol = (
        proxy.protocol.value
        if isinstance(proxy.protocol, ProxyProtocol)
        else str(proxy.protocol)
    )
    label = f"{protocol}://{proxy.ip}:{proxy.port}"
    if proxy.username or proxy.password:
        label += " (authenticated)"
    return label


def build_fetch_proxy_kwargs(
    proxy: ValidProxy,
    profile: ScraperProfile,
) -> dict[str, Any]:
    """Translate a ``ValidProxy`` into Scrapling 0.4 request kwargs.

    - Static profiles (curl_cffi): ``{"proxy": "<url>"}`` plus an optional
      ``proxy_auth`` tuple. Credentials are kept **out** of the URL so
      they never leak through accidental stringification of the kwargs.
    - Browser profiles (Playwright): ``{"proxy": {"server": ...}}`` with
      optional ``username`` / ``password`` keys (the only keys Scrapling
      accepts for browser proxies).
    """
    protocol = (
        proxy.protocol.value
        if isinstance(proxy.protocol, ProxyProtocol)
        else str(proxy.protocol)
    )
    server = f"{protocol}://{proxy.ip}:{proxy.port}"

    if profile in _STATIC_PROFILES:
        kwargs: dict[str, Any] = {"proxy": server}
        if proxy.username and proxy.password:
            kwargs["proxy_auth"] = (proxy.username, proxy.password)
        return kwargs

    browser_proxy: dict[str, str] = {"server": server}
    if proxy.username:
        browser_proxy["username"] = proxy.username
    if proxy.password:
        browser_proxy["password"] = proxy.password
    return {"proxy": browser_proxy}


def _sanitize_error(exc: BaseException, proxy: ValidProxy) -> str:
    """Return a log-safe error string for a failed proxy attempt.

    Credentials of *proxy* are masked out defensively: fetch exceptions
    come from third-party code, so we never trust their message to be
    credential-free.
    """
    text = str(exc)[:_MAX_ERROR_CHARS]
    for secret in (proxy.username, proxy.password):
        if secret:
            text = text.replace(secret, "***")
    return text


@dataclass(frozen=True)
class ProxyAttemptLog:
    """One proxy try, as recorded in the job's activity log."""

    attempt: int
    proxy: str
    ok: bool
    error: str | None = None


@dataclass
class ProxyRotationReport:
    """Activity-log view of a proxied fetch (credential-free).

    Mutated in place by :func:`fetch_with_proxy_rotation` so that the
    caller keeps the report even when the fetch ultimately raises.
    """

    used_proxy: str | None = None
    attempts: list[ProxyAttemptLog] = field(default_factory=list)
    fell_back_direct: bool = False
    fallback_reason: str | None = None

    def summary(self) -> dict[str, Any]:
        """Return a JSON-safe dict for ``CrawlJob.result_summary['proxy']``."""
        return {
            "enabled": True,
            "used": self.used_proxy,
            "attempts": [
                {
                    "attempt": entry.attempt,
                    "proxy": entry.proxy,
                    "ok": entry.ok,
                    "error": entry.error,
                }
                for entry in self.attempts
            ],
            "fell_back_direct": self.fell_back_direct,
            "fallback_reason": self.fallback_reason,
        }


async def fetch_with_proxy_rotation(
    *,
    fetch: Callable[[dict[str, Any]], Any],
    select_proxy: Callable[[Collection[UUID]], Awaitable[ValidProxy | None]],
    profile: ScraperProfile,
    max_attempts: int,
    report: ProxyRotationReport,
) -> Any:
    """Run *fetch* through the healthy proxy pool, rotating on failure.

    Behaviour (mirrors the README "Proxy rotation" section):

    1. Up to *max_attempts* **distinct** healthy proxies are tried; each
       attempt requests a fresh random proxy via *select_proxy*, which
       receives the proxy IDs tried so far (rotation must not retry the
       same failed proxy).
    2. The first successful response is returned immediately.
    3. If the pool runs dry — because it was empty from the start or every
       healthy proxy has been tried — the fetch is retried **without** a
       proxy and the fallback is flagged on *report*.

    *report* is filled in as the loop progresses so callers can persist it
    even when this function raises. Raises whatever the final (direct)
    fetch raised; individual proxy attempt errors are recorded on
    *report*, never raised.
    """
    tried: set[UUID] = set()

    for attempt in range(1, max_attempts + 1):
        proxy = await select_proxy(tried)
        if proxy is None:
            # Pool exhausted before the retry budget was spent.
            report.fallback_reason = "no_healthy_proxy_available"
            break

        # UUIDMixin annotates ``id`` with SQLAlchemy's UUID sqltype, so
        # cast to the runtime type (``uuid.UUID``) mypy expects here.
        if proxy.id is not None:
            tried.add(cast(UUID, proxy.id))

        label = proxy_label(proxy)
        try:
            response = fetch(build_fetch_proxy_kwargs(proxy, profile))
        except Exception as exc:
            report.attempts.append(
                ProxyAttemptLog(
                    attempt=attempt,
                    proxy=label,
                    ok=False,
                    error=_sanitize_error(exc, proxy),
                )
            )
            logger.warning(
                "Proxy fetch attempt %d/%d via %s failed: %s",
                attempt,
                max_attempts,
                label,
                _sanitize_error(exc, proxy),
            )
            continue

        report.used_proxy = label
        report.attempts.append(ProxyAttemptLog(attempt=attempt, proxy=label, ok=True))
        logger.info(
            "Proxy fetch attempt %d/%d via %s succeeded",
            attempt,
            max_attempts,
            label,
        )
        return response

    if not report.fallback_reason:
        report.fallback_reason = "all_proxy_attempts_failed"

    # No usable proxy left — proceed without one, as documented in the
    # README, and make the fallback visible in the activity log.
    report.fell_back_direct = True
    logger.warning(
        "Falling back to a direct (proxyless) fetch (reason=%s) after %d "
        "proxy attempt(s)",
        report.fallback_reason,
        len(report.attempts),
    )
    return fetch({})
