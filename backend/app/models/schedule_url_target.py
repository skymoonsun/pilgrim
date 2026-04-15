"""ScheduleUrlTarget — URL set for a CrawlSchedule."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScheduleUrlTarget(Base, UUIDMixin, TimestampMixin):
    """A single target URL belonging to a schedule's URL set.

    When the schedule triggers, each active URL is crawled with every
    linked configuration.
    """

    __tablename__ = "schedule_url_targets"

    schedule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    url: Mapped[str] = mapped_column(
        String(2000), nullable=False,
    )
    label: Mapped[str | None] = mapped_column(
        String(200), nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )

    # ── Relationships ────────────────────────────────────────────
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="url_targets",
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduleUrlTarget(id={self.id}, "
            f"url='{self.url[:60]}', active={self.is_active})>"
        )
