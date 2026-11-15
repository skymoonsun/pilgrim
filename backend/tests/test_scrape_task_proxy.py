"""Mocked end-to-end tests for ``pilgrim.scrape.run_job`` proxy rotation.

The task's Celery body runs against fakes: no PostgreSQL, no Redis, no
Scrapling — the database engine factory, the job service, the proxy
service and the fetcher are all patched at the module boundary. These
tests lock in the promised behaviour of ``use_proxy = true``:

- the fetch is routed through a proxy from the healthy pool,
- a failed proxy attempt rotates to a *different* proxy,
- an exhausted pool falls back to a direct fetch and says so in the
  job's ``result_summary['proxy']`` activity-log entry.
"""

from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from app.models.enums import CrawlJobStatus, ProxyProtocol, ScraperProfile
from app.models.valid_proxy import ValidProxy
from app.workers.tasks.scrape import run_crawl_job

# ── Fakes ───────────────────────────────────────────────────────────


class _FakeExecuteResult:
    def scalars(self) -> list:
        return []

    def scalar_one_or_none(self) -> None:
        return None


class _FakeSession:
    """Just enough of an AsyncSession for the task body."""

    def __init__(self, config: Any) -> None:
        self._config = config
        self.added: list[Any] = []

    async def run_sync(self, fn: Any) -> Any:
        return self._config

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    async def execute(self, *args: Any, **kwargs: Any) -> _FakeExecuteResult:
        return _FakeExecuteResult()

    async def commit(self) -> None:
        pass

    async def refresh(self, *args: Any) -> None:
        pass


class _SessionContext:
    def __init__(self, session: _FakeSession) -> None:
        self._session = session

    async def __aenter__(self) -> _FakeSession:
        return self._session

    async def __aexit__(self, *exc: Any) -> bool:
        return False


class _FakeJobService:
    """Records status transitions handed to ``update_status``."""

    def __init__(self, session: Any, job: Any) -> None:
        self.session = session
        self.job = job
        self.updates: list[tuple[Any, dict]] = []

    async def get_by_id(self, job_id: Any) -> Any:
        return self.job

    async def update_status(self, job_id: Any, status: Any, **kwargs: Any) -> Any:
        self.updates.append((status, kwargs))
        return self.job


class _FakeProxyService:
    """Serves healthy proxies in order, honouring exclusions."""

    def __init__(self, proxies: list[ValidProxy]) -> None:
        self.proxies = proxies
        self.exclusion_calls: list[set] = []

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


class _RecordingFetcher:
    """Scrapling fetcher double: records every ``get()`` call."""

    def __init__(self, fail_proxies: set[str]) -> None:
        self.fail_proxies = fail_proxies
        self.calls: list[tuple[str, dict]] = []

    def get(self, url: str, **kwargs: Any) -> Any:
        self.calls.append((url, dict(kwargs)))
        proxy = kwargs.get("proxy")
        if proxy in self.fail_proxies:
            raise ConnectionError(f"proxy {proxy} unreachable")
        return SimpleNamespace(status=200, html="<html></html>")


# ── Test scaffolding ─────────────────────────────────────────────────


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
        scraper_profile=ScraperProfile.FETCHER,
        fetch_options={"timeout": 30, "proxy_retries": 3},
        extraction_spec={"fields": {}},  # → extract_data returns {}
        use_proxy=use_proxy,
    )


@pytest.fixture
def eager_celery():
    """Run the task body in-process and propagate exceptions."""
    from app.workers.celery_app import celery_app

    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield celery_app
    celery_app.conf.update(task_always_eager=False, task_eager_propagates=False)


def _run_task(
    config: Any,
    proxies: list[ValidProxy],
    fail_proxies: set[str],
) -> tuple[_FakeJobService, _RecordingFetcher, _FakeProxyService]:
    """Execute ``run_crawl_job`` against fakes; return the doubles used."""
    job = SimpleNamespace(
        id=uuid4(),
        target_url="https://example.com/page",
        crawl_configuration_id=uuid4(),
        crawl_configuration=config,
    )
    session = _FakeSession(config)
    fetcher = _RecordingFetcher(fail_proxies)
    proxy_service = _FakeProxyService(proxies)

    job_service: dict[str, _FakeJobService] = {}

    class _BoundJobService(_FakeJobService):
        def __init__(self, session_arg: Any) -> None:
            super().__init__(session_arg, job)
            job_service["instance"] = self

    fake_engine = SimpleNamespace(dispose=_async_noop)

    with (
        patch(
            "sqlalchemy.ext.asyncio.create_async_engine",
            return_value=fake_engine,
        ),
        patch(
            "sqlalchemy.ext.asyncio.async_sessionmaker",
            side_effect=_sessionmaker_stub(session),
        ),
        patch(
            "app.services.crawl_job_service.CrawlJobService",
            _BoundJobService,
        ),
        patch(
            "app.services.valid_proxy_service.ValidProxyService",
            lambda session_arg: proxy_service,
        ),
        patch(
            "app.crawlers.factory.create_fetcher",
            lambda profile, options: fetcher,
        ),
    ):
        run_crawl_job.apply(args=[str(job.id)])

    assert "instance" in job_service, "job service was never constructed"
    return job_service["instance"], fetcher, proxy_service


async def _async_noop() -> None:
    pass


def _sessionmaker_stub(session: _FakeSession) -> Any:
    """Build a stand-in for ``async_sessionmaker(engine, ...)``.

    The returned sessionmaker yields a factory whose call opens the fake
    session as an async context manager, mirroring
    ``async with session_factory() as session``.
    """

    def sessionmaker(*args: Any, **kwargs: Any) -> Any:
        def factory(*a: Any, **kw: Any) -> _SessionContext:
            return _SessionContext(session)

        return factory

    return sessionmaker


# ── Tests ────────────────────────────────────────────────────────────


class TestRunJobProxyRotation:
    def test_use_proxy_fetches_through_healthy_pool(self, eager_celery) -> None:
        proxy = make_proxy()
        service, fetcher, _ = _run_task(
            make_config(use_proxy=True), [proxy], fail_proxies=set()
        )

        # The task completed successfully.
        statuses = [status for status, _ in service.updates]
        assert statuses == [CrawlJobStatus.RUNNING, CrawlJobStatus.SUCCEEDED]

        # The fetch really went through the proxy.
        assert fetcher.calls == [
            ("https://example.com/page", {"proxy": "http://203.0.113.10:8080"})
        ]

        # The success summary records the proxy story.
        success_kwargs = service.updates[-1][1]
        proxy_summary = success_kwargs["result_summary"]["proxy"]
        assert proxy_summary["enabled"] is True
        assert proxy_summary["used"] == "http://203.0.113.10:8080"
        assert proxy_summary["fell_back_direct"] is False
        assert [a["ok"] for a in proxy_summary["attempts"]] == [True]

    def test_failed_proxy_rotates_to_next_then_succeeds(self, eager_celery) -> None:
        first = make_proxy(ip="203.0.113.1")
        second = make_proxy(ip="203.0.113.2")
        service, fetcher, proxy_service = _run_task(
            make_config(use_proxy=True),
            [first, second],
            fail_proxies={"http://203.0.113.1:8080"},
        )

        statuses = [status for status, _ in service.updates]
        assert statuses == [CrawlJobStatus.RUNNING, CrawlJobStatus.SUCCEEDED]

        # Both proxies were used, in rotation order.
        assert [url for url, _ in fetcher.calls] == [
            "https://example.com/page",
            "https://example.com/page",
        ]
        assert [kwargs["proxy"] for _, kwargs in fetcher.calls] == [
            "http://203.0.113.1:8080",
            "http://203.0.113.2:8080",
        ]

        # The second selection excluded the failed proxy.
        assert proxy_service.exclusion_calls[1] == {first.id}

        success_kwargs = service.updates[-1][1]
        proxy_summary = success_kwargs["result_summary"]["proxy"]
        assert proxy_summary["used"] == "http://203.0.113.2:8080"
        assert proxy_summary["attempts"][0]["ok"] is False
        assert proxy_summary["attempts"][1]["ok"] is True
        assert proxy_summary["fell_back_direct"] is False

    def test_exhausted_pool_falls_back_to_direct_and_logs_it(
        self, eager_celery
    ) -> None:
        only = make_proxy(ip="203.0.113.1")
        service, fetcher, _ = _run_task(
            make_config(use_proxy=True),
            [only],
            fail_proxies={"http://203.0.113.1:8080"},
        )

        statuses = [status for status, _ in service.updates]
        assert statuses == [CrawlJobStatus.RUNNING, CrawlJobStatus.SUCCEEDED]

        # One proxied attempt, then a direct retry without proxy kwargs.
        assert fetcher.calls[0] == (
            "https://example.com/page",
            {"proxy": "http://203.0.113.1:8080"},
        )
        assert fetcher.calls[1] == ("https://example.com/page", {})

        success_kwargs = service.updates[-1][1]
        proxy_summary = success_kwargs["result_summary"]["proxy"]
        assert proxy_summary["used"] is None
        assert proxy_summary["fell_back_direct"] is True
        assert proxy_summary["fallback_reason"] == "no_healthy_proxy_available"
        assert proxy_summary["attempts"][0]["ok"] is False

    def test_use_proxy_false_fetches_directly(self, eager_celery) -> None:
        service, fetcher, proxy_service = _run_task(
            make_config(use_proxy=False), [make_proxy()], fail_proxies=set()
        )

        statuses = [status for status, _ in service.updates]
        assert statuses == [CrawlJobStatus.RUNNING, CrawlJobStatus.SUCCEEDED]
        assert fetcher.calls == [("https://example.com/page", {})]
        # The proxy pool must not even be consulted.
        assert proxy_service.exclusion_calls == []
        # No proxy section in the summary when rotation is disabled.
        success_kwargs = service.updates[-1][1]
        assert "proxy" not in success_kwargs["result_summary"]

    def test_all_fetches_failing_marks_job_failed_with_proxy_story(
        self, eager_celery
    ) -> None:
        only = make_proxy(ip="203.0.113.1")
        job = SimpleNamespace(
            id=uuid4(),
            target_url="https://example.com/page",
            crawl_configuration_id=uuid4(),
            crawl_configuration=make_config(use_proxy=True),
        )
        session = _FakeSession(job.crawl_configuration)
        fetcher = _RecordingFetcher({"*"})  # every fetch fails
        proxy_service = _FakeProxyService([only])
        job_service: dict[str, _FakeJobService] = {}

        class _BoundJobService(_FakeJobService):
            def __init__(self, session_arg: Any) -> None:
                super().__init__(session_arg, job)
                job_service["instance"] = self

        def _fail_on_get(url: str, **kwargs: Any) -> Any:
            fetcher.calls.append((url, dict(kwargs)))
            if kwargs:
                raise ConnectionError("proxy broken")
            raise RuntimeError("target unreachable")

        fake_engine = SimpleNamespace(dispose=_async_noop)

        with (
            patch(
                "sqlalchemy.ext.asyncio.create_async_engine",
                return_value=fake_engine,
            ),
            patch(
                "sqlalchemy.ext.asyncio.async_sessionmaker",
                side_effect=_sessionmaker_stub(session),
            ),
            patch(
                "app.services.crawl_job_service.CrawlJobService",
                _BoundJobService,
            ),
            patch(
                "app.services.valid_proxy_service.ValidProxyService",
                lambda session_arg: proxy_service,
            ),
            patch(
                "app.crawlers.factory.create_fetcher",
                lambda profile, options: SimpleNamespace(get=_fail_on_get),
            ),
        ):
            # RuntimeError is not in autoretry_for, so it propagates.
            with pytest.raises(RuntimeError, match="target unreachable"):
                run_crawl_job.apply(args=[str(job.id)])

        statuses = [status for status, _ in job_service["instance"].updates]
        assert statuses == [CrawlJobStatus.RUNNING, CrawlJobStatus.FAILED]
        failure_kwargs = job_service["instance"].updates[-1][1]
        assert failure_kwargs["error_message"] == "target unreachable"
        # The failed job still tells the proxy story.
        proxy_summary = failure_kwargs["result_summary"]["proxy"]
        assert proxy_summary["fell_back_direct"] is True
        assert proxy_summary["attempts"][0]["ok"] is False
