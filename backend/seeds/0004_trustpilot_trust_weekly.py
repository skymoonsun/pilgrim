"""Seed 0004 — Weekly Trustpilot trust-score schedule + delivery callback.

Wires the ``trustpilot-trust-score`` config (seed 0003) into an actual
cadence: a crawl schedule running every Monday 04:00 UTC (cron
``0 4 * * 1`` — a 7-day cadence, above the ToS minimum 6 h run spacing),
URL targets ``https://www.trustpilot.com/review/<domain>`` for each
domain in ``PILGRIM_TRUSTPILOT_DOMAINS`` (comma-separated, default
``kinguin.net``), and a callback that delivers the domain → score
document via the ``trust_scores`` transform
(``app.services.callback_service``).

Environment knobs (all read at seed-application time):

* ``PILGRIM_RUN_TRUSTPILOT`` — the schedule is created *active* only
  when this is ``1`` (default inactive); crawling is additionally
  gated at trigger time, so nothing runs without both.
* ``PILGRIM_TRUSTPILOT_DOMAINS`` — seller domains to crawl weekly.
* ``PILGRIM_TRUST_CALLBACK_URL`` — delivery endpoint; when empty
  (default) the callback is created **inactive** and parked — flip it
  active after setting a real endpoint.

The callback's single header ``X-Webhook-Secret`` stores the LITERAL
placeholder ``{{WEBHOOK_SECRET}}`` in the DB (never a plain-text
secret); ``callback_service`` resolves it from the environment at
dispatch time and drops the header when the variable is unset/empty.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime

from croniter import croniter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.callback_config import CallbackConfig
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_schedule import CrawlSchedule
from app.models.enums import CallbackMethod, ScheduleType
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget
from app.services.trust_scores import trustpilot_review_url

logger = logging.getLogger(__name__)

SCHEDULE_NAME = "trustpilot-trust-scores-weekly"
CONFIG_NAME = "trustpilot-trust-score"
#: Monday 04:00 UTC — a 7-day cadence (≥ 6 h run spacing per the ToS).
TRUSTPILOT_CRON = "0 4 * * 1"
#: Literal placeholder stored in the DB and resolved at dispatch time.
WEBHOOK_SECRET_PLACEHOLDER = "{{WEBHOOK_SECRET}}"
DEFAULT_DOMAIN = "kinguin.net"


async def run(session: AsyncSession) -> None:
    """Insert the weekly schedule (inactive by default) + its callback."""
    # ``seed_versions`` already makes this run-once, but never duplicate
    # the schedule even when the version row goes missing.
    existing = await session.execute(
        select(CrawlSchedule.id).where(CrawlSchedule.name == SCHEDULE_NAME)
    )
    if existing.scalar_one_or_none() is not None:
        logger.info(
            "Seed 0004: schedule %r already present — nothing to do",
            SCHEDULE_NAME,
        )
        return

    config = (
        await session.execute(
            select(CrawlConfiguration).where(
                CrawlConfiguration.name == CONFIG_NAME
            )
        )
    ).scalar_one_or_none()
    if config is None:
        raise LookupError(
            f"Seed 0004: config {CONFIG_NAME!r} not found — "
            "apply seed 0003 first"
        )

    raw_domains = os.environ.get("PILGRIM_TRUSTPILOT_DOMAINS", "")
    domains = [d.strip() for d in raw_domains.split(",") if d.strip()]
    if not domains:
        domains = [DEFAULT_DOMAIN]

    schedule = CrawlSchedule(
        name=SCHEDULE_NAME,
        description=(
            "Weekly Trustpilot trust-score crawl (Monday 04:00 UTC). "
            "Gated by PILGRIM_RUN_TRUSTPILOT at trigger time; delivers "
            "the domain → score document via the trust_scores callback "
            "transform."
        ),
        timezone="UTC",
        cron_expression=TRUSTPILOT_CRON,
        schedule_type=ScheduleType.CRAWL,
        default_queue="crawl_default",
        # Inactive until the operator explicitly opts in; the run gate
        # (PILGRIM_RUN_TRUSTPILOT) protects real crawling on top.
        is_active=os.environ.get("PILGRIM_RUN_TRUSTPILOT") == "1",
    )
    # Pre-compute the first due moment: without it an activated schedule
    # would never match the beat poller's next_run_at filter.
    schedule.next_run_at = croniter(
        TRUSTPILOT_CRON, datetime.now(UTC)
    ).get_next(datetime)
    session.add(schedule)
    await session.flush()

    link = ScheduleConfigLink(
        schedule_id=schedule.id,
        config_id=config.id,
        priority=0,
    )
    session.add(link)
    await session.flush()

    for domain in domains:
        # Raises for a non-domain entry — the seed fails loudly instead
        # of scheduling a URL it can never key a trust score to.
        session.add(
            ScheduleUrlTarget(
                config_link_id=link.id,
                url=trustpilot_review_url(domain),
                label=domain,
                is_active=True,
            )
        )

    callback_url = os.environ.get("PILGRIM_TRUST_CALLBACK_URL", "")
    if not callback_url:
        logger.warning(
            "Seed 0004: PILGRIM_TRUST_CALLBACK_URL unset — creating the "
            "callback INACTIVE (parked); set the URL and activate it "
            "once the ingest side is live"
        )
    session.add(
        CallbackConfig(
            schedule_id=schedule.id,
            url=callback_url,
            method=CallbackMethod.POST,
            # Exactly one header, literal env placeholder — resolved
            # from the environment at dispatch, never stored resolved.
            headers={"X-Webhook-Secret": WEBHOOK_SECRET_PLACEHOLDER},
            field_mapping={"transform": "trust_scores"},
            # Transform mode folds everything itself; no _metadata.
            include_metadata=False,
            batch_results=False,
            retry_count=2,
            retry_delay_seconds=60,
            is_active=bool(callback_url),
        )
    )

    await session.flush()
    logger.info(
        "✅ Seed 0004: %s (%d domain target(s), %s)",
        SCHEDULE_NAME,
        len(domains),
        "callback active" if callback_url else "callback parked inactive",
    )
