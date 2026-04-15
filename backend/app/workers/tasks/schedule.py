"""Schedule polling task — checks for due schedules and triggers them.

Runs every 30 seconds via Celery Beat.  For each schedule whose
``next_run_at`` is in the past, it creates CrawlJob rows for every
(config, url) permutation and enqueues them to workers.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="pilgrim.schedule.check_schedules",
    queue="maintenance",
)
def check_schedules() -> dict[str, int]:
    """Poll the database for due schedules and trigger them."""
    return asyncio.run(_check_schedules())


async def _check_schedules() -> dict[str, int]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    from sqlalchemy.orm import selectinload

    from app.core.config import get_settings
    from app.models.crawl_schedule import CrawlSchedule
    from app.models.schedule_config_link import ScheduleConfigLink
    from app.services.schedule_service import ScheduleService

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    triggered = 0

    try:
        async with session_factory() as session:
            now = datetime.now(timezone.utc)

            # Find active schedules whose next_run_at is in the past
            result = await session.execute(
                select(CrawlSchedule)
                .options(
                    selectinload(CrawlSchedule.config_links).selectinload(
                        ScheduleConfigLink.config
                    ),
                    selectinload(CrawlSchedule.config_links).selectinload(
                        ScheduleConfigLink.url_targets
                    ),
                    selectinload(CrawlSchedule.callback),
                )
                .where(
                    CrawlSchedule.is_active.is_(True),
                    CrawlSchedule.next_run_at.isnot(None),
                    CrawlSchedule.next_run_at <= now,
                )
            )
            schedules = list(result.scalars().unique())

            if not schedules:
                logger.debug("No due schedules found")
                return {"triggered": 0}

            service = ScheduleService(session)

            for schedule in schedules:
                try:
                    jobs = await service.trigger(schedule.id)
                    if jobs:
                        # Enqueue each job to Celery
                        from app.workers.tasks.scrape import run_crawl_job

                        for job in jobs:
                            run_crawl_job.apply_async(
                                args=[str(job.id)],
                                queue=job.queue,
                            )
                        triggered += 1
                        logger.info(
                            "Schedule '%s' triggered: %d jobs",
                            schedule.name, len(jobs),
                        )
                except Exception:
                    logger.exception(
                        "Failed to trigger schedule '%s'", schedule.name
                    )

    finally:
        await engine.dispose()

    return {"triggered": triggered}
