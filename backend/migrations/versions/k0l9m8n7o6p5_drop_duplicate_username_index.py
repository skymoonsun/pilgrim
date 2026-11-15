"""drop the redundant duplicate unique index on users.username

Revision ID: k0l9m8n7o6p5
Revises: j9k8l7m6n5o4
Create Date: 2026-11-15 21:30:00.000000

j9k8l7m6n5o4 created users.username twice-unique: the
``UniqueConstraint('username')`` (which already maintains its own unique
index, e.g. ``users_username_key`` on Postgres) *plus* an explicit
``ix_users_username`` unique index — two identical indexes on the same
column.  This revision drops the explicit one; uniqueness is kept by the
constraint.  The ORM model matches (``unique=True``, no ``index=True``).
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'k0l9m8n7o6p5'
down_revision: str | None = 'j9k8l7m6n5o4'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index('ix_users_username', table_name='users')


def downgrade() -> None:
    op.create_index(
        'ix_users_username', 'users', ['username'], unique=True
    )
