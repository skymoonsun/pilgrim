"""Seed runner — discovers and applies pending seed files.

Similar to Alembic migrations: each seed gets a version string and is
tracked in the ``seed_versions`` table so it runs exactly once.

Seed files live in ``backend/seeds/`` and follow the naming convention::

    NNNN_short_description.py    (e.g. 0001_sample_crawl_configs.py)

Each seed module must expose an async ``async def run(session)`` function.
"""

from __future__ import annotations

import importlib
import logging
import os
from pathlib import Path

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seed_version import SeedVersion

logger = logging.getLogger(__name__)

SEEDS_DIR = Path(__file__).resolve().parent.parent.parent / "seeds"


async def _ensure_seed_table(session: AsyncSession) -> None:
    """Create the seed_versions table if it doesn't exist yet."""
    await session.execute(
        text("""
            CREATE TABLE IF NOT EXISTS seed_versions (
                id SERIAL PRIMARY KEY,
                version VARCHAR(50) NOT NULL UNIQUE,
                name VARCHAR(255) NOT NULL,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
    )
    await session.commit()


async def get_applied_versions(session: AsyncSession) -> set[str]:
    """Return the set of already-applied seed version strings."""
    result = await session.execute(select(SeedVersion.version))
    return {row[0] for row in result.all()}


def discover_seeds() -> list[tuple[str, str, Path]]:
    """Discover seed files sorted by version number.

    Returns a list of ``(version, name, filepath)`` tuples.
    """
    if not SEEDS_DIR.exists():
        logger.warning("Seeds directory not found: %s", SEEDS_DIR)
        return []

    seeds: list[tuple[str, str, Path]] = []
    for filepath in sorted(SEEDS_DIR.glob("*.py")):
        stem = filepath.stem
        if stem.startswith("_"):
            continue
        # Expected format: NNNN_description
        parts = stem.split("_", 1)
        if len(parts) != 2:
            logger.warning("Skipping malformed seed filename: %s", stem)
            continue
        version = parts[0]
        name = parts[1]
        seeds.append((version, name, filepath))

    return seeds


async def run_pending_seeds(session: AsyncSession) -> list[str]:
    """Discover and apply all pending seeds.

    Returns the list of newly applied version strings.
    """
    await _ensure_seed_table(session)
    applied = await get_applied_versions(session)
    all_seeds = discover_seeds()

    pending = [
        (version, name, filepath)
        for version, name, filepath in all_seeds
        if version not in applied
    ]

    if not pending:
        logger.info("No pending seeds to apply.")
        return []

    applied_versions: list[str] = []
    for version, name, filepath in pending:
        logger.info("Applying seed %s (%s)...", version, name)
        try:
            # Dynamically import the seed module
            spec = importlib.util.spec_from_file_location(
                f"seeds.{filepath.stem}", filepath
            )
            if spec is None or spec.loader is None:
                logger.error("Cannot load seed module: %s", filepath)
                continue

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Each seed must have an async `run(session)` function
            if not hasattr(module, "run"):
                logger.error(
                    "Seed %s has no 'run' function, skipping.", filepath.stem
                )
                continue

            await module.run(session)

            # Record the seed version
            seed_record = SeedVersion(version=version, name=name)
            session.add(seed_record)
            await session.commit()

            applied_versions.append(version)
            logger.info("✓ Seed %s (%s) applied.", version, name)

        except Exception as exc:
            logger.error(
                "✗ Seed %s (%s) failed: %s", version, name, exc,
                exc_info=True,
            )
            await session.rollback()
            raise

    return applied_versions
