"""Schedule-trigger and polling logic tests against in-memory SQLite.

Covers the pieces Celery Beat's 30-second poll leans on:

- ``ScheduleService._compute_next_run``: cron vs interval vs neither,
  invalid cron → ``None``.
- ``ScheduleService.trigger`` for crawl schedules: one CrawlJob per
  *active* (config-link, URL) pair, tracking fields bumped, and the
  no-work early return.
- ``ScheduleService.trigger`` for proxy_source schedules: no jobs, but
  tracking fields still advance.

PostgreSQL is never touched — the schema is replayed on
``sqlite+aiosqlite`` via the ``db_session`` fixture.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ScheduleNotFoundError
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_schedule import CrawlSchedule
from app.models.enums import CrawlJobStatus, ScheduleType
from app.models.proxy_source_config import ProxySourceConfig
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_proxy_source_link import ScheduleProxySourceLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.services.schedule_service import ScheduleService

_UTC = UTC
_PAST = datetime.now(_UTC) - timedelta(hours=1)


def _tag() -> str:
    """Unique suffix so every seed row satisfies unique constraints."""
    return uuid.uuid4().hex[:10]


async def _reload(session: AsyncSession, model: Any, key: Any) -> Any:
    """Force a fresh SELECT, bypassing the commit-skipped identity map."""
    session.expire_all()  # sync call — never await this
    return await session.get(model, key)


async def _seed_crawl_schedule(
    session: AsyncSession,
    *,
    urls: list[str],
    active_flags: list[bool] | None = None,
    is_active: bool = True,
    next_run_at: datetime | None = _PAST,
) -> CrawlSchedule:
    """Seed schedule → config link → URL targets as one commit.

    Returns the schedule.  Column values are fine to read afterwards
    (the fixture session uses ``expire_on_commit=False``), but *never*
    touch a lazy relationship on a seed row — accessing an unloaded
    ``instrumented`` relationship in an async session raises
    MissingGreenlet; carry ids/values through the return instead.
    """
    config = CrawlConfiguration(name=f"cfg-{_tag()}")
    session.add(config)
    await session.flush()

    schedule = CrawlSchedule(
        name=f"schedule-{_tag()}",
        schedule_type=ScheduleType.CRAWL,
        cron_expression="*/5 * * * *",
        next_run_at=next_run_at,
        is_active=is_active,
    )
    session.add(schedule)
    await session.flush()

    link = ScheduleConfigLink(schedule_id=schedule.id, config_id=config.id)
    session.add(link)
    await session.flush()

    flags = active_flags if active_flags is not None else [True] * len(urls)
    for url, active in zip(urls, flags, strict=True):
        session.add(
            ScheduleUrlTarget(
                config_link_id=link.id, url=url, is_active=active
            )
        )
    await session.commit()
    loaded = await session.get(CrawlSchedule, schedule.id)
    assert loaded is not None  # commit-then-reload sanity
    return loaded


class TestComputeNextRun:
    def test_cron_expression_resolves_to_future(self) -> None:
        now = datetime.now(_UTC)
        nxt = ScheduleService._compute_next_run("*/5 * * * *", None)
        assert nxt is not None
        assert nxt > now

    def test_invalid_cron_returns_none(self) -> None:
        assert ScheduleService._compute_next_run("not a cron", None) is None

    def test_interval_adds_seconds(self) -> None:
        before = datetime.now(_UTC).timestamp()
        nxt = ScheduleService._compute_next_run(None, 120)
        assert nxt is not None
        after = datetime.now(_UTC).timestamp()
        assert before + 120 <= nxt.timestamp() <= after + 121

    def test_neither_definition_returns_none(self) -> None:
        assert ScheduleService._compute_next_run(None, None) is None


class TestTriggerCrawlSchedule:
    async def test_creates_job_per_active_url(
        self, db_session: AsyncSession
    ) -> None:
        schedule = await _seed_crawl_schedule(
            db_session,
            urls=["https://a.example/1", "https://a.example/2"],
            active_flags=[True, True],
        )
        link = (
            await db_session.execute(
                select(ScheduleConfigLink).where(
                    ScheduleConfigLink.schedule_id == schedule.id
                )
            )
        ).scalar_one()
        service = ScheduleService(db_session)

        jobs = await service.trigger(cast(uuid.UUID, schedule.id))

        assert len(jobs) == 2
        assert {job.target_url for job in jobs} == {
            "https://a.example/1",
            "https://a.example/2",
        }
        assert all(job.status is CrawlJobStatus.QUEUED for job in jobs)
        assert all(
            job.crawl_configuration_id == link.config_id for job in jobs
        )
        assert all(job.queue == schedule.default_queue for job in jobs)

    async def test_inactive_urls_skipped(
        self, db_session: AsyncSession
    ) -> None:
        schedule = await _seed_crawl_schedule(
            db_session,
            urls=["https://a.example/1", "https://a.example/2"],
            active_flags=[True, False],
        )
        service = ScheduleService(db_session)

        jobs = await service.trigger(cast(uuid.UUID, schedule.id))

        assert [job.target_url for job in jobs] == ["https://a.example/1"]

    async def test_tracking_fields_advance(
        self, db_session: AsyncSession
    ) -> None:
        schedule = await _seed_crawl_schedule(
            db_session, urls=["https://a.example/1"]
        )
        service = ScheduleService(db_session)

        await service.trigger(cast(uuid.UUID, schedule.id))

        refreshed_any = await _reload(db_session, CrawlSchedule, schedule.id)
        assert refreshed_any is not None
        refreshed: CrawlSchedule = refreshed_any
        assert refreshed.run_count == 1
        assert refreshed.last_run_at is not None
        # Cron */5 → next run strictly in the future (was in the past).
        assert refreshed.next_run_at is not None
        # SQLite stores DateTime columns timezone-naive; re-anchor to UTC
        # before comparing with tz-aware "now".
        stored_next_run = refreshed.next_run_at.replace(tzinfo=_UTC)
        now = datetime.now(_UTC)
        assert now <= stored_next_run <= now + timedelta(minutes=5)

    async def test_no_active_urls_returns_early_and_skips_tracking(
        self, db_session: AsyncSession
    ) -> None:
        schedule = await _seed_crawl_schedule(
            db_session,
            urls=["https://a.example/1"],
            active_flags=[False],
        )
        service = ScheduleService(db_session)

        jobs = await service.trigger(cast(uuid.UUID, schedule.id))

        assert jobs == []
        refreshed = await db_session.get(CrawlSchedule, schedule.id)
        assert refreshed is not None
        assert refreshed.run_count == 0
        assert refreshed.last_run_at is None

    async def test_missing_schedule_raises(
        self, db_session: AsyncSession
    ) -> None:
        service = ScheduleService(db_session)
        with pytest.raises(ScheduleNotFoundError):
            await service.trigger(uuid.uuid4())


class TestTriggerProxySourceSchedule:
    async def test_returns_empty_but_advances_tracking(
        self, db_session: AsyncSession
    ) -> None:
        source = ProxySourceConfig(
            name=f"source-{_tag()}", url="https://lists.example/proxies"
        )
        schedule = CrawlSchedule(
            name=f"pschedule-{_tag()}",
            schedule_type=ScheduleType.PROXY_SOURCE,
            interval_seconds=3600,
        )
        db_session.add_all([source, schedule])
        await db_session.flush()
        db_session.add(
            ScheduleProxySourceLink(
                schedule_id=schedule.id, proxy_source_id=source.id
            )
        )
        await db_session.commit()

        service = ScheduleService(db_session)
        jobs = await service.trigger(cast(uuid.UUID, schedule.id))

        assert jobs == []  # caller enqueues fetch+validate tasks itself
        refreshed = await db_session.get(CrawlSchedule, schedule.id)
        assert refreshed is not None
        assert refreshed.run_count == 1
        assert refreshed.next_run_at is not None


class TestGetById:
    async def test_raises_for_unknown(
        self, db_session: AsyncSession
    ) -> None:
        service = ScheduleService(db_session)
        with pytest.raises(ScheduleNotFoundError):
            await service.get_by_id(uuid.uuid4())

    async def test_returns_seeded_schedule(
        self, db_session: AsyncSession
    ) -> None:
        schedule = await _seed_crawl_schedule(
            db_session, urls=["https://a.example/1"]
        )
        service = ScheduleService(db_session)
        loaded = await service.get_by_id(cast(uuid.UUID, schedule.id))
        assert loaded.name == schedule.name
        assert [
            target.url for target in loaded.config_links[0].url_targets
        ] == ["https://a.example/1"]
