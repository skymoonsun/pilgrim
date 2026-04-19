"""add_proxy_management_tables

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-04-19 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ─────────────────────────────────────────────
    # Use create_type=False since SQLAlchemy model metadata already
    # creates these enums when models are imported by Alembic env.py.
    # We still need the ENUM objects for column definitions below.
    proxy_format_type = postgresql.ENUM(
        'raw_text', 'json', 'xml', 'csv',
        name='proxy_format_type_enum',
        create_type=False,
    )
    proxy_protocol = postgresql.ENUM(
        'http', 'https', 'socks4', 'socks5',
        name='proxy_protocol_enum',
        create_type=False,
    )
    proxy_health_status = postgresql.ENUM(
        'healthy', 'degraded', 'unhealthy',
        name='proxy_health_status_enum',
        create_type=False,
    )

    # Ensure enum types exist (safe if already created by model import)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'proxy_format_type_enum') THEN
                CREATE TYPE proxy_format_type_enum AS ENUM ('raw_text', 'json', 'xml', 'csv');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'proxy_protocol_enum') THEN
                CREATE TYPE proxy_protocol_enum AS ENUM ('http', 'https', 'socks4', 'socks5');
            END IF;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'proxy_health_status_enum') THEN
                CREATE TYPE proxy_health_status_enum AS ENUM ('healthy', 'degraded', 'unhealthy');
            END IF;
        END $$;
    """)

    # ── proxy_source_configs ────────────────────────────────────
    op.create_table(
        'proxy_source_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('url', sa.String(length=2000), nullable=False),
        sa.Column('format_type', proxy_format_type, nullable=False),
        sa.Column('extraction_spec', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('source_headers', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('validation_urls', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('require_all_urls', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('validation_timeout', sa.Integer(), nullable=False, server_default=sa.text('10')),
        sa.Column('fetch_interval_seconds', sa.Integer(), nullable=False, server_default=sa.text('3600')),
        sa.Column('proxy_ttl_seconds', sa.Integer(), nullable=False, server_default=sa.text('86400')),
        sa.Column('last_fetched_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_fetch_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_proxy_source_configs_name'),
        'proxy_source_configs',
        ['name'],
        unique=True,
    )
    op.create_index(
        op.f('ix_proxy_source_configs_is_active'),
        'proxy_source_configs',
        ['is_active'],
    )
    op.create_index(
        op.f('ix_proxy_source_configs_created_at'),
        'proxy_source_configs',
        ['created_at'],
    )
    op.create_index(
        op.f('ix_proxy_source_configs_updated_at'),
        'proxy_source_configs',
        ['updated_at'],
    )

    # ── valid_proxies ───────────────────────────────────────────
    op.create_table(
        'valid_proxies',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('source_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('ip', sa.String(length=45), nullable=False),
        sa.Column('port', sa.Integer(), nullable=False),
        sa.Column('protocol', proxy_protocol, nullable=False),
        sa.Column('username', sa.String(length=255), nullable=True),
        sa.Column('password', sa.String(length=255), nullable=True),
        sa.Column('health', proxy_health_status, nullable=False),
        sa.Column('avg_response_ms', sa.Float(), nullable=True),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('failure_count', sa.Integer(), nullable=False, server_default=sa.text('0')),
        sa.Column('last_checked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_success_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['source_config_id'],
            ['proxy_source_configs.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('ip', 'port', 'protocol', name='uq_proxy_ip_port_protocol'),
    )
    op.create_index(
        op.f('ix_valid_proxies_source_config_id'),
        'valid_proxies',
        ['source_config_id'],
    )
    op.create_index(
        op.f('ix_valid_proxies_ip'),
        'valid_proxies',
        ['ip'],
    )
    op.create_index(
        op.f('ix_valid_proxies_protocol'),
        'valid_proxies',
        ['protocol'],
    )
    op.create_index(
        op.f('ix_valid_proxies_health'),
        'valid_proxies',
        ['health'],
    )
    op.create_index(
        op.f('ix_valid_proxies_last_checked_at'),
        'valid_proxies',
        ['last_checked_at'],
    )
    op.create_index(
        op.f('ix_valid_proxies_expires_at'),
        'valid_proxies',
        ['expires_at'],
    )
    op.create_index(
        op.f('ix_valid_proxies_created_at'),
        'valid_proxies',
        ['created_at'],
    )
    op.create_index(
        op.f('ix_valid_proxies_updated_at'),
        'valid_proxies',
        ['updated_at'],
    )


def downgrade() -> None:
    op.drop_table('valid_proxies')
    op.drop_table('proxy_source_configs')

    op.execute("DROP TYPE IF EXISTS proxy_health_status_enum")
    op.execute("DROP TYPE IF EXISTS proxy_protocol_enum")
    op.execute("DROP TYPE IF EXISTS proxy_format_type_enum")