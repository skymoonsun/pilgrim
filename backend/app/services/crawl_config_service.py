"""CRUD operations for CrawlConfiguration."""

import logging
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.exceptions import ConfigNotFoundError
from app.models.crawl_config import CrawlConfiguration
from app.schemas.crawl_config import (
    CrawlConfigCreate,
    CrawlConfigUpdate,
)

logger = logging.getLogger(__name__)


class CrawlConfigService:
    """Service layer for crawl configuration management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: CrawlConfigCreate) -> CrawlConfiguration:
        """Create a new crawl configuration."""
        config = CrawlConfiguration(**data.model_dump())
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        # Re-fetch with eager-loaded relationships to avoid MissingGreenlet
        config = await self.get_by_id(config.id)
        logger.info("Created crawl config: %s (%s)", config.id, config.name)
        return config

    async def get_by_id(self, config_id: UUID) -> CrawlConfiguration:
        """Get a configuration by ID or raise ``ConfigNotFoundError``."""
        result = await self.session.execute(
            select(CrawlConfiguration)
            .options(selectinload(CrawlConfiguration.sanitizer_config))
            .where(CrawlConfiguration.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise ConfigNotFoundError(str(config_id))
        return config

    async def list_all(
        self,
        *,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[CrawlConfiguration], int]:
        """Return paginated configs and total count."""
        query = select(CrawlConfiguration).options(
            selectinload(CrawlConfiguration.sanitizer_config)
        )
        count_query = select(func.count()).select_from(CrawlConfiguration)

        if active_only:
            query = query.where(CrawlConfiguration.is_active.is_(True))
            count_query = count_query.where(
                CrawlConfiguration.is_active.is_(True)
            )

        query = query.order_by(CrawlConfiguration.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        configs = list(result.scalars().all())

        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        return configs, total

    async def update(
        self,
        config_id: UUID,
        data: CrawlConfigUpdate,
    ) -> CrawlConfiguration:
        """Partially update a crawl configuration."""
        config = await self.get_by_id(config_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)
        await self.session.commit()
        # Re-fetch with eager-loaded relationships to avoid MissingGreenlet
        config = await self.get_by_id(config_id)
        logger.info("Updated crawl config: %s", config.id)
        return config

    async def delete(self, config_id: UUID) -> None:
        """Delete a crawl configuration."""
        config = await self.get_by_id(config_id)
        await self.session.delete(config)
        await self.session.commit()
        logger.info("Deleted crawl config: %s", config_id)
