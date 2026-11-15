"""End-to-end test for the Celery Beat schedule-polling task.

``pilgrim.schedule.check_schedules`` builds its own async engine from
settings, so the test monkeypatches ``create_async_engine`` (exactly the
seam the mocked scrape-task tests use) to point that engine at a
scratch SQLite file seeded with the full schema.  Celery fan-out
(``run_crawl_job`` / ``fetch_proxy_source``) is recorded, never
executed — no Redis, no PostgreSQL, no Scrapling.

The tests are *synchronous* on purpose: the task body calls
``asyncio.run`` itself, which can't run inside pytest-asyncio's loop.
"""

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from sqlalchemy.ext.asyncio import (
    async_sessionmaker,
    create_async_engine,
)

from app.models import Base
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_schedule import CrawlSchedule
from app.models.enums import ScheduleType
from app.models.proxy_source_config import ProxySourceConfig
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_proxy_source_link import ScheduleProxySourceLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.workers.tasks.proxy import fetch_proxy_source
from app.workers.tasks.schedule import check_schedules
from app.workers.tasks.scrape import run_crawl_job

_UTC = UTC
_PAST = datetime.now(_UTC) - timedelta(hours=1)
_FUTURE = datetime.now(_UTC) + timedelta(hours=1)


def _sqlite_url(db_file: Path) -> str:
    """File-qualified URL for the scratch SQLite database."""
    return f"sqlite+aiosqlite:///{db_file}"


def _engine_for(db_file: Path, real_create_engine: Any) -> Any:
    """Stand-in for create_async_engine targeting the scratch file."""

    def engine_factory(_url: Any, **_kw: Any) -> Any:
        return real_create_engine(_sqlite_url(db_file))

    return engine_factory


def patch_engine_to_scratch_file(monkeypatch: Any, db_file: Path) -> None:
    real_create_engine = create_async_engine
    monkeypatch.setattr(
        "sqlalchemy.ext.asyncio.create_async_engine",
        _engine_for(db_file, real_create_engine),
    )


async def _run_with_session(db_file: Path, fn: Any) -> Any:
    """Open a session on the scratch file, run ``fn(session, factory)``,
    return its result.  The engine is disposed before the loop closes so
    each ``asyncio.run`` gets its own connections."""
    engine = create_async_engine(_sqlite_url(db_file))
    try:
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            return await fn(session)
    finally:
        await engine.dispose()


async def _create_schema(db_file: Path) -> None:
    engine = create_async_engine(_sqlite_url(db_file))
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


async def _seed_crawl_schedule(
    session: Any, *, is_active: bool, next_run_at: datetime
) -> Any:
    """Seed due schedule → config link → URL target; returns schedule id."""
    config = CrawlConfiguration(name=f"cfg-{uuid.uuid4().hex[:10]}")
    session.add(config)
    await session.flush()
    schedule = CrawlSchedule(
        name=f"schedule-{uuid.uuid4().hex[:10]}",
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
    session.add(
        ScheduleUrlTarget(
            config_link_id=link.id,
            url="https://example.com/due-page",
            is_active=True,
        )
    )
    await session.commit()
    return schedule.id


class EnqueueRecorder:
    """Records every ``.apply_async(**kwargs)`` call made by the poller."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def record(self, *args: Any, **kwargs: Any) -> Any:
        assert args == (), "poller must fan out with keyword args only"
        self.calls.append(kwargs)
        return None

    def __len__(self) -> int:
        return len(self.calls)


def _count_jobs_schema() -> Any:
    from sqlalchemy import func, select

    from app.models.crawl_job import CrawlJob

    return select(func.count()).select_from(CrawlJob)


class TestPollDueCrawlSchedule:
    def test_due_schedule_creates_jobs_and_enqueues(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        db_file = tmp_path / "poll-crawl.sqlite3"
        asyncio.run(_create_schema(db_file))

        async def _seed(session: Any) -> tuple[str, Any]:
            schedule_id = await _seed_crawl_schedule(
                session, is_active=True, next_run_at=_PAST
            )
            return schedule_id, None

        schedule_id, _ = asyncio.run(_run_with_session(db_file, _seed))

        patch_engine_to_scratch_file(monkeypatch, db_file)
        enqueued = EnqueueRecorder()
        monkeypatch.setattr(run_crawl_job, "apply_async", enqueued.record)

        result = check_schedules()

        assert result == {"triggered": 1}
        assert len(enqueued) == 1
        fanout = enqueued.calls[0]
        assert fanout["queue"] == "crawl_default"

        async def _check(session: Any) -> Any:
            from sqlalchemy import select

            from app.models.crawl_job import CrawlJob

            total = (
                await session.execute(_count_jobs_schema())
            ).scalar_one()
            assert total == 1
            job = (
                await session.execute(select(CrawlJob))
            ).scalar_one()
            assert job.target_url == "https://example.com/due-page"
            schedule_row = await session.get(CrawlSchedule, schedule_id)
            assert schedule_row is not None
            assert schedule_row.run_count == 1
            assert schedule_row.next_run_at is not None
            # SQLite round-trips DateTime as naive — re-anchor to UTC.
            assert (
                schedule_row.next_run_at.replace(tzinfo=_UTC) > _PAST
            )
            return job.id

        created_job_id = asyncio.run(_run_with_session(db_file, _check))
        # The poller enqueued the freshly created CrawlJob, not the
        # schedule.
        assert fanout["args"] == [str(created_job_id)]

    def test_not_due_or_inactive_schedules_are_ignored(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        db_file = tmp_path / "poll-idle.sqlite3"
        asyncio.run(_create_schema(db_file))

        async def _seed(session: Any) -> None:
            await _seed_crawl_schedule(
                session, is_active=True, next_run_at=_FUTURE
            )
            await _seed_crawl_schedule(
                session, is_active=False, next_run_at=_PAST
            )

        asyncio.run(_run_with_session(db_file, _seed))

        patch_engine_to_scratch_file(monkeypatch, db_file)
        enqueued = EnqueueRecorder()
        monkeypatch.setattr(run_crawl_job, "apply_async", enqueued.record)

        result = check_schedules()

        assert result == {"triggered": 0}
        assert len(enqueued) == 0

        async def _check(session: Any) -> None:
            total = (
                await session.execute(_count_jobs_schema())
            ).scalar_one()
            assert total == 0

        asyncio.run(_run_with_session(db_file, _check))


class TestPollDueProxySourceSchedule:
    def test_due_proxy_schedule_enqueues_fetch_tasks(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        db_file = tmp_path / "poll-proxy.sqlite3"
        asyncio.run(_create_schema(db_file))

        async def _seed(session: Any) -> tuple[Any, Any]:
            source = ProxySourceConfig(
                name=f"source-{uuid.uuid4().hex[:10]}",
                url="https://lists.example/proxies",
            )
            session.add(source)
            await session.flush()
            schedule = CrawlSchedule(
                name=f"pschedule-{uuid.uuid4().hex[:10]}",
                schedule_type=ScheduleType.PROXY_SOURCE,
                interval_seconds=3600,
                next_run_at=_PAST,
            )
            session.add(schedule)
            await session.flush()
            session.add(
                ScheduleProxySourceLink(
                    schedule_id=schedule.id, proxy_source_id=source.id
                )
            )
            await session.commit()
            return schedule.id, source.id

        schedule_id, source_id = asyncio.run(
            _run_with_session(db_file, _seed)
        )

        patch_engine_to_scratch_file(monkeypatch, db_file)
        enqueued = EnqueueRecorder()
        monkeypatch.setattr(fetch_proxy_source, "apply_async", enqueued.record)

        result = check_schedules()

        assert result == {"triggered": 1}
        assert len(enqueued) == 1
        fanout = enqueued.calls[0]
        assert fanout["args"] == [str(source_id)]
        assert fanout["queue"] == "maintenance"
        assert "link" in fanout  # fetch chains into validate_proxies

        async def _check(session: Any) -> None:
            schedule_row = await session.get(CrawlSchedule, schedule_id)
            assert schedule_row is not None
            assert schedule_row.run_count == 1
            assert schedule_row.next_run_at is not None

        asyncio.run(_run_with_session(db_file, _check))


class TestPollEmptyDatabase:
    def test_no_schedules_returns_zero(
        self, tmp_path: Path, monkeypatch: Any
    ) -> None:
        db_file = tmp_path / "poll-empty.sqlite3"
        asyncio.run(_create_schema(db_file))

        patch_engine_to_scratch_file(monkeypatch, db_file)
        enqueued = EnqueueRecorder()
        monkeypatch.setattr(run_crawl_job, "apply_async", enqueued.record)
        monkeypatch.setattr(fetch_proxy_source, "apply_async", enqueued.record)

        result = check_schedules()

        assert result == {"triggered": 0}
        assert len(enqueued) == 0
