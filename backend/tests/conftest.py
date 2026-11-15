"""Shared pytest fixtures for the Pilgrim backend test suite.

Tests must never require a real PostgreSQL/Redis instance — external
dependencies are mocked at the boundary or replaced by an in-memory
SQLite database.  Environment variables only exist so
``app.core.config.Settings`` (imported eagerly by the Celery app) can be
constructed; no connection is ever opened with them.

Database strategy
-----------------
``db_engine``/``db_session`` provide the full Pilgrim schema on
``sqlite+aiosqlite`` in memory.  The models use Postgres-only column
types (``postgresql.UUID``, ``JSONB``), so lightweight ``@compiles``
hooks render them as portable SQLite types for the test dialect only.

Tests that genuinely need external services must be marked
``@pytest.mark.integration``; the suite skips them unless
``PILGRIM_RUN_INTEGRATION=1`` is exported.
"""

import os
from typing import Any

# Settings has required fields (DATABASE_URL, REDIS_URL) with no defaults.
# Provide placeholder values before any ``app.*`` import happens.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://pilgrim:pilgrim@localhost:5432/pilgrim"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

from collections.abc import AsyncIterator  # noqa: E402

import pytest  # noqa: E402
from sqlalchemy import StaticPool  # noqa: E402
from sqlalchemy.dialects.postgresql import JSONB as PGJSONB  # noqa: E402
from sqlalchemy.dialects.postgresql import UUID as PGUUID  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.ext.compiler import compiles  # noqa: E402

from app.models import Base  # noqa: E402


@compiles(PGUUID, "sqlite")
def _render_pg_uuid_sqlite(
    type_: PGUUID[Any], compiler: Any, **kw: Any
) -> str:
    """Render Postgres UUID columns as CHAR(32) under the SQLite dialect."""
    return "CHAR(32)"


@compiles(PGJSONB, "sqlite")
def _render_pg_jsonb_sqlite(
    type_: PGJSONB, compiler: Any, **kw: Any
) -> str:
    """Render Postgres JSONB columns as JSON affinity under SQLite."""
    return "JSON"


def _memory_url() -> str:
    return "sqlite+aiosqlite://"


@pytest.fixture
async def db_engine() -> AsyncIterator[AsyncEngine]:
    """In-memory SQLite engine with the complete Pilgrim schema loaded."""
    engine = create_async_engine(
        _memory_url(),
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def db_session(db_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """Session over the in-memory schema; every test starts empty."""
    factory = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as session:
        yield session


def pytest_collection_modifyitems(
    config: Any, items: list[Any]
) -> None:
    """Skip ``integration``-marked tests unless explicitly enabled.

    Nothing in the unit suite may demand Postgres/Redis/network; tests
    that do belong to this marker and stay invisible locally/CI unless
    ``PILGRIM_RUN_INTEGRATION=1`` opts in.
    """
    run_integration = os.environ.get("PILGRIM_RUN_INTEGRATION") == "1"
    if run_integration:
        return
    skip = pytest.mark.skip(
        reason="needs real external services; set PILGRIM_RUN_INTEGRATION=1"
    )
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip)
