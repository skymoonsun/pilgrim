"""add started_at finished_at to crawl_jobs

Revision ID: g7h8i9j0k1l2
Revises: 53c456acad12
Create Date: 2026-04-20 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'g7h8i9j0k1l2'
down_revision: Union[str, None] = '53c456acad12'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('crawl_jobs', sa.Column('started_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('crawl_jobs', sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True))
    op.create_index(op.f('ix_crawl_jobs_started_at'), 'crawl_jobs', ['started_at'], unique=False)
    op.create_index(op.f('ix_crawl_jobs_finished_at'), 'crawl_jobs', ['finished_at'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_crawl_jobs_finished_at'), table_name='crawl_jobs')
    op.drop_index(op.f('ix_crawl_jobs_started_at'), table_name='crawl_jobs')
    op.drop_column('crawl_jobs', 'finished_at')
    op.drop_column('crawl_jobs', 'started_at')