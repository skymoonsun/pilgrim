"""Trustpilot schedule gating — the trigger-level ToS fence.

Celery Beat (``app.workers.tasks.schedule``) and the manual API trigger
endpoint both call ``ScheduleService.trigger``; the gate in
``_trigger_crawl`` protects both entry points: when a linked config is
the Trustpilot one and ``PILGRIM_RUN_TRUSTPILOT`` is off, zero jobs are
created and the schedule's tracking fields stay untouched.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_job import CrawlJob
from app.models.crawl_schedule import CrawlSchedule
from app.models.enums import ScheduleType
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.services.schedule_service import ScheduleService

_PAST = datetime.now(UTC) - timedelta(days=1)
_TRUSTPILOT_JOB_URL = "https://www.trustpilot.com/review/kinguin.net"


def _tag() -> str:
    """Unique suffix so every seed row satisfies unique constraints."""
    return uuid.uuid4().hex[:10]


async def _seed_schedule(
    session: AsyncSession,
    config_names: list[str],
) -> UUID:
    """Schedule → config links (+ one active URL each), active with
    ``next_run_at`` in the past — exactly what the beat poller selects.

    Returns the schedule id; never touch lazy relationships on a seeded
    row from an async session (MissingGreenlet) — carry ids back.
    """
    schedule = CrawlSchedule(
        name=f"schedule-{_tag()}",
        schedule_type=ScheduleType.CRAWL,
        cron_expression="0 4 * * 1",
        next_run_at=_PAST,
        is_active=True,
    )
    session.add(schedule)
    await session.flush()

    for priority, config_name in enumerate(config_names):
        # The Trustpilot config name must match the setting EXACTLY —
        # randomise only the decoy names for unique constraints.
        trusted = config_name == _trust_config_name()
        config = CrawlConfiguration(
            name=config_name if trusted else f"{config_name}-{_tag()}"
        )
        session.add(config)
        await session.flush()
        link = ScheduleConfigLink(
            schedule_id=schedule.id, config_id=config.id, priority=priority
        )
        session.add(link)
        await session.flush()
        session.add(
            ScheduleUrlTarget(
                config_link_id=link.id, url=_TRUSTPILOT_JOB_URL, is_active=True
            )
        )
    await session.commit()
    return cast(UUID, schedule.id)


async def _job_count(session: AsyncSession, schedule_id: UUID) -> int:
    result = await session.execute(
        select(CrawlJob).where(CrawlJob.target_url == _TRUSTPILOT_JOB_URL)
    )
    return len(list(result.scalars()))


def _trust_config_name() -> str:
    return get_settings().trustpilot_config_name


class TestTrustpilotGate:
    async def test_gated_trigger_creates_no_jobs_and_leaves_schedule(
        self, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture,
    ) -> None:
        # Default env: PILGRIM_RUN_TRUSTPILOT unset → gated.
        monkeypatch.delenv("PILGRIM_RUN_TRUSTPILOT", raising=False)
        schedule_id = await _seed_schedule(
            db_session, [_trust_config_name()]
        )

        with caplog.at_level(logging.WARNING):
            jobs = await ScheduleService(db_session).trigger(schedule_id)

        assert jobs == []
        assert await _job_count(db_session, schedule_id) == 0
        refreshed = await db_session.get(CrawlSchedule, schedule_id)
        assert refreshed is not None
        assert refreshed.run_count == 0
        assert refreshed.last_run_at is None
        # SQLite stores DateTime columns timezone-naive; re-anchor to UTC
        # before comparing with tz-aware values (same as the trigger tests).
        assert refreshed.next_run_at is not None
        assert refreshed.next_run_at.replace(tzinfo=UTC) == _PAST
        message = "trustpilot crawl gated — set PILGRIM_RUN_TRUSTPILOT=1 to enable"
        assert message in caplog.text

    async def test_beat_and_manual_share_the_gate(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PILGRIM_RUN_TRUSTPILOT", raising=False)
        schedule_id = await _seed_schedule(
            db_session, [_trust_config_name()]
        )
        service = ScheduleService(db_session)

        # Beat path: the poller calls trigger(schedule.id) for every
        # active schedule with next_run_at in the past.
        assert await service.trigger(schedule_id) == []
        # Manual API path: POST /schedules/{id}/trigger → same method.
        assert await service.trigger(schedule_id) == []

    async def test_enabled_trigger_advances_tracking(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setenv("PILGRIM_RUN_TRUSTPILOT", "1")
        schedule_id = await _seed_schedule(
            db_session, [_trust_config_name()]
        )

        jobs = await ScheduleService(db_session).trigger(schedule_id)

        assert len(jobs) == 1
        assert jobs[0].target_url == _TRUSTPILOT_JOB_URL
        refreshed = await db_session.get(CrawlSchedule, schedule_id)
        assert refreshed is not None
        assert refreshed.run_count == 1
        assert refreshed.last_run_at is not None
        assert refreshed.next_run_at is not None
        assert refreshed.next_run_at.replace(tzinfo=UTC) > _PAST

    async def test_any_linked_trust_config_gates_the_schedule(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PILGRIM_RUN_TRUSTPILOT", raising=False)
        schedule_id = await _seed_schedule(
            db_session, ["plain-crawler", _trust_config_name()]
        )

        assert await ScheduleService(db_session).trigger(schedule_id) == []

    async def test_lookalike_config_name_is_not_gated(
        self, db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.delenv("PILGRIM_RUN_TRUSTPILOT", raising=False)
        schedule_id = await _seed_schedule(
            db_session, [f"{_trust_config_name()}-lookalike"]
        )

        jobs = await ScheduleService(db_session).trigger(schedule_id)
        assert len(jobs) == 1  # exact-name match only
