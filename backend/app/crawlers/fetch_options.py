"""App-owned fetch-option keys on the Pilgrim ↔ Scrapling boundary.

Every ``create_fetcher`` call site routes a ``fetch_options`` dict
towards a Scrapling fetcher constructor: the Celery task
``pilgrim.scrape.run_job``, the synchronous ``ScrapeService.execute``
(``POST /api/v1/scrape``) and the AI verification pipeline
(``AIService.verify_extraction_spec``).  Scrapling's fetchers take
strict keyword arguments, so an app-owned key raises ``TypeError`` at
``create_fetcher`` time and crashes every fetch before it starts (e.g.
``FetcherSession(**{"proxy_retries": 3})`` on scrapling 0.5).

App-owned keys are consumed by Pilgrim itself and must therefore never
be forwarded to a Scrapling fetcher constructor.  ``proxy_retries``
(the proxy-rotation budget) is the one app-owned key so far: it is
read from the RAW options by
``app.services.proxy_rotation.resolve_proxy_attempts`` (worker path —
the sync/AI paths have no rotation budget).  Any other key is a genuine
Scrapling kwarg (``timeout``, ``impersonate``, ``stealthy_headers``,
``follow_redirects``, ...) and passes through unchanged.
"""

from __future__ import annotations

from typing import Any

APP_OWNED_FETCH_KEYS: frozenset[str] = frozenset({"proxy_retries"})


def strip_app_owned_keys(fetch_options: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of *fetch_options* without the app-owned keys.

    The input dict is NOT mutated — the raw options stay available
    (``resolve_proxy_attempts`` reads ``proxy_retries`` from them).
    """
    return {
        key: value
        for key, value in (fetch_options or {}).items()
        if key not in APP_OWNED_FETCH_KEYS
    }
