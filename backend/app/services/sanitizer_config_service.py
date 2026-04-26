"""CRUD operations for SanitizerConfig."""

import logging
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import SanitizerConfigNotFoundError
from app.models.sanitizer_config import SanitizerConfig
from app.schemas.sanitizer_config import (
    SanitizerConfigCreate,
    SanitizerConfigUpdate,
)

logger = logging.getLogger(__name__)


class SanitizerConfigService:
    """Service layer for sanitizer config management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(self, data: SanitizerConfigCreate) -> SanitizerConfig:
        """Create a new sanitizer config."""
        config = SanitizerConfig(**data.model_dump())
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        logger.info("Created sanitizer config: %s (%s)", config.id, config.name)
        return config

    async def get_by_id(self, config_id: UUID) -> SanitizerConfig:
        """Get a sanitizer config by ID or raise ``SanitizerConfigNotFoundError``."""
        result = await self.session.execute(
            select(SanitizerConfig).where(SanitizerConfig.id == config_id)
        )
        config = result.scalar_one_or_none()
        if config is None:
            raise SanitizerConfigNotFoundError(str(config_id))
        return config

    async def list_all(
        self,
        *,
        active_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[SanitizerConfig], int]:
        """Return paginated sanitizer configs and total count."""
        query = select(SanitizerConfig)
        count_query = select(func.count()).select_from(SanitizerConfig)

        if active_only:
            query = query.where(SanitizerConfig.is_active.is_(True))
            count_query = count_query.where(SanitizerConfig.is_active.is_(True))

        query = query.order_by(SanitizerConfig.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        configs = list(result.scalars().all())

        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        return configs, total

    async def update(
        self,
        config_id: UUID,
        data: SanitizerConfigUpdate,
    ) -> SanitizerConfig:
        """Partially update a sanitizer config."""
        config = await self.get_by_id(config_id)
        update_data = data.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(config, field, value)
        await self.session.commit()
        await self.session.refresh(config)
        logger.info("Updated sanitizer config: %s", config.id)
        return config

    async def delete(self, config_id: UUID) -> None:
        """Delete a sanitizer config."""
        config = await self.get_by_id(config_id)
        await self.session.delete(config)
        await self.session.commit()
        logger.info("Deleted sanitizer config: %s", config_id)