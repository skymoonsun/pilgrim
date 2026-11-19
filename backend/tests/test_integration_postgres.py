"""Opt-in integration probe: real PostgreSQL is REQUIRED here.

Marked ``integration``, so conftest skips it on every run unless
``PILGRIM_RUN_INTEGRATION=1`` is exported — CI and local runs never set
it.  It exists to prove the marker mechanism and to give an opt-in
smoke check against the configured database URL.
"""

from collections.abc import AsyncIterator
from enum import Enum
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.models.enums import ProxyFormatType, ProxyHealthStatus, ProxyProtocol
from app.models.proxy_source_config import ProxySourceConfig
from app.models.valid_proxy import ValidProxy
from app.services.valid_proxy_service import ValidProxyService

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


# ── Proxy enum casing regression ─────────────────────────────────────
#
# ``b2c3d4e5f6a7`` created the proxy enums with lowercase *values* while
# ``sa.Enum(<PyEnum>)`` persists member *names*; on real PostgreSQL every
# proxy insert / list / stats call died with ``invalid input value for enum
# proxy_health_status_enum: "HEALTHY"``.  SQLite (the unit-test dialect)
# stores enums as VARCHAR, so only a real PostgreSQL at alembic head can
# catch this class of drift.  Requires ``alembic upgrade head`` to have run.

PROXY_ENUMS: list[tuple[str, type[Enum]]] = [
    ("proxy_health_status_enum", ProxyHealthStatus),
    ("proxy_protocol_enum", ProxyProtocol),
    ("proxy_format_type_enum", ProxyFormatType),
]


@pytest.fixture
async def pg_engine() -> AsyncIterator[AsyncEngine]:
    engine = create_async_engine(str(get_settings().database_url))
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.fixture
async def pg_session(pg_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    factory = async_sessionmaker(pg_engine, expire_on_commit=False)
    async with factory() as session:
        yield session


@pytest.mark.parametrize(("pg_type", "py_enum"), PROXY_ENUMS)
async def test_proxy_enum_labels_match_member_names(
    pg_engine: AsyncEngine, pg_type: str, py_enum: type[Enum]
) -> None:
    """The DB enum labels are exactly the Python member *names*."""
    async with pg_engine.connect() as conn:
        rows = await conn.execute(
            text(
                "SELECT e.enumlabel FROM pg_enum e "
                "JOIN pg_type t ON t.oid = e.enumtypid "
                "WHERE t.typname = :name"
            ),
            {"name": pg_type},
        )
        labels = {r[0] for r in rows}
    assert labels == {m.name for m in py_enum}


async def test_proxy_enums_insert_select_roundtrip(
    pg_session: AsyncSession,
) -> None:
    """Every member of every proxy enum survives INSERT → SELECT → filter."""
    tag = uuid4().hex[:8]
    proxies: list[ValidProxy] = []
    base_port = 0
    try:
        for i, fmt in enumerate(ProxyFormatType):
            src = ProxySourceConfig(
                name=f"enum-rt-{tag}-{fmt.name}",
                url=f"http://source-{i}.invalid/list",
                format_type=fmt,
            )
            pg_session.add(src)

        base_port = 20000 + uuid4().int % 30000
        port = base_port
        for protocol in ProxyProtocol:
            for health in ProxyHealthStatus:
                port += 1
                proxy = ValidProxy(
                    ip=f"198.51.100.{port % 250}",
                    port=port,
                    protocol=protocol,
                    health=health,
                    success_count=0,
                    failure_count=0,
                )
                pg_session.add(proxy)
                proxies.append(proxy)
        await pg_session.commit()

        # SELECT through ORM filters (bind params use the member *name*).
        for fmt in ProxyFormatType:
            got = (
                await pg_session.execute(
                    select(ProxySourceConfig).where(
                        ProxySourceConfig.name == f"enum-rt-{tag}-{fmt.name}",
                        ProxySourceConfig.format_type == fmt,
                    )
                )
            ).scalar_one()
            assert got.format_type is fmt

        ids = [p.id for p in proxies]
        pg_session.expire_all()
        for protocol in ProxyProtocol:
            for health in ProxyHealthStatus:
                got_proxy = (
                    await pg_session.execute(
                        select(ValidProxy).where(
                            ValidProxy.id.in_(ids),
                            ValidProxy.protocol == protocol,
                            ValidProxy.health == health,
                        )
                    )
                ).scalar_one()
                assert got_proxy.protocol is protocol
                assert got_proxy.health is health
    finally:
        await pg_session.rollback()
        await pg_session.execute(
            delete(ValidProxy).where(
                ValidProxy.ip.like("198.51.100.%"),
                ValidProxy.port.between(base_port + 1, base_port + len(proxies)),
            )
        )
        await pg_session.execute(
            delete(ProxySourceConfig).where(
                ProxySourceConfig.name.like(f"enum-rt-{tag}-%")
            )
        )
        await pg_session.commit()


async def test_pool_stats_and_random_healthy_on_real_postgres(
    pg_session: AsyncSession,
) -> None:
    """``/proxies/stats`` + rotation's ``get_random_healthy`` run on PG.

    Both queries filter on ``health == HEALTHY`` — the exact statement that
    raised ``InvalidTextRepresentationError`` before the casing migration.
    """
    tag = uuid4().int % 40000 + 20000
    healthy = ValidProxy(
        ip="198.51.100.200", port=tag, protocol=ProxyProtocol.HTTP,
        health=ProxyHealthStatus.HEALTHY, success_count=0, failure_count=0,
    )
    dead = ValidProxy(
        ip="198.51.100.201", port=tag, protocol=ProxyProtocol.HTTP,
        health=ProxyHealthStatus.UNHEALTHY, success_count=0, failure_count=0,
    )
    pg_session.add_all([healthy, dead])
    await pg_session.commit()
    try:
        service = ValidProxyService(pg_session)
        stats = await service.get_pool_stats()
        assert stats["healthy"] >= 1
        assert stats["unhealthy"] >= 1
        assert stats["total"] == stats["healthy"] + stats["unhealthy"]

        # Rotation: exclude every healthy row except ours → ours is returned;
        # exclude ours too → pool is dry.
        all_healthy = (
            await pg_session.execute(
                select(ValidProxy.id).where(
                    ValidProxy.health == ProxyHealthStatus.HEALTHY
                )
            )
        ).scalars().all()
        others = [pid for pid in all_healthy if pid != healthy.id]
        picked = await service.get_random_healthy(exclude_ids=others)
        assert picked is not None and picked.id == healthy.id
        assert await service.get_random_healthy(exclude_ids=all_healthy) is None
    finally:
        await pg_session.execute(
            delete(ValidProxy).where(ValidProxy.id.in_([healthy.id, dead.id]))
        )
        await pg_session.commit()
