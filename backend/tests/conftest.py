"""Shared pytest fixtures for the Pilgrim backend test suite.

Tests must never require a real PostgreSQL/Redis instance — external
dependencies are mocked at the boundary. Environment variables only exist
so ``app.core.config.Settings`` (imported eagerly by the Celery app) can
be constructed; no connection is ever opened with them.
"""

import os

# Settings has required fields (DATABASE_URL, REDIS_URL) with no defaults.
# Provide placeholder values before any ``app.*`` import happens.
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://pilgrim:pilgrim@localhost:5432/pilgrim"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")
