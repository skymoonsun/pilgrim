"""ScheduleConfigLink — M2M between CrawlSchedule and CrawlConfiguration.

Each link owns its own URL target set, so URLs are config-specific.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScheduleConfigLink(Base, UUIDMixin, TimestampMixin):
    """Links a schedule to one of its crawl configurations.

    Each config link has its own set of target URLs.  When the schedule
    triggers, every (config, url) pair within the link produces a
    ``CrawlJob`` — *not* the cartesian product across all links.
    """

    __tablename__ = "schedule_config_links"

    schedule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    config_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_configurations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # ── Relationships ────────────────────────────────────────────
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="config_links",
    )
    config: Mapped["CrawlConfiguration"] = relationship(
        "CrawlConfiguration",
    )
    url_targets: Mapped[list["ScheduleUrlTarget"]] = relationship(
        "ScheduleUrlTarget",
        back_populates="config_link",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduleConfigLink(schedule={self.schedule_id}, "
            f"config={self.config_id}, urls={len(self.url_targets)})>"
        )
