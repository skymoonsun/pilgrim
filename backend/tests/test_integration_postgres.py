"""Opt-in integration probe: real PostgreSQL is REQUIRED here.

Marked ``integration``, so conftest skips it on every run unless
``PILGRIM_RUN_INTEGRATION=1`` is exported — CI and local runs never set
it.  It exists to prove the marker mechanism and to give an opt-in
smoke check against the configured database URL.
"""

import os
import subprocess
import sys
from collections.abc import AsyncIterator, Collection
from enum import Enum
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.models.enums import (
    ProxyFormatType,
    ProxyHealthStatus,
    ProxyProtocol,
    ScraperProfile,
)
from app.models.proxy_source_config import ProxySourceConfig
from app.models.valid_proxy import ValidProxy
from app.services.proxy_rotation import (
    ProxyRotationReport,
    fetch_with_proxy_rotation,
    proxy_label,
)
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


def _pid(proxy: ValidProxy) -> UUID:
    """``proxy.id`` as plain ``uuid.UUID``.

    UUIDMixin annotates ``id`` with SQLAlchemy's UUID sqltype, so the
    raw attribute fails mypy's ``Collection[UUID]`` args — cast the
    runtime value once here.
    """
    return cast(UUID, proxy.id)


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


# ── Alembic fresh-reproduction sync ──────────────────────────────────
#
# The live pools above are audited at whatever revision the target DB
# happens to sit on.  The remaining drift path is *reproduction*: the
# migration chain itself must rebuild the name-cased enums from scratch
# (``b2c3d4e5f6a7`` creates lowercase labels, ``f6a7b8c9d0e1`` adds
# ``PENDING``, ``l1m2n3o4p5q6`` renames them).  A future migration that
# re-creates an enum with wrong casing, or a model member without the
# matching ``ALTER TYPE ... ADD VALUE``, would pass every test above on
# an already-migrated DB.  This test re-runs ``alembic upgrade head``
# against a throwaway database and audits the pg_enum labels, so CI
# fails on the fresh-reproduction path itself.


async def test_fresh_alembic_reproduction_syncs_proxy_enums() -> None:
    """``alembic upgrade head`` on an empty DB rebuilds synced enums."""
    source_url = make_url(str(get_settings().database_url))
    throwaway = f"enum_audit_reprod_{uuid4().hex[:8]}"
    # render_as_string(hide_password=False): plain str() masks the
    # password as "***", which then fails auth everywhere downstream.
    fresh_url = source_url.set(database=throwaway).render_as_string(
        hide_password=False
    )
    admin_url = source_url.set(database="postgres").render_as_string(
        hide_password=False
    )

    admin = create_async_engine(str(admin_url), isolation_level="AUTOCOMMIT")
    try:
        async with admin.connect() as conn:
            await conn.execute(text(f'CREATE DATABASE "{throwaway}"'))
    finally:
        await admin.dispose()

    proc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=str(Path(__file__).resolve().parent.parent),
        env={
            **os.environ,
            "DATABASE_URL": str(fresh_url),
        },
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )

    try:
        assert proc.returncode == 0, (
            "alembic upgrade head failed on a fresh database:\n"
            f"stderr: {proc.stderr[-2000:]}"
        )

        fresh_engine = create_async_engine(str(fresh_url))
        try:
            async with fresh_engine.connect() as conn:
                version = (
                    await conn.execute(text("SELECT version_num FROM alembic_version"))
                ).scalar_one()
                for pg_type, py_enum in PROXY_ENUMS:
                    rows = await conn.execute(
                        text(
                            "SELECT e.enumlabel FROM pg_enum e "
                            "JOIN pg_type t ON t.oid = e.enumtypid "
                            "WHERE t.typname = :name"
                        ),
                        {"name": pg_type},
                    )
                    labels = {r[0] for r in rows}
                    assert labels == {m.name for m in py_enum}, (
                        f"fresh alembic reproduction produced enum {pg_type} "
                        f"with labels {sorted(labels)}; expected member names "
                        f"{sorted(m.name for m in py_enum)}"
                    )
        finally:
            await fresh_engine.dispose()
        # The throwaway DB sat at a single real head revision.
        assert isinstance(version, str) and len(version) >= 12
    finally:
        drop_admin = create_async_engine(str(admin_url), isolation_level="AUTOCOMMIT")
        try:
            async with drop_admin.connect() as conn:
                await conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE datname = :db AND pid <> pg_backend_pid()"
                    ),
                    {"db": throwaway},
                )
                await conn.execute(text(f'DROP DATABASE "{throwaway}"'))
        finally:
            await drop_admin.dispose()


# ── Two-proxy rotation on real PostgreSQL ────────────────────────────
#
# tests/test_proxy_rotation_two_proxies.py pins the exclusion-based
# rotation contract on SQLite.  Against real PostgreSQL the selection
# statement (``WHERE health = 'HEALTHY'``) is enum-qualified — the
# exact filter that was broken pre-l1m2n3o4p5q6.  This parity test
# re-runs the same deterministic sequence over the real PG session.  A
# hermetic base-exclusion keeps strays from the shared live pool out.


async def test_two_proxy_rotation_sequence_on_real_postgres(
    pg_session: AsyncSession,
) -> None:
    """Exactly two healthy proxies rotate deterministically over real PG."""
    service = ValidProxyService(pg_session)
    tag = 20000 + uuid4().int % 30000
    proxies = [
        ValidProxy(
            ip=f"203.0.113.{10 + i}",
            port=tag + i,
            protocol=ProxyProtocol.HTTP,
            health=ProxyHealthStatus.HEALTHY,
            success_count=0,
            failure_count=0,
        )
        for i in range(2)
    ]
    pg_session.add_all(proxies)
    await pg_session.commit()
    try:
        # Strays healthy in the shared pool are excluded everywhere.
        base_ids: set[UUID] = {
            pid
            for pid in (
                await pg_session.execute(
                    select(ValidProxy.id).where(
                        ValidProxy.health == ProxyHealthStatus.HEALTHY
                    )
                )
            ).scalars().all()
            if cast(UUID, pid) not in {_pid(p) for p in proxies}
        }

        async def select_proxy(tried: Collection[UUID]) -> ValidProxy | None:
            return await service.get_random_healthy(
                exclude_ids={*base_ids, *tried}
            )

        # 1. Excluding one proxy must always select the other.
        first, second = proxies
        other = await select_proxy({_pid(first)})
        got = await select_proxy({_pid(second)})
        assert other is not None and got is not None
        assert other.id == _pid(second)
        assert got.id == _pid(first)

        # 2. A failing first attempt must land on the other proxy, and
        #    never retry the failed one.
        report = ProxyRotationReport()
        calls: list[bool] = []

        def flaky_fetch(kwargs: dict[str, Any]) -> str:
            if not calls:
                calls.append(False)
                raise RuntimeError("proxy down")
            calls.append(True)
            return "ok"

        response = await fetch_with_proxy_rotation(
            fetch=flaky_fetch,
            select_proxy=select_proxy,
            profile=ScraperProfile.FETCHER,
            max_attempts=2,
            report=report,
        )
        assert response == "ok"
        labels = [e.proxy for e in report.attempts]
        assert len(labels) == 2 and labels[0] != labels[1]
        assert report.attempts[0].ok is False
        assert report.used_proxy == labels[1]
        assert {labels[0], labels[1]} == {
            proxy_label(first),
            proxy_label(second),
        }

        # 3. Pool exhausted → both proxies attempted (distinct), then a
        #    direct fallback whose exception propagates (documented:
        #    "Raises whatever the final (direct) fetch raised"), with
        #    the report fully filled.
        report_exhausted = ProxyRotationReport()

        def dead_fetch(kwargs: dict[str, Any]) -> str:
            raise RuntimeError("proxy down")

        with pytest.raises(RuntimeError, match="proxy down"):
            await fetch_with_proxy_rotation(
                fetch=dead_fetch,
                select_proxy=select_proxy,
                profile=ScraperProfile.FETCHER,
                max_attempts=2,
                report=report_exhausted,
            )
        assert report_exhausted.fell_back_direct is True
        assert report_exhausted.fallback_reason == "all_proxy_attempts_failed"
        exhausted_labels = [e.proxy for e in report_exhausted.attempts]
        assert len(exhausted_labels) == 2
        assert set(exhausted_labels) == {proxy_label(first), proxy_label(second)}
    finally:
        await pg_session.execute(
            delete(ValidProxy).where(
                ValidProxy.id.in_([_pid(p) for p in proxies])
            )
        )
        await pg_session.commit()
