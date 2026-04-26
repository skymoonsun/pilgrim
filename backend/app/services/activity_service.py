"""Service for the unified activity feed across job types."""

import logging
from uuid import UUID

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl_job import CrawlJob
from app.models.enums import CrawlJobStatus
from app.models.proxy_fetch_log import ProxyFetchLog
from app.models.proxy_source_config import ProxySourceConfig
from app.models.proxy_validation_log import ProxyValidationLog
from app.schemas.activity import (
    ActivityType,
    CrawlJobActivity,
    ProxyFetchActivity,
    ProxyValidationActivity,
)

logger = logging.getLogger(__name__)


class ActivityService:
    """Unified activity feed across crawl jobs, proxy fetches, and validations."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def list_activities(
        self,
        *,
        type_filter: list[ActivityType] | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list, int]:
        """Return a merged, paginated activity feed.

        Each item is a Pydantic model instance (CrawlJobActivity,
        ProxyFetchActivity, or ProxyValidationActivity).
        """
        type_filter = type_filter or list(ActivityType)

        # Count queries
        total = 0
        if ActivityType.CRAWL_JOB in type_filter:
            total += (await self.session.execute(
                select(func.count()).select_from(CrawlJob)
            )).scalar() or 0
        if ActivityType.PROXY_FETCH in type_filter:
            total += (await self.session.execute(
                select(func.count()).select_from(ProxyFetchLog)
            )).scalar() or 0
        if ActivityType.PROXY_VALIDATION in type_filter:
            total += (await self.session.execute(
                select(func.count()).select_from(ProxyValidationLog)
            )).scalar() or 0

        # Fetch lightweight rows from each table, merge by created_at DESC
        # Fetch more rows than needed to account for merging
        fetch_limit = skip + limit + 1

        items: list[tuple[datetime, ActivityType, UUID]] = []

        if ActivityType.CRAWL_JOB in type_filter:
            result = await self.session.execute(
                select(CrawlJob.id, CrawlJob.created_at)
                .order_by(CrawlJob.created_at.desc())
                .limit(fetch_limit)
            )
            for row in result:
                items.append((row.created_at, ActivityType.CRAWL_JOB, row.id))

        if ActivityType.PROXY_FETCH in type_filter:
            result = await self.session.execute(
                select(ProxyFetchLog.id, ProxyFetchLog.created_at)
                .order_by(ProxyFetchLog.created_at.desc())
                .limit(fetch_limit)
            )
            for row in result:
                items.append((row.created_at, ActivityType.PROXY_FETCH, row.id))

        if ActivityType.PROXY_VALIDATION in type_filter:
            result = await self.session.execute(
                select(ProxyValidationLog.id, ProxyValidationLog.created_at)
                .order_by(ProxyValidationLog.created_at.desc())
                .limit(fetch_limit)
            )
            for row in result:
                items.append((row.created_at, ActivityType.PROXY_VALIDATION, row.id))

        # Sort by created_at DESC and slice
        items.sort(key=lambda x: x[0], reverse=True)
        page = items[skip: skip + limit]

        # Fetch full objects for the selected IDs
        result_items = []
        crawl_ids = [id_ for ts, typ, id_ in page if typ == ActivityType.CRAWL_JOB]
        fetch_ids = [id_ for ts, typ, id_ in page if typ == ActivityType.PROXY_FETCH]
        validation_ids = [id_ for ts, typ, id_ in page if typ == ActivityType.PROXY_VALIDATION]

        crawl_map: dict[UUID, CrawlJob] = {}
        fetch_map: dict[UUID, ProxyFetchLog] = {}
        validation_map: dict[UUID, ProxyValidationLog] = {}
        source_names: dict[UUID, str] = {}

        if crawl_ids:
            result = await self.session.execute(
                select(CrawlJob).where(CrawlJob.id.in_(crawl_ids))
            )
            for job in result.scalars().all():
                crawl_map[job.id] = job

        if fetch_ids:
            result = await self.session.execute(
                select(ProxyFetchLog).where(ProxyFetchLog.id.in_(fetch_ids))
            )
            for log in result.scalars().all():
                fetch_map[log.id] = log
                source_ids = {log.source_config_id for log in fetch_map.values()}

        if validation_ids:
            result = await self.session.execute(
                select(ProxyValidationLog).where(ProxyValidationLog.id.in_(validation_ids))
            )
            for log in result.scalars().all():
                validation_map[log.id] = log

        # Collect all source config IDs that need name lookups
        source_ids: set[UUID] = set()
        for log in fetch_map.values():
            source_ids.add(log.source_config_id)
        for log in validation_map.values():
            source_ids.add(log.source_config_id)

        if source_ids:
            result = await self.session.execute(
                select(ProxySourceConfig.id, ProxySourceConfig.name)
                .where(ProxySourceConfig.id.in_(source_ids))
            )
            for row in result:
                source_names[row.id] = row.name

        # Build result list in order
        for ts, typ, id_ in page:
            if typ == ActivityType.CRAWL_JOB:
                job = crawl_map.get(id_)
                if job:
                    status_value = job.status.value if isinstance(job.status, CrawlJobStatus) else str(job.status)
                    result_items.append(CrawlJobActivity(
                        id=job.id,
                        type=ActivityType.CRAWL_JOB,
                        status=status_value,
                        error_message=job.error_message,
                        created_at=job.created_at,
                        crawl_configuration_id=job.crawl_configuration_id,
                        target_url=job.target_url,
                        queue=job.queue,
                        priority=job.priority,
                        started_at=job.started_at,
                        finished_at=job.finished_at,
                        result_summary=job.result_summary,
                    ))
            elif typ == ActivityType.PROXY_FETCH:
                log = fetch_map.get(id_)
                if log:
                    result_items.append(ProxyFetchActivity(
                        id=log.id,
                        type=ActivityType.PROXY_FETCH,
                        status=log.status,
                        error_message=log.error_message,
                        created_at=log.created_at,
                        source_config_id=log.source_config_id,
                        source_name=source_names.get(log.source_config_id),
                        proxies_found=log.proxies_found,
                        proxies_new=log.proxies_new,
                        proxies_updated=log.proxies_updated,
                        content_length=log.content_length,
                        duration_ms=log.duration_ms,
                    ))
            elif typ == ActivityType.PROXY_VALIDATION:
                log = validation_map.get(id_)
                if log:
                    result_items.append(ProxyValidationActivity(
                        id=log.id,
                        type=ActivityType.PROXY_VALIDATION,
                        status=log.status,
                        error_message=log.error_message,
                        created_at=log.created_at,
                        source_config_id=log.source_config_id,
                        source_name=source_names.get(log.source_config_id),
                        proxies_tested=log.proxies_tested,
                        proxies_healthy=log.proxies_healthy,
                        proxies_degraded=log.proxies_degraded,
                        proxies_unhealthy=log.proxies_unhealthy,
                        proxies_removed=log.proxies_removed,
                        duration_ms=log.duration_ms,
                    ))

        return result_items, total