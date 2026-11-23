"""``factory.fetch_off_loop`` — browser profiles must run off the loop.

Regression for the E2E failure: a stealth crawl job inside the Celery
worker (``asyncio.run``) hit Playwright's sync-in-loop wall —
``It looks like you are using Playwright Sync API inside the asyncio
loop.`` — because the scrapling fetch ran on the event-loop thread.
``fetch_off_loop`` moves the sync ``fetcher.get`` call onto an executor
thread, where ``get_running_loop()`` raises instead of returning a loop.
"""

from __future__ import annotations

import asyncio

import pytest

from app.crawlers.factory import fetch_off_loop

_LOOP_WALL = (
    "It looks like you are using Playwright Sync API inside the asyncio loop."
)


class _LoopSensitiveFetcher:
    """Fake scrapling fetcher mirroring Patchright's sync API behaviour."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def get(self, url: str, **kwargs: object) -> str:
        # Patchright raises precisely when called on a thread that runs an
        # event loop.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            self.calls.append(url)
            return f"ok:{url}"
        raise RuntimeError(_LOOP_WALL)


@pytest.mark.asyncio
async def test_fetch_off_loop_runs_browser_fetch_off_the_loop() -> None:
    """The sync-in-loop wall is passed via the executor thread."""
    fetcher = _LoopSensitiveFetcher()

    # Sanity: a direct call from the loop thread reproduces the real bug.
    with pytest.raises(RuntimeError, match="Playwright Sync API"):
        fetcher.get("https://www.trustpilot.com/review/kinguin.net")

    response = await fetch_off_loop(
        fetcher, "https://www.trustpilot.com/review/kinguin.net"
    )
    assert response == "ok:https://www.trustpilot.com/review/kinguin.net"
    assert fetcher.calls == ["https://www.trustpilot.com/review/kinguin.net"]


@pytest.mark.asyncio
async def test_fetch_off_loop_forwards_request_kwargs() -> None:
    """Request kwargs ride through (fetch_options + request kwargs)."""

    class _KwargsFetcher(_LoopSensitiveFetcher):
        seen: dict[str, object] = {}

        def get(self, url: str, **kwargs: object) -> str:  # noqa: D102
            self.seen = dict(kwargs)
            return super().get(url, **kwargs)

    fetcher = _KwargsFetcher()
    response = await fetch_off_loop(
        fetcher,
        "https://www.trustpilot.com/review/kinguin.net",
        timeout=60,
        network_idle=True,
    )
    assert response == "ok:https://www.trustpilot.com/review/kinguin.net"
    assert fetcher.seen == {"timeout": 60, "network_idle": True}
