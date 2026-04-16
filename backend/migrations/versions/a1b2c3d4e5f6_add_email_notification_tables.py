"""add_email_notification_tables

Revision ID: a1b2c3d4e5f6
Revises: f5e266ee1acd
Create Date: 2026-04-16 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'f5e266ee1acd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── email_notification_configs ─────────────────────────────────
    op.create_table(
        'email_notification_configs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recipient_emails', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('subject_template', sa.String(length=500), nullable=False),
        sa.Column('field_mapping', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('include_metadata', sa.Boolean(), nullable=False),
        sa.Column('batch_results', sa.Boolean(), nullable=False),
        sa.Column('on_success', sa.Boolean(), nullable=False),
        sa.Column('on_failure', sa.Boolean(), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['schedule_id'], ['crawl_schedules.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_email_notification_configs_schedule_id'),
        'email_notification_configs',
        ['schedule_id'],
        unique=True,
    )
    op.create_index(
        op.f('ix_email_notification_configs_created_at'),
        'email_notification_configs',
        ['created_at'],
    )
    op.create_index(
        op.f('ix_email_notification_configs_updated_at'),
        'email_notification_configs',
        ['updated_at'],
    )

    # ── email_notification_logs ────────────────────────────────────
    op.create_table(
        'email_notification_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('email_notification_config_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('crawl_job_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('schedule_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('recipients', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('subject', sa.String(length=500), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=True),
        sa.Column('trigger_reason', sa.String(length=32), nullable=False),
        sa.Column('success', sa.Boolean(), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('smtp_response_code', sa.Integer(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=False),
        sa.Column('attempt_number', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['email_notification_config_id'],
            ['email_notification_configs.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['crawl_job_id'],
            ['crawl_jobs.id'],
            ondelete='SET NULL',
        ),
        sa.ForeignKeyConstraint(
            ['schedule_id'],
            ['crawl_schedules.id'],
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_email_notification_logs_email_notification_config_id'),
        'email_notification_logs',
        ['email_notification_config_id'],
    )
    op.create_index(
        op.f('ix_email_notification_logs_crawl_job_id'),
        'email_notification_logs',
        ['crawl_job_id'],
    )
    op.create_index(
        op.f('ix_email_notification_logs_schedule_id'),
        'email_notification_logs',
        ['schedule_id'],
    )
    op.create_index(
        op.f('ix_email_notification_logs_created_at'),
        'email_notification_logs',
        ['created_at'],
    )
    op.create_index(
        op.f('ix_email_notification_logs_updated_at'),
        'email_notification_logs',
        ['updated_at'],
    )


def downgrade() -> None:
    op.drop_table('email_notification_logs')
    op.drop_table('email_notification_configs')