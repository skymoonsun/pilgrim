"""add schedule_type and proxy_source_links table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-04-19 19:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e5f6a7b8c9d0'
down_revision: Union[str, None] = 'd4e5f6a7b8c9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create schedule_type_enum
    schedule_type_enum = postgresql.ENUM(
        'crawl', 'proxy_source', name='schedule_type_enum', create_type=True,
    )
    schedule_type_enum.create(op.get_bind(), checkfirst=True)

    # Add schedule_type column to crawl_schedules
    op.add_column(
        'crawl_schedules',
        sa.Column(
            'schedule_type',
            schedule_type_enum,
            nullable=False,
            server_default='crawl',
        ),
    )

    # Create schedule_proxy_source_links table
    op.create_table(
        'schedule_proxy_source_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('crawl_schedules.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('proxy_source_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('proxy_source_configs.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table('schedule_proxy_source_links')

    op.drop_column('crawl_schedules', 'schedule_type')

    schedule_type_enum = postgresql.ENUM(name='schedule_type_enum')
    schedule_type_enum.drop(op.get_bind(), checkfirst=True)