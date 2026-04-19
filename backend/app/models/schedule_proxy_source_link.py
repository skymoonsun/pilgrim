"""ScheduleProxySourceLink — M2M between CrawlSchedule and ProxySourceConfig.

Used by proxy_source schedules to define which proxy sources to
fetch + validate on trigger.
"""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ScheduleProxySourceLink(Base, UUIDMixin, TimestampMixin):
    """Links a proxy_source schedule to a ProxySourceConfig."""

    __tablename__ = "schedule_proxy_source_links"

    schedule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    proxy_source_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_source_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # ── Relationships ────────────────────────────────────────────
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="proxy_source_links",
    )
    proxy_source: Mapped["ProxySourceConfig"] = relationship(
        "ProxySourceConfig",
    )

    def __repr__(self) -> str:
        return (
            f"<ScheduleProxySourceLink(schedule={self.schedule_id}, "
            f"proxy_source={self.proxy_source_id})>"
        )