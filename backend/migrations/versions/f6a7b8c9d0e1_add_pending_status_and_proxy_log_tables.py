"""add pending health status and proxy log tables

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-04-20 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6a7b8c9d0e1'
down_revision: Union[str, None] = 'e5f6a7b8c9d0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add 'pending' value to proxy_health_status_enum
    # Must run outside transaction — ALTER TYPE ADD VALUE is transactional
    # in PG12+ but Alembic's transaction handling can cause issues
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE proxy_health_status_enum ADD VALUE IF NOT EXISTS 'PENDING'")

    # Create proxy_fetch_logs table
    op.create_table(
        'proxy_fetch_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_config_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('proxy_source_configs.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('proxies_found', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_new', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_updated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_truncated', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('content_length', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Float(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Create proxy_validation_logs table
    op.create_table(
        'proxy_validation_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('source_config_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('proxy_source_configs.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('status', sa.String(16), nullable=False),
        sa.Column('proxies_tested', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_healthy', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_degraded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_unhealthy', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_removed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('duration_ms', sa.Float(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )

    # Create proxy_url_check_logs table
    op.create_table(
        'proxy_url_check_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('validation_log_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('proxy_validation_logs.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('source_config_id', postgresql.UUID(as_uuid=True),
                   sa.ForeignKey('proxy_source_configs.id', ondelete='CASCADE'),
                   nullable=False, index=True),
        sa.Column('url', sa.String(2000), nullable=False),
        sa.Column('proxies_tested', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_passed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('proxies_failed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('avg_response_ms', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('proxy_url_check_logs')
    op.drop_table('proxy_validation_logs')
    op.drop_table('proxy_fetch_logs')

    # Note: PostgreSQL does not support ALTER TYPE DROP VALUE.
    # The 'pending' enum value will remain in the type but is harmless
    # if no rows reference it. To fully remove, the enum must be recreated.