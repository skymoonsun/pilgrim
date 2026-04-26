"""add sanitizer_configs table and FK to crawl_configurations

Revision ID: h8i9j0k1l2m3
Revises: g7h8i9j0k1l2
Create Date: 2026-04-26 12:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'h8i9j0k1l2m3'
down_revision: Union[str, None] = 'g7h8i9j0k1l2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create sanitizer_configs table
    op.create_table(
        'sanitizer_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('name', sa.String(100), nullable=False, unique=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('rules', postgresql.JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('ix_sanitizer_configs_name', 'sanitizer_configs', ['name'], unique=True)
    op.create_index('ix_sanitizer_configs_is_active', 'sanitizer_configs', ['is_active'])

    # Add sanitizer_config_id FK to crawl_configurations
    op.add_column(
        'crawl_configurations',
        sa.Column('sanitizer_config_id', postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        'fk_crawl_configurations_sanitizer_config_id',
        'crawl_configurations', 'sanitizer_configs',
        ['sanitizer_config_id'], ['id'],
        ondelete='SET NULL',
    )
    op.create_index(
        'ix_crawl_configurations_sanitizer_config_id',
        'crawl_configurations', ['sanitizer_config_id'],
    )


def downgrade() -> None:
    # Drop FK and column from crawl_configurations
    op.drop_index('ix_crawl_configurations_sanitizer_config_id', table_name='crawl_configurations')
    op.drop_constraint('fk_crawl_configurations_sanitizer_config_id', 'crawl_configurations', type_='foreignkey')
    op.drop_column('crawl_configurations', 'sanitizer_config_id')

    # Drop sanitizer_configs table
    op.drop_index('ix_sanitizer_configs_is_active', table_name='sanitizer_configs')
    op.drop_index('ix_sanitizer_configs_name', table_name='sanitizer_configs')
    op.drop_table('sanitizer_configs')