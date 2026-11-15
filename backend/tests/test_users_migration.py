"""users.username duplicate-index migration test (k0l9m8n7o6p5).

j9k8l7m6n5o4 left ``users`` with TWO unique indexes on username: the
``UniqueConstraint`` (its own backing index) plus the explicit
``ix_users_username``.  The migration drops the explicit one while the
constraint keeps uniqueness — verified here against a real SQLite
database by replaying the exact pre-migration state and running the
revision's ``upgrade()``/``downgrade()`` through Alembic's operations
proxy (no Postgres required).
"""

from __future__ import annotations

import importlib.util
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    Index,
    MetaData,
    String,
    Table,
    UniqueConstraint,
    create_engine,
    insert,
    inspect,
)
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

_MIGRATION_FILE = (
    Path(__file__).resolve().parents[1]
    / "migrations"
    / "versions"
    / "k0l9m8n7o6p5_drop_duplicate_username_index.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "k0l9m8n7o6p5_migration", _MIGRATION_FILE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def engine() -> Iterator[Engine]:
    """SQLite engine holding users EXACTLY as j9k8l7m6n5o4 left it."""
    engine = create_engine("sqlite://", poolclass=StaticPool)
    md = MetaData()
    Table(
        "users",
        md,
        Column("id", String(32), primary_key=True),
        Column("username", String(180), nullable=False),
        Column("password", String(255), nullable=False),
        UniqueConstraint("username"),
        # The redundant explicit unique index (kept by j9k8l7m6n5o4).
        Index("ix_users_username", "username", unique=True),
    )
    md.create_all(engine)
    try:
        yield engine
    finally:
        engine.dispose()


def _index_names(engine: Engine, table: str = "users") -> dict[str, bool]:
    inspector = inspect(engine)
    names: dict[str, bool] = {}
    for idx in inspector.get_indexes(table):
        name = idx["name"]
        if name is not None:
            names[name] = bool(idx["unique"])
    return names


def _run_revision(engine: Engine, fn_name: str) -> None:
    migration = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(migration, fn_name)()


class TestDropDuplicateUsernameIndex:
    def test_pre_state_has_duplicate_index_and_uniqueness(
        self, engine: Engine
    ) -> None:
        indexes = _index_names(engine)
        assert indexes["ix_users_username"]  # the redundant explicit index

        # Uniqueness already enforced BEFORE the migration (constraint).
        metadata = MetaData()
        users = Table("users", metadata, autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(
                insert(users).values(id="u1", username="op", password="h")
            )
            with pytest.raises(IntegrityError):
                conn.execute(
                    insert(users).values(id="u2", username="op", password="h")
                )

    def test_upgrade_drops_duplicate_keeps_uniqueness(
        self, engine: Engine
    ) -> None:
        _run_revision(engine, "upgrade")

        indexes = _index_names(engine)
        assert "ix_users_username" not in indexes

        # Uniqueness still enforced by the constraint's backing index.
        metadata = MetaData()
        users = Table("users", metadata, autoload_with=engine)
        with engine.begin() as conn:
            conn.execute(
                insert(users).values(id="u1", username="op", password="h")
            )
            with pytest.raises(IntegrityError):
                conn.execute(
                    insert(users).values(id="u2", username="op", password="h")
                )

    def test_downgrade_recreates_the_index(self, engine: Engine) -> None:
        _run_revision(engine, "upgrade")
        _run_revision(engine, "downgrade")

        indexes = _index_names(engine)
        assert indexes.get("ix_users_username")  # recreated, unique flag set

    def test_revision_chains_on_top_of_users_table(self) -> None:
        migration = _load_migration()
        assert migration.down_revision == "j9k8l7m6n5o4"
