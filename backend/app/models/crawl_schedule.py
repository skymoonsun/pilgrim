"""CrawlSchedule model — periodic job triggers (consumed by Celery Beat)."""

from datetime import datetime
from uuid import UUID

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CrawlSchedule(Base, UUIDMixin, TimestampMixin):
    """Schedule definition for recurring crawl jobs.

    Exactly one of ``cron_expression`` or ``interval_seconds`` should be
    set.  Enforcement is done at the application / schema level.
    """

    __tablename__ = "crawl_schedules"

    crawl_configuration_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Target URL for scheduled runs ────────────────────────────
    target_url: Mapped[str] = mapped_column(
        String(2000), nullable=False
    )

    # ── Schedule definition ──────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True
    )
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC"
    )
    cron_expression: Mapped[str | None] = mapped_column(
        String(128), nullable=True
    )
    interval_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ── Queue routing ────────────────────────────────────────────
    default_queue: Mapped[str] = mapped_column(
        String(64), nullable=False, default="crawl_default"
    )

    # ── Next planned run ─────────────────────────────────────────
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True
    )

    # ── Relationships ────────────────────────────────────────────
    crawl_configuration: Mapped["CrawlConfiguration"] = relationship(
        "CrawlConfiguration", back_populates="schedules"
    )

    def __repr__(self) -> str:
        schedule_type = (
            f"cron='{self.cron_expression}'"
            if self.cron_expression
            else f"interval={self.interval_seconds}s"
        )
        return f"<CrawlSchedule(id={self.id}, {schedule_type})>"
