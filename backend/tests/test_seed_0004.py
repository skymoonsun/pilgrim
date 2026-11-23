"""Seed 0004 — weekly Trustpilot schedule + parkable callback (idempotent)."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.callback_config import CallbackConfig
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_schedule import CrawlSchedule
from app.models.enums import ScheduleType
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.services.trust_scores import trustpilot_review_url

ROOT = Path(__file__).resolve().parent
SEED_PATH = ROOT.parent / "seeds" / "0004_trustpilot_trust_weekly.py"


def _load_seed() -> Any:
    spec = importlib.util.spec_from_file_location("seed_0004", SEED_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def _ensure_config(session: AsyncSession) -> None:
    session.add(
        CrawlConfiguration(name="trustpilot-trust-score", is_active=True)
    )
    await session.flush()


async def _seed(session: AsyncSession) -> None:
    await _load_seed().run(session)


async def _schedules(session: AsyncSession) -> list[Any]:
    return list((await session.execute(select(CrawlSchedule))).scalars())


async def _callbacks(session: AsyncSession) -> list[Any]:
    return list((await session.execute(select(CallbackConfig))).scalars())


async def _targets(session: AsyncSession) -> list[Any]:
    return list((await session.execute(select(ScheduleUrlTarget))).scalars())


class TestSeed0004:
    async def test_creates_schedule_callback_and_target(
        self, db_session: AsyncSession,
    ) -> None:
        await _ensure_config(db_session)
        await _seed(db_session)

        schedules = await _schedules(db_session)
        assert len(schedules) == 1
        schedule = schedules[0]
        assert schedule.name == "trustpilot-trust-scores-weekly"
        assert schedule.schedule_type is ScheduleType.CRAWL
        assert schedule.cron_expression == "0 4 * * 1"
        assert schedule.timezone == "UTC"
        assert schedule.default_queue == "crawl_default"
        assert schedule.next_run_at is not None
        # env unset → schedule inactive
        assert schedule.is_active is False

        callbacks = await _callbacks(db_session)
        assert len(callbacks) == 1
        callback = callbacks[0]
        assert callback.schedule_id == schedule.id
        assert callback.method.value == "POST"
        # Literal placeholder in the DB, exactly one header.
        assert callback.headers == {"X-Webhook-Secret": "{{WEBHOOK_SECRET}}"}
        assert callback.field_mapping == {"transform": "trust_scores"}
        assert callback.batch_results is False
        assert callback.retry_count == 2
        assert callback.retry_delay_seconds == 60
        # No callback URL → parked inactive.
        assert callback.url == ""
        assert callback.is_active is False

    async def test_default_url_target_is_kinguin(
        self, db_session: AsyncSession,
    ) -> None:
        await _ensure_config(db_session)
        await _seed(db_session)

        assert len(await _targets(db_session)) == 1  # default: kinguin.net
        target = (await _targets(db_session))[0]
        assert target.url == trustpilot_review_url("kinguin.net")
        assert target.label == "kinguin.net"
        assert target.is_active is True

        link = (await db_session.execute(select(ScheduleConfigLink))).scalar_one()
        assert link.priority == 0
        config = await db_session.get(CrawlConfiguration, link.config_id)
        assert config is not None
        assert config.name == "trustpilot-trust-score"

    async def test_rerun_does_not_duplicate(
        self, db_session: AsyncSession,
    ) -> None:
        await _ensure_config(db_session)
        await _seed(db_session)
        # seed_version would normally prevent re-running; the name guard
        # must hold even without it.
        await _seed(db_session)

        assert len(await _schedules(db_session)) == 1
        assert len(await _callbacks(db_session)) == 1
        assert len(await _targets(db_session)) == 1
        assert len((await db_session.execute(
            select(ScheduleConfigLink)
        )).scalars().all()) == 1

    async def test_active_when_env_enabled(
        self, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _ensure_config(db_session)
        monkeypatch.setenv("PILGRIM_RUN_TRUSTPILOT", "1")
        await _seed(db_session)

        schedule = (await _schedules(db_session))[0]
        assert schedule.is_active is True

    async def test_domains_env_expands_targets(
        self, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _ensure_config(db_session)
        monkeypatch.setenv(
            "PILGRIM_TRUSTPILOT_DOMAINS", " gog.com , WWW.kinguin.net ,"
        )
        await _seed(db_session)

        urls = [t.url for t in await _targets(db_session)]
        assert urls == [
            trustpilot_review_url("gog.com"),
            trustpilot_review_url("kinguin.net"),
        ]

    async def test_callback_url_activates(
        self, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _ensure_config(db_session)
        monkeypatch.setenv(
            "PILGRIM_TRUST_CALLBACK_URL", "https://ingest.example/trust"
        )
        await _seed(db_session)

        callback = (await _callbacks(db_session))[0]
        assert callback.url == "https://ingest.example/trust"
        assert callback.is_active is True

    async def test_missing_config_fails_the_seed(
        self, db_session: AsyncSession,
    ) -> None:
        with pytest.raises(LookupError, match="seed 0003"):
            await _seed(db_session)

    async def test_garbage_domain_fails_the_seed(
        self, db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        await _ensure_config(db_session)
        monkeypatch.setenv("PILGRIM_TRUSTPILOT_DOMAINS", "not a domain")
        with pytest.raises(ValueError):
            await _seed(db_session)
