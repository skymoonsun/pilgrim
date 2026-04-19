"""CRUD operations for ProxySourceConfig."""

import logging
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProxySourceNotFoundError
from app.models.proxy_source_config import ProxySourceConfig
from app.schemas.proxy import ProxySourceCreate, ProxySourceUpdate

logger = logging.getLogger(__name__)


class ProxySourceService:
    """Service layer for proxy source config management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: ProxySourceCreate) -> ProxySourceConfig:
        """Create a new proxy source config."""
        config = ProxySourceConfig(**data.model_dump())
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        logger.info("Created proxy source config: %s (%s)", config.id, config.name)
        return config

    async def get_by_id(self, source_id: UUID) -> ProxySourceConfig:
        """Get a proxy source config by ID or raise."""
        result = await self.session.execute(
            select(ProxySourceConfig).where(
                ProxySourceConfig.id == source_id
            )
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise ProxySourceNotFoundError(str(source_id))
        return config

    async def list_all(
        self,
        *,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ProxySourceConfig], int]:
        """Return paginated proxy source configs and total count."""
        query = select(ProxySourceConfig)
        count_query = select(func.count()).select_from(ProxySourceConfig)

        if active_only:
            query = query.where(ProxySourceConfig.is_active.is_(True))
            count_query = count_query.where(
                ProxySourceConfig.is_active.is_(True)
            )

        query = query.order_by(ProxySourceConfig.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        configs = list(result.scalars().all())

        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        return configs, total

    async def update(
        self,
        source_id: UUID,
        data: ProxySourceUpdate,
    ) -> ProxySourceConfig:
        """Partially update a proxy source config."""
        config = await self.get_by_id(source_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)
        await self.session.commit()
        await self.session.refresh(config)
        logger.info("Updated proxy source config: %s", config.id)
        return config

    async def delete(self, source_id: UUID) -> None:
        """Delete a proxy source config and its proxies."""
        config = await self.get_by_id(source_id)
        await self.session.delete(config)
        await self.session.commit()
        logger.info("Deleted proxy source config: %s", source_id)

    async def list_fetch_logs(
        self,
        source_id: UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list, int]:
        """Return paginated fetch logs for a source."""
        from app.models.proxy_fetch_log import ProxyFetchLog

        await self.get_by_id(source_id)
        query = (
            select(ProxyFetchLog)
            .where(ProxyFetchLog.source_config_id == source_id)
            .order_by(ProxyFetchLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        count_query = (
            select(func.count())
            .select_from(ProxyFetchLog)
            .where(ProxyFetchLog.source_config_id == source_id)
        )
        result = await self.session.execute(query)
        logs = list(result.scalars().all())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()
        return logs, total

    async def list_validation_logs(
        self,
        source_id: UUID,
        *,
        skip: int = 0,
        limit: int = 20,
    ) -> tuple[list, int]:
        """Return paginated validation logs for a source, with URL checks."""
        from sqlalchemy.orm import selectinload
        from app.models.proxy_validation_log import ProxyValidationLog

        await self.get_by_id(source_id)
        query = (
            select(ProxyValidationLog)
            .options(selectinload(ProxyValidationLog.url_checks))
            .where(ProxyValidationLog.source_config_id == source_id)
            .order_by(ProxyValidationLog.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        count_query = (
            select(func.count())
            .select_from(ProxyValidationLog)
            .where(ProxyValidationLog.source_config_id == source_id)
        )
        result = await self.session.execute(query)
        logs = list(result.scalars().unique())
        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()
        return logs, total