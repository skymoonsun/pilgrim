"""make_source_config_id_nullable

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-04-19 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'valid_proxies', 'source_config_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=True,
        existing_nullable=False,
    )


def downgrade() -> None:
    # Only safe if no manual (source_config_id=NULL) proxies exist
    op.alter_column(
        'valid_proxies', 'source_config_id',
        existing_type=postgresql.UUID(as_uuid=True),
        nullable=False,
        existing_nullable=True,
    )