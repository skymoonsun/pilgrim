"""Proxy management Celery tasks — fetch, validate, expire."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone

import httpx

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

CONCURRENT_VALIDATIONS = 20


@celery_app.task(
    name="pilgrim.proxy.fetch_proxy_source",
    queue="maintenance",
    bind=True,
    autoretry_for=(httpx.TimeoutException, httpx.ConnectError),
    retry_backoff=True,
    max_retries=3,
    soft_time_limit=120,
    time_limit=180,
)
def fetch_proxy_source(self, source_id: str) -> str:
    """Fetch a proxy source URL, parse proxies, and store them as PENDING.

    Returns the source_id string so the linked validate_proxies task
    receives it as its first positional argument.
    """
    return asyncio.run(_fetch_proxy_source(source_id))


async def _fetch_proxy_source(source_id: str) -> str:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.enums import ProxyFormatType, ProxyHealthStatus, ProxyProtocol
    from app.models.proxy_source_config import ProxySourceConfig
    from app.models.proxy_fetch_log import ProxyFetchLog
    from app.models.valid_proxy import ValidProxy
    from app.services.proxy_parser import parse_proxy_list

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            start_time = time.monotonic()

            result = await session.execute(
                select(ProxySourceConfig).where(
                    ProxySourceConfig.id == source_id
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                logger.error("ProxySourceConfig %s not found", source_id)
                return source_id

            # Extract values from ORM object immediately
            source_uuid = config.id
            source_url = config.url
            source_name = config.name
            source_headers = config.source_headers or {}
            format_type = config.format_type
            extraction_spec = config.extraction_spec
            max_proxies = config.max_proxies
            proxy_ttl_seconds = config.proxy_ttl_seconds

            # Fetch the proxy list
            content: str | None = None
            content_length = 0
            fetch_error: str | None = None
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                try:
                    resp = await client.get(source_url, headers=source_headers)
                    resp.raise_for_status()
                    content = resp.text
                    content_length = len(content)
                except httpx.HTTPError as exc:
                    fetch_error = str(exc)

            if fetch_error:
                config.last_fetch_error = fetch_error
                config.last_fetched_at = datetime.now(timezone.utc)
                duration_ms = (time.monotonic() - start_time) * 1000
                fetch_log = ProxyFetchLog(
                    source_config_id=source_uuid,
                    status="error",
                    proxies_found=0,
                    proxies_new=0,
                    proxies_updated=0,
                    proxies_truncated=0,
                    content_length=content_length,
                    duration_ms=duration_ms,
                    error_message=fetch_error,
                )
                session.add(fetch_log)
                await session.commit()
                logger.error("Failed to fetch %s: %s", source_url, fetch_error)
                return source_id

            # Parse the content
            parsed: list = []
            parse_error: str | None = None
            try:
                parsed = parse_proxy_list(content, format_type, extraction_spec)
            except Exception as exc:
                parse_error = f"Parse error: {exc}"

            if parse_error:
                config.last_fetch_error = parse_error
                config.last_fetched_at = datetime.now(timezone.utc)
                duration_ms = (time.monotonic() - start_time) * 1000
                fetch_log = ProxyFetchLog(
                    source_config_id=source_uuid,
                    status="error",
                    proxies_found=0,
                    proxies_new=0,
                    proxies_updated=0,
                    proxies_truncated=0,
                    content_length=content_length,
                    duration_ms=duration_ms,
                    error_message=parse_error,
                )
                session.add(fetch_log)
                await session.commit()
                logger.error("Failed to parse proxies from %s: %s", source_name, exc)
                return source_id

            proxies_found = len(parsed)
            truncated = 0

            if not parsed:
                config.last_fetch_error = "No proxies found in source"
                config.last_fetched_at = datetime.now(timezone.utc)
                duration_ms = (time.monotonic() - start_time) * 1000
                fetch_log = ProxyFetchLog(
                    source_config_id=source_uuid,
                    status="success",
                    proxies_found=0,
                    proxies_new=0,
                    proxies_updated=0,
                    proxies_truncated=0,
                    content_length=content_length,
                    duration_ms=duration_ms,
                    error_message="No proxies found in source",
                )
                session.add(fetch_log)
                await session.commit()
                return source_id

            # Truncate if max_proxies is set
            if max_proxies is not None and len(parsed) > max_proxies:
                truncated = len(parsed) - max_proxies
                logger.info(
                    "Truncating proxies from %d to %d (max_proxies=%d) for source '%s'",
                    proxies_found, max_proxies, max_proxies, source_name,
                )
                parsed = parsed[:max_proxies]

            # Upsert parsed proxies — all as PENDING, with expires_at set
            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(seconds=proxy_ttl_seconds)
            proxies_new = 0
            proxies_updated = 0

            for proxy in parsed:
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
                        health=ProxyHealthStatus.PENDING,
                        success_count=0,
                        failure_count=0,
                        last_checked_at=now,
                        expires_at=expires_at,
                    )
                    session.add(new_proxy)
                    proxies_new += 1
                else:
                    existing_proxy.source_config_id = source_uuid
                    existing_proxy.expires_at = expires_at
                    if proxy.username is not None:
                        existing_proxy.username = proxy.username
                    if proxy.password is not None:
                        existing_proxy.password = proxy.password
                    proxies_updated += 1

            config.last_fetch_error = None
            config.last_fetched_at = now

            duration_ms = (time.monotonic() - start_time) * 1000
            fetch_log = ProxyFetchLog(
                source_config_id=source_uuid,
                status="success",
                proxies_found=proxies_found,
                proxies_new=proxies_new,
                proxies_updated=proxies_updated,
                proxies_truncated=truncated,
                content_length=content_length,
                duration_ms=duration_ms,
                error_message=None,
            )
            session.add(fetch_log)
            await session.commit()

            logger.info(
                "Fetched %d proxies from source '%s' (%d new, %d updated, %d truncated)",
                len(parsed), source_name, proxies_new, proxies_updated, truncated,
            )
            return source_id

    finally:
        await engine.dispose()


@celery_app.task(
    name="pilgrim.proxy.validate_proxies",
    queue="maintenance",
    bind=True,
    soft_time_limit=1800,
    time_limit=1860,
)
def validate_proxies(self, source_id_or_result: str | dict) -> dict[str, str]:
    """Validate proxies from a source by testing connectivity.

    When called via Celery link from fetch_proxy_source, receives the
    source_id string as the first positional argument. Also handles the
    legacy dict return format for backward compatibility.
    """
    actual_id = source_id_or_result
    if isinstance(source_id_or_result, dict):
        actual_id = source_id_or_result.get("source_id", source_id_or_result)
    return asyncio.run(_validate_proxies(str(actual_id)))


async def _test_proxy_url(
    proxy_url: str, url: str, timeout: int,
) -> tuple[bool, float | None]:
    """Test a single proxy against a single URL. Returns (passed, elapsed_ms)."""
    try:
        t0 = time.monotonic()
        async with httpx.AsyncClient(proxy=proxy_url, timeout=timeout) as client:
            resp = await client.get(url)
        elapsed = (time.monotonic() - t0) * 1000
        if resp.status_code < 500:
            return True, elapsed
        return False, None
    except Exception:
        return False, None


async def _test_proxy(
    semaphore: asyncio.Semaphore,
    proxy_url: str,
    validation_urls: list[str],
    timeout: int,
) -> dict[str, tuple[bool, float | None]]:
    """Test one proxy against all validation URLs, bounded by semaphore."""
    async with semaphore:
        results: dict[str, tuple[bool, float | None]] = {}
        for url in validation_urls:
            passed, elapsed = await _test_proxy_url(proxy_url, url, timeout)
            results[url] = (passed, elapsed)
        return results


async def _validate_proxies(source_id: str) -> dict[str, str]:
    from sqlalchemy import delete, select
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.models.enums import ProxyHealthStatus
    from app.models.proxy_source_config import ProxySourceConfig
    from app.models.proxy_validation_log import ProxyValidationLog
    from app.models.proxy_url_check_log import ProxyUrlCheckLog
    from app.models.valid_proxy import ValidProxy

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    try:
        async with session_factory() as session:
            start_time = time.monotonic()

            result = await session.execute(
                select(ProxySourceConfig).where(
                    ProxySourceConfig.id == source_id
                )
            )
            config = result.scalar_one_or_none()
            if config is None:
                return {"status": "error", "message": "Source not found"}

            # Extract values to avoid lazy-load issues
            source_uuid = config.id
            validation_urls = config.validation_urls.get("urls", [])
            require_all = config.require_all_urls
            timeout = config.validation_timeout or 10
            proxy_ttl_seconds = config.proxy_ttl_seconds

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

            # Per-URL accumulators for the performance matrix
            url_metrics: dict[str, dict] = {
                url: {"tested": 0, "passed": 0, "failed": 0, "total_ms": 0.0}
                for url in validation_urls
            }

            # Test proxies concurrently with bounded parallelism
            semaphore = asyncio.Semaphore(CONCURRENT_VALIDATIONS)
            proxy_urls = [_build_proxy_url(p) for p in proxies]

            test_tasks = [
                _test_proxy(semaphore, purl, validation_urls, timeout)
                for purl in proxy_urls
            ]
            all_results = await asyncio.gather(*test_tasks)

            # Process results and update proxy health
            healthy = 0
            degraded = 0
            unhealthy = 0
            now = datetime.now(timezone.utc)

            for proxy, results in zip(proxies, all_results):
                successes = 0
                total_time = 0.0

                for url, (passed, elapsed) in results.items():
                    url_metrics[url]["tested"] += 1
                    if passed:
                        successes += 1
                        total_time += elapsed  # type: ignore[operator]
                        url_metrics[url]["passed"] += 1
                        url_metrics[url]["total_ms"] += elapsed  # type: ignore[operator]
                    else:
                        url_metrics[url]["failed"] += 1

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
                    proxy.expires_at = now + timedelta(seconds=proxy_ttl_seconds)
                elif health == ProxyHealthStatus.DEGRADED:
                    proxy.failure_count += 1
                    proxy.expires_at = now + timedelta(seconds=proxy_ttl_seconds)
                else:
                    proxy.failure_count += 1

            # Delete unhealthy proxies
            unhealthy_ids = [p.id for p in proxies if p.health == ProxyHealthStatus.UNHEALTHY]
            removed = 0
            if unhealthy_ids:
                stmt = delete(ValidProxy).where(ValidProxy.id.in_(unhealthy_ids))
                result = await session.execute(stmt)
                removed = result.rowcount

            # Create validation log
            duration_ms = (time.monotonic() - start_time) * 1000
            validation_log = ProxyValidationLog(
                source_config_id=source_uuid,
                status="success",
                proxies_tested=len(proxies),
                proxies_healthy=healthy,
                proxies_degraded=degraded,
                proxies_unhealthy=unhealthy,
                proxies_removed=removed,
                duration_ms=duration_ms,
                error_message=None,
            )
            session.add(validation_log)
            await session.flush()  # get validation_log.id

            # Create per-URL check logs (performance matrix)
            for url, metrics in url_metrics.items():
                avg = (
                    metrics["total_ms"] / metrics["passed"]
                    if metrics["passed"] > 0
                    else None
                )
                url_check = ProxyUrlCheckLog(
                    validation_log_id=validation_log.id,
                    source_config_id=source_uuid,
                    url=url,
                    proxies_tested=metrics["tested"],
                    proxies_passed=metrics["passed"],
                    proxies_failed=metrics["failed"],
                    avg_response_ms=avg,
                )
                session.add(url_check)

            await session.commit()

            logger.info(
                "Validated proxies for source %s: %d healthy, %d degraded, %d unhealthy (%d removed) in %.0fms",
                source_id, healthy, degraded, unhealthy, removed, duration_ms,
            )
            return {
                "status": "ok",
                "healthy": str(healthy),
                "degraded": str(degraded),
                "unhealthy": str(unhealthy),
                "removed": str(removed),
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