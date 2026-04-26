"""CrawlJob model — authoritative job status lives here, not in Redis."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    Enum as SQLEnum,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import CrawlJobStatus


class CrawlJob(Base, UUIDMixin, TimestampMixin):
    """A single crawl execution tied to a configuration and target URL."""

    __tablename__ = "crawl_jobs"

    # ── Config reference ─────────────────────────────────────────
    crawl_configuration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Target ───────────────────────────────────────────────────
    target_url: Mapped[str] = mapped_column(
        String(2000), nullable=False
    )

    # ── Status ───────────────────────────────────────────────────
    status: Mapped[CrawlJobStatus] = mapped_column(
        SQLEnum(CrawlJobStatus, name="crawl_job_status_enum"),
        nullable=False,
        default=CrawlJobStatus.QUEUED,
        index=True,
    )

    # ── Timing ───────────────────────────────────────────────────
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True,
    )

    # ── Celery auxiliary ─────────────────────────────────────────
    celery_task_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    queue: Mapped[str] = mapped_column(
        String(64), nullable=False, default="crawl_default", index=True
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )

    # ── Results ──────────────────────────────────────────────────
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )
    result_summary: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── Relationships ────────────────────────────────────────────
    crawl_configuration: Mapped["CrawlConfiguration"] = relationship(
        "CrawlConfiguration", back_populates="crawl_jobs"
    )
    results: Mapped[list["CrawlJobResult"]] = relationship(
        "CrawlJobResult",
        back_populates="crawl_job",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlJob(id={self.id}, status={self.status.value}, "
            f"url='{self.target_url[:60]}')>"
        )
