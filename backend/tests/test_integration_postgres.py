"""Opt-in integration probe: real PostgreSQL is REQUIRED here.

Marked ``integration``, so conftest skips it on every run unless
``PILGRIM_RUN_INTEGRATION=1`` is exported — CI and local runs never set
it.  It exists to prove the marker mechanism and to give an opt-in
smoke check against the configured database URL.
"""

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import get_settings

pytestmark = pytest.mark.integration


async def test_postgres_reachable() -> None:
    """``SELECT 1`` over the app's DATABASE_URL; skipped by default."""
    engine = create_async_engine(str(get_settings().database_url))
    try:
        async with engine.connect() as conn:
            value = (await conn.execute(text("SELECT 1"))).scalar_one()
        assert value == 1
    finally:
        await engine.dispose()
