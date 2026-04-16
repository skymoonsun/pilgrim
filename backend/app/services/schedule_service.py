"""Service for managing crawl schedules, config links, URL targets."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from croniter import croniter
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConfigNotFoundError, ScheduleNotFoundError
from app.models.callback_config import CallbackConfig
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_job import CrawlJob
from app.models.crawl_schedule import CrawlSchedule
from app.models.email_notification_config import EmailNotificationConfig
from app.models.enums import CallbackMethod, CrawlJobStatus
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.schemas.schedule import (
    CallbackConfigCreate,
    EmailNotificationConfigCreate,
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleUrlCreate,
)

logger = logging.getLogger(__name__)


class ScheduleService:
    """Business logic for CrawlSchedule lifecycle."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    # ── Query helpers ────────────────────────────────────────────

    def _base_query(self):
        return select(CrawlSchedule).options(
            selectinload(CrawlSchedule.config_links)
            .selectinload(ScheduleConfigLink.config),
            selectinload(CrawlSchedule.config_links)
            .selectinload(ScheduleConfigLink.url_targets),
            selectinload(CrawlSchedule.callback),
            selectinload(CrawlSchedule.email_notification),
        )

    async def get_by_id(self, schedule_id: UUID) -> CrawlSchedule:
        result = await self.session.execute(
            self._base_query().where(CrawlSchedule.id == schedule_id)
        )
        schedule = result.scalar_one_or_none()
        if schedule is None:
            raise ScheduleNotFoundError(str(schedule_id))
        return schedule

    async def list_schedules(
        self, skip: int = 0, limit: int = 50, active_only: bool = False
    ) -> tuple[list[CrawlSchedule], int]:
        query = self._base_query()
        count_query = select(func.count()).select_from(CrawlSchedule)

        if active_only:
            query = query.where(CrawlSchedule.is_active.is_(True))
            count_query = count_query.where(CrawlSchedule.is_active.is_(True))

        total = (await self.session.execute(count_query)).scalar() or 0
        result = await self.session.execute(
            query.order_by(CrawlSchedule.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().unique()), total

    # ── Create ───────────────────────────────────────────────────

    async def create(self, data: ScheduleCreate) -> CrawlSchedule:
        schedule = CrawlSchedule(
            name=data.name,
            description=data.description,
            timezone=data.timezone,
            cron_expression=data.cron_expression,
            interval_seconds=data.interval_seconds,
            default_queue=data.default_queue,
            is_active=True,
        )

        # Calculate next_run_at
        schedule.next_run_at = self._compute_next_run(
            data.cron_expression, data.interval_seconds, data.timezone
        )

        self.session.add(schedule)
        await self.session.flush()  # get schedule.id

        # Create config links with their URL targets
        for i, cl in enumerate(data.config_links):
            config_id = UUID(cl.config_id)
            await self._validate_config(config_id)

            link = ScheduleConfigLink(
                schedule_id=schedule.id,
                config_id=config_id,
                priority=i,
            )
            self.session.add(link)
            await self.session.flush()  # get link.id

            for url_data in cl.urls:
                target = ScheduleUrlTarget(
                    config_link_id=link.id,
                    url=url_data.url,
                    label=url_data.label,
                    is_active=url_data.is_active,
                )
                self.session.add(target)

        # Callback config
        if data.callback:
            cb = self._build_callback(schedule.id, data.callback)
            self.session.add(cb)

        # Email notification config
        if data.email_notification:
            en = self._build_email_notification(schedule.id, data.email_notification)
            self.session.add(en)

        await self.session.commit()

        # Reload with relationships
        return await self.get_by_id(schedule.id)

    # ── Update ───────────────────────────────────────────────────

    async def update(
        self, schedule_id: UUID, data: ScheduleUpdate
    ) -> CrawlSchedule:
        schedule = await self.get_by_id(schedule_id)

        for field in (
            "name", "description", "timezone", "cron_expression",
            "interval_seconds", "default_queue", "is_active",
        ):
            value = getattr(data, field, None)
            if value is not None:
                setattr(schedule, field, value)

        # Recompute next_run if schedule changed
        if data.cron_expression is not None or data.interval_seconds is not None:
            schedule.next_run_at = self._compute_next_run(
                schedule.cron_expression,
                schedule.interval_seconds,
                schedule.timezone,
            )

        await self.session.commit()
        return await self.get_by_id(schedule_id)

    # ── Delete ───────────────────────────────────────────────────

    async def delete(self, schedule_id: UUID) -> None:
        schedule = await self.get_by_id(schedule_id)
        await self.session.delete(schedule)
        await self.session.commit()

    # ── URL management (per config link) ─────────────────────────

    async def add_url(
        self, config_link_id: UUID, data: ScheduleUrlCreate
    ) -> ScheduleUrlTarget:
        target = ScheduleUrlTarget(
            config_link_id=config_link_id,
            url=data.url,
            label=data.label,
            is_active=data.is_active,
        )
        self.session.add(target)
        await self.session.commit()
        await self.session.refresh(target)
        return target

    async def remove_url(self, url_id: UUID) -> None:
        await self.session.execute(
            delete(ScheduleUrlTarget).where(
                ScheduleUrlTarget.id == url_id,
            )
        )
        await self.session.commit()

    # ── Callback management ──────────────────────────────────────

    async def set_callback(
        self, schedule_id: UUID, data: CallbackConfigCreate
    ) -> CallbackConfig:
        schedule = await self.get_by_id(schedule_id)

        # Upsert: delete existing, create new
        if schedule.callback:
            await self.session.delete(schedule.callback)
            await self.session.flush()

        cb = self._build_callback(schedule_id, data)
        self.session.add(cb)
        await self.session.commit()
        await self.session.refresh(cb)
        return cb

    async def remove_callback(self, schedule_id: UUID) -> None:
        schedule = await self.get_by_id(schedule_id)
        if schedule.callback:
            await self.session.delete(schedule.callback)
            await self.session.commit()

    # ── Email notification management ──────────────────────────────

    async def set_email_notification(
        self, schedule_id: UUID, data: EmailNotificationConfigCreate,
    ) -> EmailNotificationConfig:
        """Create or replace the email notification config for a schedule."""
        schedule = await self.get_by_id(schedule_id)

        # Upsert: delete existing, create new
        if schedule.email_notification:
            await self.session.delete(schedule.email_notification)
            await self.session.flush()

        en = self._build_email_notification(schedule_id, data)
        self.session.add(en)
        await self.session.commit()
        await self.session.refresh(en)
        return en

    async def remove_email_notification(self, schedule_id: UUID) -> None:
        """Remove the email notification config from a schedule."""
        schedule = await self.get_by_id(schedule_id)
        if schedule.email_notification:
            await self.session.delete(schedule.email_notification)
            await self.session.commit()

    # ── Trigger (manual or by beat) ──────────────────────────────

    async def trigger(self, schedule_id: UUID) -> list[CrawlJob]:
        """Create CrawlJobs for every (config_link → urls) pair."""
        schedule = await self.get_by_id(schedule_id)
        jobs: list[CrawlJob] = []

        for link in schedule.config_links:
            active_urls = [t for t in link.url_targets if t.is_active]
            if not active_urls:
                continue
            for url_target in active_urls:
                job = CrawlJob(
                    crawl_configuration_id=link.config_id,
                    target_url=url_target.url,
                    queue=schedule.default_queue,
                    priority=5,
                    status=CrawlJobStatus.QUEUED,
                )
                self.session.add(job)
                jobs.append(job)

        if not jobs:
            logger.warning(
                "Schedule %s has no active config/URL pairs — skipping",
                schedule_id,
            )
            return jobs

        # Update tracking
        now = datetime.now(timezone.utc)
        schedule.last_run_at = now
        schedule.run_count += 1
        schedule.next_run_at = self._compute_next_run(
            schedule.cron_expression,
            schedule.interval_seconds,
            schedule.timezone,
        )

        await self.session.commit()
        for job in jobs:
            await self.session.refresh(job)

        logger.info(
            "Schedule %s triggered: %d jobs created", schedule_id, len(jobs)
        )
        return jobs

    # ── Helpers ──────────────────────────────────────────────────

    async def _validate_config(self, config_id: UUID) -> None:
        result = await self.session.execute(
            select(CrawlConfiguration.id).where(
                CrawlConfiguration.id == config_id
            )
        )
        if result.scalar_one_or_none() is None:
            raise ConfigNotFoundError(str(config_id))

    @staticmethod
    def _build_callback(
        schedule_id: UUID, data: CallbackConfigCreate
    ) -> CallbackConfig:
        return CallbackConfig(
            schedule_id=schedule_id,
            url=data.url,
            method=CallbackMethod(data.method),
            headers=data.headers,
            field_mapping=data.field_mapping,
            include_metadata=data.include_metadata,
            batch_results=data.batch_results,
            retry_count=data.retry_count,
            retry_delay_seconds=data.retry_delay_seconds,
            is_active=data.is_active,
        )

    @staticmethod
    def _build_email_notification(
        schedule_id: UUID, data: EmailNotificationConfigCreate,
    ) -> EmailNotificationConfig:
        return EmailNotificationConfig(
            schedule_id=schedule_id,
            recipient_emails=data.recipient_emails,
            subject_template=data.subject_template,
            field_mapping=data.field_mapping,
            include_metadata=data.include_metadata,
            batch_results=data.batch_results,
            on_success=data.on_success,
            on_failure=data.on_failure,
            is_active=data.is_active,
        )

    @staticmethod
    def _compute_next_run(
        cron_expression: str | None,
        interval_seconds: int | None,
        tz: str = "UTC",
    ) -> datetime | None:
        now = datetime.now(timezone.utc)
        if cron_expression:
            try:
                cron = croniter(cron_expression, now)
                return cron.get_next(datetime)
            except (ValueError, KeyError):
                return None
        elif interval_seconds:
            from datetime import timedelta

            return now + timedelta(seconds=interval_seconds)
        return None
