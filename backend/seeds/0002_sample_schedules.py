"""Seed 0002 — Sample crawl schedules with config-specific URL targets.

Creates realistic schedules linking the seed configs from 0001 to their
correct target URLs.  Each config link has its own URL set — URLs are not
shared across configs (no cartesian product).
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.callback_config import CallbackConfig
from app.models.crawl_config import CrawlConfiguration
from app.models.crawl_schedule import CrawlSchedule
from app.models.enums import CallbackMethod
from app.models.schedule_config_link import ScheduleConfigLink
from app.models.schedule_url_target import ScheduleUrlTarget


async def _get_config_by_name(session: AsyncSession, name: str) -> CrawlConfiguration | None:
    result = await session.execute(
        select(CrawlConfiguration).where(CrawlConfiguration.name == name)
    )
    return result.scalar_one_or_none()


async def run(session: AsyncSession) -> None:
    """Insert sample schedules for the seed crawl configs."""

    # Fetch existing configs
    books_listing = await _get_config_by_name(session, "books-toscrape-listing")
    books_detail = await _get_config_by_name(session, "books-toscrape-detail")
    quotes_listing = await _get_config_by_name(session, "quotes-toscrape-listing")
    hackernews = await _get_config_by_name(session, "hackernews-frontpage")

    if not all([books_listing, books_detail, quotes_listing, hackernews]):
        print("⚠️  Seed configs not found — run seed 0001 first.")
        return

    # ─────────────────────────────────────────────────────────────
    # 1. Books to Scrape — Hourly Listing Monitor
    # ─────────────────────────────────────────────────────────────
    books_schedule = CrawlSchedule(
        name="Books Listing Monitor",
        description=(
            "Hourly scrape of books.toscrape.com listing pages. "
            "Monitors first 3 pages for new titles and price changes."
        ),
        timezone="UTC",
        interval_seconds=3600,  # every hour
        default_queue="crawl_default",
        is_active=True,
    )
    session.add(books_schedule)
    await session.flush()

    # Config: books-toscrape-listing → 3 listing page URLs
    books_listing_link = ScheduleConfigLink(
        schedule_id=books_schedule.id,
        config_id=books_listing.id,
        priority=0,
    )
    session.add(books_listing_link)
    await session.flush()

    for url, label in [
        ("https://books.toscrape.com/", "Page 1"),
        ("https://books.toscrape.com/catalogue/page-2.html", "Page 2"),
        ("https://books.toscrape.com/catalogue/page-3.html", "Page 3"),
    ]:
        session.add(ScheduleUrlTarget(
            config_link_id=books_listing_link.id,
            url=url, label=label, is_active=True,
        ))

    # Config: books-toscrape-detail → 2 specific book detail pages
    books_detail_link = ScheduleConfigLink(
        schedule_id=books_schedule.id,
        config_id=books_detail.id,
        priority=1,
    )
    session.add(books_detail_link)
    await session.flush()

    for url, label in [
        (
            "https://books.toscrape.com/catalogue/a-light-in-the-attic_1000/index.html",
            "A Light in the Attic",
        ),
        (
            "https://books.toscrape.com/catalogue/tipping-the-velvet_999/index.html",
            "Tipping the Velvet",
        ),
    ]:
        session.add(ScheduleUrlTarget(
            config_link_id=books_detail_link.id,
            url=url, label=label, is_active=True,
        ))

    # ─────────────────────────────────────────────────────────────
    # 2. Quotes Monitor — Every 6 Hours (Cron)
    # ─────────────────────────────────────────────────────────────
    quotes_schedule = CrawlSchedule(
        name="Quotes Daily Monitor",
        description=(
            "Scrapes quotes.toscrape.com every 6 hours. "
            "Monitors first 2 pages for new quotes."
        ),
        timezone="Europe/Istanbul",
        cron_expression="0 */6 * * *",  # every 6 hours
        default_queue="crawl_default",
        is_active=True,
    )
    session.add(quotes_schedule)
    await session.flush()

    quotes_link = ScheduleConfigLink(
        schedule_id=quotes_schedule.id,
        config_id=quotes_listing.id,
        priority=0,
    )
    session.add(quotes_link)
    await session.flush()

    for url, label in [
        ("https://quotes.toscrape.com/", "Page 1"),
        ("https://quotes.toscrape.com/page/2/", "Page 2"),
    ]:
        session.add(ScheduleUrlTarget(
            config_link_id=quotes_link.id,
            url=url, label=label, is_active=True,
        ))

    # ─────────────────────────────────────────────────────────────
    # 3. Hacker News — Every 30 Minutes + Webhook Callback
    # ─────────────────────────────────────────────────────────────
    hn_schedule = CrawlSchedule(
        name="HN Headlines Tracker",
        description=(
            "Scrapes Hacker News front page every 30 minutes. "
            "Sends results to a webhook endpoint via callback."
        ),
        timezone="UTC",
        interval_seconds=1800,  # 30 minutes
        default_queue="crawl_high",
        is_active=True,
    )
    session.add(hn_schedule)
    await session.flush()

    hn_link = ScheduleConfigLink(
        schedule_id=hn_schedule.id,
        config_id=hackernews.id,
        priority=0,
    )
    session.add(hn_link)
    await session.flush()

    session.add(ScheduleUrlTarget(
        config_link_id=hn_link.id,
        url="https://news.ycombinator.com/",
        label="Front Page",
        is_active=True,
    ))

    # Webhook callback for HN schedule
    session.add(CallbackConfig(
        schedule_id=hn_schedule.id,
        url="https://webhook.site/example-pilgrim-callback",
        method=CallbackMethod.POST,
        headers={
            "X-Source": "pilgrim",
            "X-Schedule": "hn-headlines-tracker",
        },
        field_mapping={
            "field_mapping": {
                "headlines": "$.data.titles",
                "links": "$.data.links",
                "scores": "$.data.scores",
                "source_url": "$.url",
                "scraped_at": "$.metadata.timestamp",
            },
            "static_fields": {
                "source_system": "pilgrim",
                "feed": "hackernews",
            },
            "wrap_key": "payload",
        },
        include_metadata=True,
        batch_results=True,
        retry_count=3,
        retry_delay_seconds=30,
        is_active=True,
    ))

    await session.flush()
    print("✅ Seeded 3 schedules with URL targets and 1 callback config")
