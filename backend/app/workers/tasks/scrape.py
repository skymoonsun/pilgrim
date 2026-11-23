"""Scrape tasks executed by Celery workers.

Each task receives a ``crawl_job_id`` (UUID string), loads the job and
its configuration from PostgreSQL, runs the Scrapling pipeline, and
persists results back to the database.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)

# ── App-owned fetch-option keys ─────────────────────────────────────
# Keys of ``CrawlConfiguration.fetch_options`` that Pilgrim consumes
# itself and must therefore NEVER be forwarded to a Scrapling fetcher
# constructor: Scrapling's fetchers take strict keyword arguments, so
# an app-owned key raises ``TypeError`` at ``create_fetcher`` time and
# crashes every fetch before it starts (e.g.
# ``FetcherSession(**{"proxy_retries": 3})`` on scrapling 0.5).
# ``proxy_retries`` (the proxy-rotation budget) is the one app-owned
# key so far: it is read from the RAW options by
# ``app.services.proxy_rotation.resolve_proxy_attempts``. Any other
# key is a genuine Scrapling kwarg (``timeout``, ``impersonate``,
# ``stealthy_headers``, ``follow_redirects``, ...) and passes through.
APP_OWNED_FETCH_KEYS: frozenset[str] = frozenset({"proxy_retries"})


def strip_app_owned_keys(fetch_options: dict[str, Any] | None) -> dict[str, Any]:
    """Return a copy of *fetch_options* without the app-owned keys.

    The input dict is NOT mutated — the raw options stay available
    (``resolve_proxy_attempts`` reads ``proxy_retries`` from them).
    """
    return {
        key: value
        for key, value in (fetch_options or {}).items()
        if key not in APP_OWNED_FETCH_KEYS
    }


@celery_app.task(
    name="pilgrim.scrape.run_job",
    bind=True,
    queue="crawl_default",
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def run_crawl_job(self, crawl_job_id: str) -> dict[str, str]:
    """Execute a single crawl job identified by *crawl_job_id*.

    Steps
    -----
    1. Load ``CrawlJob`` and its ``CrawlConfiguration`` from the DB.
    2. Update status → RUNNING.
    3. Fetch the target URL via Scrapling (using the config profile).
       When the config has ``use_proxy = true``, the fetch runs through
       the healthy proxy pool with rotation and a direct-fetch fallback
       (see ``app.services.proxy_rotation``).
    4. Apply extraction rules.
    5. Persist ``CrawlJobResult`` rows.
    6. Update status → SUCCEEDED (or FAILED on error).

    Proxy usage (which proxy, how many attempts, outcome) is recorded in
    the job's ``result_summary['proxy']`` so it shows up in the activity
    feed, with credentials always masked.
    """
    import asyncio
    from collections.abc import Collection
    from uuid import UUID

    async def _run() -> dict[str, str]:
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )

        from app.core.config import get_settings
        from app.crawlers.extraction import extract_data
        from app.crawlers.factory import create_fetcher, fetch_off_loop
        from app.models.crawl_job_result import CrawlJobResult
        from app.models.enums import CrawlJobStatus
        from app.models.valid_proxy import ValidProxy
        from app.services.crawl_job_service import CrawlJobService
        from app.services.proxy_rotation import (
            ProxyRotationReport,
            fetch_with_proxy_rotation,
            resolve_proxy_attempts,
        )
        from app.services.valid_proxy_service import ValidProxyService

        settings = get_settings()
        engine = create_async_engine(str(settings.database_url))
        session_factory = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )

        async with session_factory() as session:
            service = CrawlJobService(session)

            # 1. Load job
            job = await service.get_by_id(crawl_job_id)

            # 2. Mark running
            await service.update_status(
                job.id,
                CrawlJobStatus.RUNNING,
                celery_task_id=self.request.id,
            )

            start = time.monotonic()
            proxy_report: ProxyRotationReport | None = None
            try:
                # 3. Load config (eagerly loaded via relationship)
                config = await session.run_sync(
                    lambda s: job.crawl_configuration
                )

                # 3b. Politeness stagger for Trustpilot review pages:
                # random jitter before the fetcher is even created.
                # ``crawl_default`` is a SERIAL queue (prefetch 1) — jobs
                # never run concurrently — and the weekly schedule keeps
                # runs ≥ 7 days apart, so run spacing already satisfies
                # the ToS minimum of 6 hours; the jitter only spaces out
                # repeated/overlapping triggers within one window.
                if (
                    getattr(config, "name", None) == settings.trustpilot_config_name
                    and settings.trustpilot_stagger_seconds > 0
                ):
                    import random

                    await asyncio.sleep(
                        random.uniform(
                            0.0,
                            min(settings.trustpilot_stagger_seconds, 30.0),
                        )
                    )

                # 4. Fetch (through the healthy proxy pool when configured)
                # Strip app-owned keys (``proxy_retries``) so they never
                # reach the strict-kwargs Scrapling constructor; the raw
                # ``config.fetch_options`` stays intact for
                # ``resolve_proxy_attempts`` below.
                fetcher = create_fetcher(
                    config.scraper_profile,
                    strip_app_owned_keys(config.fetch_options or {}),
                )
                if config.use_proxy:
                    # NOTE: the rotation callback runs *synchronously inside
                    # the coroutine*, so browser profiles + ``use_proxy``
                    # still hit the Playwright sync-in-loop wall
                    # (``fetch_off_loop`` cannot help there without making
                    # ``fetch_with_proxy_rotation`` await the callable).
                    # No shipped config combines that pair today.
                    proxy_report = ProxyRotationReport()
                    proxy_service = ValidProxyService(session)

                    async def _select_proxy(
                        exclude: Collection[UUID],
                    ) -> ValidProxy | None:
                        return await proxy_service.get_random_healthy(
                            exclude_ids=exclude,
                        )

                    response = await fetch_with_proxy_rotation(
                        fetch=lambda kwargs: fetcher.get(
                            job.target_url, **kwargs
                        ),
                        select_proxy=_select_proxy,
                        profile=config.scraper_profile,
                        max_attempts=resolve_proxy_attempts(
                            config.fetch_options
                        ),
                        report=proxy_report,
                    )
                else:
                    # Browser profiles (stealth/dynamic) MUST run off the
                    # loop — see ``factory.fetch_off_loop``.
                    response = await fetch_off_loop(fetcher, job.target_url)
                http_status = getattr(response, "status", None)

                # 5. Extract
                # If extraction spec uses json_path, provide structured data
                next_data = None
                json_ld = None
                fields = config.extraction_spec.get("fields", {}) if config.extraction_spec else {}
                if any(
                    f.get("type") == "json_path" for f in fields.values() if isinstance(f, dict)
                ):
                    from app.crawlers.html_sanitizer import sanitize_html

                    html_raw = (
                        getattr(response, "html", "")
                        or getattr(response, "html_content", "")
                        or getattr(response, "body", "")
                        or str(response)
                    )
                    if html_raw.strip():
                        sanitize_result = sanitize_html(html_raw)
                        next_data = sanitize_result.next_data
                        json_ld = sanitize_result.json_ld

                data = extract_data(
                    response, config.extraction_spec,
                    next_data=next_data, json_ld=json_ld,
                )

                # 6. Persist result
                result = CrawlJobResult(
                    crawl_job_id=job.id,
                    source_url=job.target_url,
                    http_status=http_status,
                    payload=data,
                )
                session.add(result)

                duration_ms = round((time.monotonic() - start) * 1000, 2)
                result_summary: dict[str, Any] = {
                    "fields_extracted": len(data),
                    "duration_ms": duration_ms,
                }
                if proxy_report is not None:
                    result_summary["proxy"] = proxy_report.summary()
                await service.update_status(
                    job.id,
                    CrawlJobStatus.SUCCEEDED,
                    result_summary=result_summary,
                )
                if proxy_report is not None:
                    logger.info(
                        "Job %s succeeded in %.1fms via proxy %s "
                        "(fell_back_direct=%s, attempts=%d)",
                        crawl_job_id,
                        duration_ms,
                        proxy_report.used_proxy or "none",
                        proxy_report.fell_back_direct,
                        len(proxy_report.attempts),
                    )
                else:
                    logger.info(
                        "Job %s succeeded in %.1fms", crawl_job_id, duration_ms
                    )

                # ── Callback chain ───────────────────────────────
                await _maybe_enqueue_callback(session, job)

                # ── Email notification chain ────────────────────
                await _maybe_enqueue_email_notification(session, job, True)

                return {
                    "crawl_job_id": crawl_job_id,
                    "status": "succeeded",
                }

            except Exception as exc:
                duration_ms = round((time.monotonic() - start) * 1000, 2)
                failure_summary: dict[str, Any] = {"duration_ms": duration_ms}
                if proxy_report is not None:
                    # Keep the proxy story visible on failed jobs too —
                    # which proxies were tried and why we fell back.
                    failure_summary["proxy"] = proxy_report.summary()
                await service.update_status(
                    job.id,
                    CrawlJobStatus.FAILED,
                    error_message=str(exc),
                    result_summary=failure_summary,
                )
                logger.error("Job %s failed: %s", crawl_job_id, exc)

                # ── Email notification on failure ──────────────
                try:
                    await _maybe_enqueue_email_notification(session, job, False)
                except Exception:
                    logger.warning(
                        "Failed to enqueue email notification for job %s",
                        crawl_job_id, exc_info=True,
                    )

                raise

        await engine.dispose()

    return asyncio.run(_run())


async def _maybe_enqueue_callback(session, job) -> None:
    """Check if this job's config is linked to a schedule with a callback."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.callback_config import CallbackConfig
    from app.models.schedule_config_link import ScheduleConfigLink

    # Find schedules linked to this config
    result = await session.execute(
        select(ScheduleConfigLink)
        .options(selectinload(ScheduleConfigLink.schedule))
        .where(ScheduleConfigLink.config_id == job.crawl_configuration_id)
    )
    links = list(result.scalars())

    for link in links:
        # Check if schedule has an active callback
        cb_result = await session.execute(
            select(CallbackConfig).where(
                CallbackConfig.schedule_id == link.schedule_id,
                CallbackConfig.is_active.is_(True),
            )
        )
        callback_config = cb_result.scalar_one_or_none()
        if callback_config and not callback_config.batch_results:
            # Individual mode: fire immediately per job
            from app.workers.tasks.callback import send_callback

            send_callback.apply_async(
                args=[
                    str(job.id),
                    str(callback_config.id),
                    str(link.schedule_id),
                ],
                queue="maintenance",
            )
            logger.info(
                "Enqueued callback for job %s → %s",
                job.id, callback_config.url,
            )


async def _maybe_enqueue_email_notification(session, job, job_succeeded: bool) -> None:
    """Check if this job's config is linked to a schedule with email notification."""
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.models.email_notification_config import EmailNotificationConfig
    from app.models.schedule_config_link import ScheduleConfigLink

    trigger_reason = "success" if job_succeeded else "failure"

    result = await session.execute(
        select(ScheduleConfigLink)
        .options(selectinload(ScheduleConfigLink.schedule))
        .where(ScheduleConfigLink.config_id == job.crawl_configuration_id)
    )
    links = list(result.scalars())

    for link in links:
        en_result = await session.execute(
            select(EmailNotificationConfig).where(
                EmailNotificationConfig.schedule_id == link.schedule_id,
                EmailNotificationConfig.is_active.is_(True),
            )
        )
        email_config = en_result.scalar_one_or_none()
        if not email_config:
            continue

        # Check trigger conditions
        if job_succeeded and not email_config.on_success:
            continue
        if not job_succeeded and not email_config.on_failure:
            continue

        if not email_config.batch_results:
            # Individual mode: fire immediately per job
            from app.workers.tasks.email_notification import send_email_notification

            send_email_notification.apply_async(
                args=[
                    str(job.id),
                    str(email_config.id),
                    str(link.schedule_id),
                    trigger_reason,
                ],
                queue="maintenance",
            )
            logger.info(
                "Enqueued email notification for job %s → %s (reason: %s)",
                job.id, email_config.recipient_emails, trigger_reason,
            )

