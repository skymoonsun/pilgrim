"""CLI entry point for running seeds.

Usage (inside container)::

    python -m app.cli.seed
    python -m app.cli.seed --status
"""

from __future__ import annotations

import asyncio
import logging
import sys

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


async def run_seeds() -> None:
    """Apply all pending seeds."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.services.seed_service import run_pending_seeds

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        applied = await run_pending_seeds(session)

    await engine.dispose()

    if applied:
        logger.info("\n✅ Applied %d seed(s): %s", len(applied), ", ".join(applied))
    else:
        logger.info("\n✅ Database is up to date — no pending seeds.")


async def show_status() -> None:
    """Show seed status: applied and pending."""
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from app.core.config import get_settings
    from app.services.seed_service import (
        _ensure_seed_table,
        discover_seeds,
        get_applied_versions,
    )

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    session_factory = async_sessionmaker(engine, class_=AsyncSession)

    async with session_factory() as session:
        await _ensure_seed_table(session)
        applied = await get_applied_versions(session)
        all_seeds = discover_seeds()

    await engine.dispose()

    logger.info("\n📦 Seed Status")
    logger.info("─" * 50)

    if not all_seeds:
        logger.info("  No seed files found.")
        return

    for version, name, _ in all_seeds:
        status = "✓ applied" if version in applied else "○ pending"
        logger.info("  %s  %s — %s", status, version, name)

    pending_count = sum(1 for v, _, _ in all_seeds if v not in applied)
    logger.info("─" * 50)
    logger.info(
        "  Total: %d | Applied: %d | Pending: %d",
        len(all_seeds),
        len(all_seeds) - pending_count,
        pending_count,
    )


def main() -> None:
    if "--status" in sys.argv:
        asyncio.run(show_status())
    else:
        asyncio.run(run_seeds())


if __name__ == "__main__":
    main()
