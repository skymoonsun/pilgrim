"""Seed 0001 — Sample crawl configurations for testing.

Creates realistic configs targeting public scraping-friendly sites.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crawl_config import CrawlConfiguration
from app.models.enums import ScraperProfile


async def run(session: AsyncSession) -> None:
    """Insert sample crawl configurations."""

    configs = [
        # ── 1. Books to Scrape — product listing ────────────────
        CrawlConfiguration(
            name="books-toscrape-listing",
            description=(
                "Scrapes book listings from books.toscrape.com. "
                "Extracts titles, prices, ratings, and availability."
            ),
            scraper_profile=ScraperProfile.FETCHER,
            is_active=True,
            extraction_spec={
                "fields": {
                    "books": {
                        "selector": "article.product_pod",
                        "type": "css",
                        "multiple": True,
                        "children": {
                            "title": {
                                "selector": "h3 a::attr(title)",
                                "type": "css",
                            },
                            "price": {
                                "selector": ".price_color::text",
                                "type": "css",
                            },
                            "availability": {
                                "selector": ".availability::text",
                                "type": "css",
                            },
                            "link": {
                                "selector": "h3 a::attr(href)",
                                "type": "css",
                            },
                            "rating": {
                                "selector": "p.star-rating::attr(class)",
                                "type": "css",
                            },
                        },
                    },
                    "next_page": {
                        "selector": "li.next a::attr(href)",
                        "type": "css",
                    },
                },
            },
            fetch_options={
                "timeout": 30,
            },
            use_proxy=False,
            rotate_user_agent=True,
            custom_headers=None,
            custom_delay=None,
            max_concurrent=None,
        ),

        # ── 2. Books to Scrape — single product detail ──────────
        CrawlConfiguration(
            name="books-toscrape-detail",
            description=(
                "Scrapes a single book detail page from books.toscrape.com. "
                "Extracts full description, UPC, price, availability, and reviews."
            ),
            scraper_profile=ScraperProfile.FETCHER,
            is_active=True,
            extraction_spec={
                "fields": {
                    "title": {
                        "selector": "div.product_main h1::text",
                        "type": "css",
                    },
                    "price": {
                        "selector": "p.price_color::text",
                        "type": "css",
                    },
                    "availability": {
                        "selector": "p.availability::text",
                        "type": "css",
                    },
                    "description": {
                        "selector": "#product_description ~ p::text",
                        "type": "css",
                    },
                    "upc": {
                        "selector": "table.table-striped tr:nth-child(1) td::text",
                        "type": "css",
                    },
                    "num_reviews": {
                        "selector": "table.table-striped tr:nth-child(7) td::text",
                        "type": "css",
                    },
                    "breadcrumbs": {
                        "selector": "ul.breadcrumb li a::text",
                        "type": "css",
                        "multiple": True,
                    },
                    "image_url": {
                        "selector": "div.item.active img::attr(src)",
                        "type": "css",
                    },
                },
            },
            fetch_options={
                "timeout": 30,
            },
            use_proxy=False,
            rotate_user_agent=True,
        ),

        # ── 3. Quotes to Scrape — quote listing ─────────────────
        CrawlConfiguration(
            name="quotes-toscrape-listing",
            description=(
                "Scrapes quotes from quotes.toscrape.com. "
                "Extracts quote text, author, and tags."
            ),
            scraper_profile=ScraperProfile.FETCHER,
            is_active=True,
            extraction_spec={
                "fields": {
                    "quotes": {
                        "selector": "div.quote",
                        "type": "css",
                        "multiple": True,
                        "children": {
                            "text": {
                                "selector": "span.text::text",
                                "type": "css",
                            },
                            "author": {
                                "selector": "small.author::text",
                                "type": "css",
                            },
                            "tags": {
                                "selector": "a.tag::text",
                                "type": "css",
                                "multiple": True,
                            },
                        },
                    },
                    "next_page": {
                        "selector": "li.next a::attr(href)",
                        "type": "css",
                    },
                },
            },
            fetch_options={
                "timeout": 15,
            },
            use_proxy=False,
            rotate_user_agent=True,
        ),

        # ── 4. Hacker News — front page headlines ────────────────
        CrawlConfiguration(
            name="hackernews-frontpage",
            description=(
                "Scrapes the Hacker News front page. "
                "Extracts post titles, URLs, scores, and comment counts."
            ),
            scraper_profile=ScraperProfile.FETCHER,
            is_active=True,
            extraction_spec={
                "fields": {
                    "titles": {
                        "selector": "span.titleline > a::text",
                        "type": "css",
                        "multiple": True,
                    },
                    "links": {
                        "selector": "span.titleline > a::attr(href)",
                        "type": "css",
                        "multiple": True,
                    },
                    "scores": {
                        "selector": "span.score::text",
                        "type": "css",
                        "multiple": True,
                    },
                },
            },
            fetch_options={
                "timeout": 15,
            },
            use_proxy=False,
            rotate_user_agent=True,
        ),
    ]

    for config in configs:
        session.add(config)

    await session.flush()
