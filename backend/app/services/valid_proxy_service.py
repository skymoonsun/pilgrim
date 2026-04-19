"""CRUD operations for ValidProxy."""

import logging
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import delete, select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

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
        manual_only: bool = False,
        skip: int = 0,
        limit: int = 50,
    ) -> tuple[list[ValidProxy], int]:
        """Return paginated valid proxies and total count."""
        query = select(ValidProxy).options(
            selectinload(ValidProxy.source_config)
        )
        count_query = select(func.count()).select_from(ValidProxy)

        if source_config_id is not None:
            query = query.where(ValidProxy.source_config_id == source_config_id)
            count_query = count_query.where(
                ValidProxy.source_config_id == source_config_id
            )
        if manual_only:
            query = query.where(ValidProxy.source_config_id.is_(None))
            count_query = count_query.where(ValidProxy.source_config_id.is_(None))
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

    async def create_manual_proxy(
        self,
        *,
        ip: str,
        port: int,
        protocol: ProxyProtocol,
        username: str | None = None,
        password: str | None = None,
    ) -> ValidProxy:
        """Create a single manual proxy (no source, no expiry).

        If the proxy already exists (by ip+port+protocol), it is
        converted to manual (source_config_id set to None, expires_at cleared).
        """
        result = await self.session.execute(
            select(ValidProxy).where(
                ValidProxy.ip == ip,
                ValidProxy.port == port,
                ValidProxy.protocol == protocol,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            existing.source_config_id = None
            existing.expires_at = None
            existing.username = username
            existing.password = password
            await self.session.commit()
            await self.session.refresh(existing)
            return existing

        proxy = ValidProxy(
            source_config_id=None,
            ip=ip,
            port=port,
            protocol=protocol,
            username=username,
            password=password,
            health=ProxyHealthStatus.HEALTHY,
            success_count=0,
            failure_count=0,
            last_checked_at=None,
            last_success_at=None,
            expires_at=None,
        )
        self.session.add(proxy)
        await self.session.commit()
        await self.session.refresh(proxy)
        return proxy

    async def create_manual_proxies_bulk(
        self,
        raw_text: str,
        default_protocol: ProxyProtocol = ProxyProtocol.HTTP,
    ) -> tuple[list[ValidProxy], int, int]:
        """Bulk-create manual proxies from raw text lines.

        Returns (proxies, created_count, skipped_count).
        """
        from app.services.proxy_parser import parse_raw_text

        parsed = parse_raw_text(raw_text)
        proxies: list[ValidProxy] = []
        skipped = 0

        for entry in parsed:
            protocol = entry.protocol
            # Apply default protocol for entries parsed as HTTP without
            # an explicit protocol prefix in the text.
            if protocol == ProxyProtocol.HTTP and default_protocol != ProxyProtocol.HTTP:
                protocol = default_protocol

            result = await self.session.execute(
                select(ValidProxy).where(
                    ValidProxy.ip == entry.ip,
                    ValidProxy.port == entry.port,
                    ValidProxy.protocol == protocol,
                )
            )
            existing = result.scalar_one_or_none()
            if existing is not None:
                existing.source_config_id = None
                existing.expires_at = None
                if entry.username is not None:
                    existing.username = entry.username
                if entry.password is not None:
                    existing.password = entry.password
                skipped += 1
                proxies.append(existing)
                continue

            proxy = ValidProxy(
                source_config_id=None,
                ip=entry.ip,
                port=entry.port,
                protocol=protocol,
                username=entry.username,
                password=entry.password,
                health=ProxyHealthStatus.HEALTHY,
                success_count=0,
                failure_count=0,
                last_checked_at=None,
                last_success_at=None,
                expires_at=None,
            )
            self.session.add(proxy)
            proxies.append(proxy)

        await self.session.commit()
        for proxy in proxies:
            await self.session.refresh(proxy)
        return proxies, len(proxies) - skipped, skipped

    async def delete_by_id(self, proxy_id: UUID) -> None:
        """Delete a valid proxy by ID."""
        proxy = await self.get_by_id(proxy_id)
        await self.session.delete(proxy)
        await self.session.commit()
        logger.info("Deleted valid proxy: %s", proxy_id)

    async def delete_by_ids(self, proxy_ids: list[UUID]) -> int:
        """Delete multiple proxies by their IDs. Returns count deleted."""
        stmt = delete(ValidProxy).where(ValidProxy.id.in_(proxy_ids))
        result = await self.session.execute(stmt)
        await self.session.commit()
        count = result.rowcount
        logger.info("Bulk-deleted %d proxies", count)
        return count

    async def delete_all(
        self,
        *,
        source_config_id: UUID | None = None,
        manual_only: bool = False,
        protocol: ProxyProtocol | None = None,
        health: ProxyHealthStatus | None = None,
    ) -> int:
        """Delete all proxies matching optional filters. Returns count deleted."""
        stmt = delete(ValidProxy)
        if source_config_id is not None:
            stmt = stmt.where(ValidProxy.source_config_id == source_config_id)
        if manual_only:
            stmt = stmt.where(ValidProxy.source_config_id.is_(None))
        if protocol is not None:
            stmt = stmt.where(ValidProxy.protocol == protocol)
        if health is not None:
            stmt = stmt.where(ValidProxy.health == health)
        result = await self.session.execute(stmt)
        await self.session.commit()
        count = result.rowcount
        logger.info("Deleted %d proxies (filtered bulk delete)", count)
        return count

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

    async def delete_unhealthy_by_source(self, source_config_id: UUID) -> int:
        """Delete all UNHEALTHY proxies for a source. Returns count deleted."""
        stmt = delete(ValidProxy).where(
            ValidProxy.source_config_id == source_config_id,
            ValidProxy.health == ProxyHealthStatus.UNHEALTHY,
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        count = result.rowcount
        logger.info("Deleted %d unhealthy proxies for source %s", count, source_config_id)
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