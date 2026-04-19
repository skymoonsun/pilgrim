"""CRUD operations for ValidProxy."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ProxyNotFoundError
from app.models.enums import ProxyHealthStatus, ProxyProtocol
from app.models.valid_proxy import ValidProxy

logger = logging.getLogger(__name__)


class ValidProxyService:
    """Service layer for valid proxy management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, proxy_id: UUID) -> ValidProxy:
        """Get a valid proxy by ID or raise."""
        result = await self.session.execute(
            select(ValidProxy).where(ValidProxy.id == proxy_id)
        )
        proxy = result.scalar_one_or_none()
        if proxy is None:
            raise ProxyNotFoundError(str(proxy_id))
        return proxy

    async def list_all(
        self,
        *,
        source_config_id: UUID | None = None,
        protocol: ProxyProtocol | None = None,
        health: ProxyHealthStatus | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ValidProxy], int]:
        """Return paginated valid proxies and total count."""
        query = select(ValidProxy)
        count_query = select(func.count()).select_from(ValidProxy)

        if source_config_id is not None:
            query = query.where(ValidProxy.source_config_id == source_config_id)
            count_query = count_query.where(
                ValidProxy.source_config_id == source_config_id
            )
        if protocol is not None:
            query = query.where(ValidProxy.protocol == protocol)
            count_query = count_query.where(ValidProxy.protocol == protocol)
        if health is not None:
            query = query.where(ValidProxy.health == health)
            count_query = count_query.where(ValidProxy.health == health)

        query = query.order_by(ValidProxy.created_at.desc())
        query = query.offset(skip).limit(limit)

        result = await self.session.execute(query)
        proxies = list(result.scalars().all())

        count_result = await self.session.execute(count_query)
        total = count_result.scalar_one()

        return proxies, total

    async def upsert_proxy(
        self,
        *,
        source_config_id: UUID,
        ip: str,
        port: int,
        protocol: ProxyProtocol,
        username: str | None = None,
        password: str | None = None,
        health: ProxyHealthStatus = ProxyHealthStatus.HEALTHY,
        avg_response_ms: float | None = None,
    ) -> ValidProxy:
        """Insert or update a proxy by (ip, port, protocol) unique key."""
        result = await self.session.execute(
            select(ValidProxy).where(
                ValidProxy.ip == ip,
                ValidProxy.port == port,
                ValidProxy.protocol == protocol,
            )
        )
        proxy = result.scalar_one_or_none()

        if proxy is None:
            proxy = ValidProxy(
                source_config_id=source_config_id,
                ip=ip,
                port=port,
                protocol=protocol,
                username=username,
                password=password,
                health=health,
                avg_response_ms=avg_response_ms,
                success_count=1 if health == ProxyHealthStatus.HEALTHY else 0,
                failure_count=0 if health == ProxyHealthStatus.HEALTHY else 1,
                last_checked_at=datetime.now(timezone.utc),
                last_success_at=datetime.now(timezone.utc)
                if health == ProxyHealthStatus.HEALTHY
                else None,
            )
            self.session.add(proxy)
        else:
            proxy.health = health
            proxy.source_config_id = source_config_id
            if username is not None:
                proxy.username = username
            if password is not None:
                proxy.password = password
            if avg_response_ms is not None:
                proxy.avg_response_ms = avg_response_ms
            if health == ProxyHealthStatus.HEALTHY:
                proxy.success_count += 1
                proxy.last_success_at = datetime.now(timezone.utc)
            else:
                proxy.failure_count += 1
            proxy.last_checked_at = datetime.now(timezone.utc)

        await self.session.commit()
        await self.session.refresh(proxy)
        return proxy

    async def delete_by_id(self, proxy_id: UUID) -> None:
        """Delete a valid proxy by ID."""
        proxy = await self.get_by_id(proxy_id)
        await self.session.delete(proxy)
        await self.session.commit()
        logger.info("Deleted valid proxy: %s", proxy_id)

    async def delete_expired(self) -> int:
        """Delete all proxies past their expires_at timestamp."""
        now = datetime.now(timezone.utc)
        stmt = delete(ValidProxy).where(
            ValidProxy.expires_at.isnot(None),
            ValidProxy.expires_at < now,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        count = result.rowcount
        logger.info("Deleted %d expired proxies", count)
        return count

    async def get_random_healthy(
        self,
        protocol: ProxyProtocol | None = None,
    ) -> ValidProxy | None:
        """Get a random healthy proxy, optionally filtered by protocol."""
        query = select(ValidProxy).where(
            ValidProxy.health == ProxyHealthStatus.HEALTHY
        )
        if protocol is not None:
            query = query.where(ValidProxy.protocol == protocol)
        query = query.order_by(func.random()).limit(1)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()