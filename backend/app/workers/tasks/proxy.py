"""Proxy management Celery tasks — fetch, validate, expire."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(
    name="pilgrim.proxy.fetch_proxy_source",
    queue="maintenance",
    bind=True,
    autoretry_for=(httpx.TimeoutException, httpx.ConnectError),
    retry_backoff=True,
    max_retries=3,
)
def fetch_proxy_source(self, source_id: str) -> dict[str, str]:
    """Fetch a proxy source URL, parse proxies, and store them."""
    return asyncio.run(_fetch_proxy_source(source_id))


async def _fetch_proxy_source(source_id: str) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.enums import ProxyFormatType
    from app.models.proxy_source_config import ProxySourceConfig
    from app.models.valid_proxy import ValidProxy
    from app.services.proxy_parser import parse_proxy_list

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(ProxySourceConfig).where(
                    ProxySourceConfig.id == source_id
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                logger.error("ProxySourceConfig %s not found", source_id)
                return {"status": "error", "message": "Source not found"}

            # Extract values from ORM object immediately to avoid lazy-load issues
            source_uuid = config.id
            source_url = config.url
            source_name = config.name
            source_headers = config.source_headers or {}
            format_type = config.format_type
            extraction_spec = config.extraction_spec
            max_proxies = config.max_proxies

            # Fetch the proxy list
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                try:
                    resp = await client.get(source_url, headers=source_headers)
                    resp.raise_for_status()
                    content = resp.text
                except httpx.HTTPError as exc:
                    config.last_fetch_error = str(exc)
                    config.last_fetched_at = datetime.now(timezone.utc)
                    await session.commit()
                    logger.error("Failed to fetch %s: %s", source_url, exc)
                    return {"status": "error", "message": f"Fetch failed: {exc}"}

            # Parse the content
            try:
                parsed = parse_proxy_list(content, format_type, extraction_spec)
            except Exception as exc:
                config.last_fetch_error = f"Parse error: {exc}"
                config.last_fetched_at = datetime.now(timezone.utc)
                await session.commit()
                logger.error("Failed to parse proxies from %s: %s", source_name, exc)
                return {"status": "error", "message": f"Parse failed: {exc}"}

            if not parsed:
                config.last_fetch_error = "No proxies found in source"
                config.last_fetched_at = datetime.now(timezone.utc)
                await session.commit()
                return {"status": "warning", "message": "No proxies found"}

            # Truncate if max_proxies is set
            if max_proxies is not None and len(parsed) > max_proxies:
                logger.info(
                    "Truncating proxies from %d to %d (max_proxies=%d) for source '%s'",
                    len(parsed), max_proxies, max_proxies, source_name,
                )
                parsed = parsed[:max_proxies]

            # Upsert parsed proxies directly
            from app.models.enums import ProxyHealthStatus, ProxyProtocol

            upserted = 0
            for proxy in parsed:
                # Check if proxy exists
                existing = await session.execute(
                    select(ValidProxy).where(
                        ValidProxy.ip == proxy.ip,
                        ValidProxy.port == proxy.port,
                        ValidProxy.protocol == proxy.protocol,
                    )
                )
                existing_proxy = existing.scalar_one_or_none()

                if existing_proxy is None:
                    new_proxy = ValidProxy(
                        source_config_id=source_uuid,
                        ip=proxy.ip,
                        port=proxy.port,
                        protocol=proxy.protocol,
                        username=proxy.username,
                        password=proxy.password,
                        health=ProxyHealthStatus.HEALTHY,
                        success_count=1,
                        failure_count=0,
                        last_checked_at=datetime.now(timezone.utc),
                        last_success_at=datetime.now(timezone.utc),
                    )
                    session.add(new_proxy)
                else:
                    existing_proxy.health = ProxyHealthStatus.HEALTHY
                    existing_proxy.source_config_id = source_uuid
                    if proxy.username is not None:
                        existing_proxy.username = proxy.username
                    if proxy.password is not None:
                        existing_proxy.password = proxy.password
                    existing_proxy.success_count += 1
                    existing_proxy.last_checked_at = datetime.now(timezone.utc)
                    existing_proxy.last_success_at = datetime.now(timezone.utc)

                upserted += 1

            config.last_fetch_error = None
            config.last_fetched_at = datetime.now(timezone.utc)
            await session.commit()

            logger.info(
                "Fetched %d proxies from source '%s'", upserted, source_name
            )
            return {"status": "ok", "proxies_found": str(upserted)}

    finally:
        await engine.dispose()


@celery_app.task(
    name="pilgrim.proxy.validate_proxies",
    queue="maintenance",
    bind=True,
)
def validate_proxies(self, source_id: str) -> dict[str, str]:
    """Validate proxies from a source by testing connectivity."""
    return asyncio.run(_validate_proxies(source_id))


async def _validate_proxies(source_id: str) -> dict[str, str]:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.enums import ProxyHealthStatus
    from app.models.proxy_source_config import ProxySourceConfig
    from app.models.valid_proxy import ValidProxy

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            result = await session.execute(
                select(ProxySourceConfig).where(
                    ProxySourceConfig.id == source_id
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                return {"status": "error", "message": "Source not found"}

            # Extract values to avoid lazy-load issues
            validation_urls = config.validation_urls.get("urls", [])
            require_all = config.require_all_urls
            timeout = config.validation_timeout or 10

            if not validation_urls:
                logger.warning("No validation URLs configured for source %s", source_id)
                return {"status": "warning", "message": "No validation URLs"}

            # Get all proxies for this source
            result = await session.execute(
                select(ValidProxy).where(
                    ValidProxy.source_config_id == source_id
                )
            )
            proxies = list(result.scalars().all())

            if not proxies:
                return {"status": "ok", "validated": "0"}

            healthy = 0
            degraded = 0
            unhealthy = 0

            for proxy in proxies:
                proxy_url = _build_proxy_url(proxy)
                successes = 0
                total_time = 0.0

                for url in validation_urls:
                    try:
                        start = time.monotonic()
                        async with httpx.AsyncClient(
                            proxy=proxy_url,
                            timeout=timeout,
                        ) as client:
                            resp = await client.get(url)
                            elapsed = (time.monotonic() - start) * 1000
                            if resp.status_code < 500:
                                successes += 1
                                total_time += elapsed
                    except Exception:
                        pass

                now = datetime.now(timezone.utc)
                if require_all and successes == len(validation_urls):
                    health = ProxyHealthStatus.HEALTHY
                    healthy += 1
                elif not require_all and successes > 0:
                    health = ProxyHealthStatus.HEALTHY
                    healthy += 1
                elif successes > 0:
                    health = ProxyHealthStatus.DEGRADED
                    degraded += 1
                else:
                    health = ProxyHealthStatus.UNHEALTHY
                    unhealthy += 1

                avg_ms = total_time / successes if successes > 0 else None

                proxy.health = health
                proxy.avg_response_ms = avg_ms
                proxy.last_checked_at = now
                if health == ProxyHealthStatus.HEALTHY:
                    proxy.success_count += 1
                    proxy.last_success_at = now
                else:
                    proxy.failure_count += 1

            await session.commit()

            logger.info(
                "Validated proxies for source %s: %d healthy, %d degraded, %d unhealthy",
                source_id, healthy, degraded, unhealthy,
            )
            return {
                "status": "ok",
                "healthy": str(healthy),
                "degraded": str(degraded),
                "unhealthy": str(unhealthy),
            }

    finally:
        await engine.dispose()


@celery_app.task(
    name="pilgrim.proxy.expire_proxies",
    queue="maintenance",
)
def expire_proxies() -> dict[str, str]:
    """Remove expired proxies from the database."""
    return asyncio.run(_expire_proxies())


async def _expire_proxies() -> dict[str, str]:
    from sqlalchemy import delete
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.valid_proxy import ValidProxy

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            now = datetime.now(timezone.utc)
            stmt = delete(ValidProxy).where(
                ValidProxy.expires_at.isnot(None),
                ValidProxy.expires_at < now,
            )
            result = await session.execute(stmt)
            await session.commit()
            count = result.rowcount
            logger.info("Deleted %d expired proxies", count)
            return {"status": "ok", "expired_deleted": str(count)}
    finally:
        await engine.dispose()


def _build_proxy_url(proxy) -> str:
    """Build a proxy URL from a ValidProxy ORM object."""
    protocol = proxy.protocol.value
    if proxy.username and proxy.password:
        return f"{protocol}://{proxy.username}:{proxy.password}@{proxy.ip}:{proxy.port}"
    return f"{protocol}://{proxy.ip}:{proxy.port}"