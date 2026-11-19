"""align proxy enums with SQLAlchemy name-based storage

``b2c3d4e5f6a7`` hand-created ``proxy_health_status_enum`` /
``proxy_protocol_enum`` / ``proxy_format_type_enum`` with lowercase
*values* (``healthy``, ``http``, ``raw_text`` ...), while the models map them
with ``sa.Enum(<PyEnum>)`` which persists member *names* (``HEALTHY``,
``HTTP``, ``RAW_TEXT`` ...).  On a real PostgreSQL every proxy list / stats /
insert therefore failed with

    invalid input value for enum proxy_health_status_enum: "HEALTHY"

(``f6a7b8c9d0e1`` had already added ``PENDING`` in uppercase, so the health
enum was a mix.)  Same defect class as ``h1i2j3k4l5m6`` (schedule_type_enum).

``ALTER TYPE ... RENAME VALUE`` (PostgreSQL 10+) renames the label in place:
enum columns store the label's OID, so existing rows follow automatically and
no UPDATE is needed.  None of the three columns carries a server_default or a
partial index/CHECK that embeds a literal, so nothing else has to be
re-pointed.  Each rename is guarded so the migration is idempotent against
databases that were already hand-fixed (``IF`` on ``pg_enum``).

Revision ID: l1m2n3o4p5q6
Revises: k0l9m8n7o6p5
Create Date: 2026-11-19 13:00:00
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l1m2n3o4p5q6"
down_revision: str | None = "k0l9m8n7o6p5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# (enum type, [(lowercase value, member name), ...]).  ``pending`` is already
# ``PENDING`` in the DB (added uppercase by f6a7b8c9d0e1) — not renamed.
_RENAMES: list[tuple[str, list[tuple[str, str]]]] = [
    (
        "proxy_health_status_enum",
        [("healthy", "HEALTHY"), ("degraded", "DEGRADED"), ("unhealthy", "UNHEALTHY")],
    ),
    (
        "proxy_protocol_enum",
        [
            ("http", "HTTP"),
            ("https", "HTTPS"),
            ("socks4", "SOCKS4"),
            ("socks5", "SOCKS5"),
        ],
    ),
    (
        "proxy_format_type_enum",
        [("raw_text", "RAW_TEXT"), ("json", "JSON"), ("xml", "XML"), ("csv", "CSV")],
    ),
]


def _rename(enum_name: str, old: str, new: str) -> None:
    """Rename one enum label iff ``old`` exists (idempotent)."""
    op.execute(
        f"""
        DO $$ BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_enum e JOIN pg_type t ON t.oid = e.enumtypid
                WHERE t.typname = '{enum_name}' AND e.enumlabel = '{old}'
            ) THEN
                ALTER TYPE {enum_name} RENAME VALUE '{old}' TO '{new}';
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    for enum_name, pairs in _RENAMES:
        for old, new in pairs:
            _rename(enum_name, old, new)


def downgrade() -> None:
    for enum_name, pairs in _RENAMES:
        for old, new in pairs:
            _rename(enum_name, new, old)
