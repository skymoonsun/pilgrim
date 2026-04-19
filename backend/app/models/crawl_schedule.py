"""CrawlSchedule model — periodic job triggers with multi-config + multi-URL support."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ScheduleType


class CrawlSchedule(Base, UUIDMixin, TimestampMixin):
    """Schedule definition for recurring crawl jobs or proxy source fetches.

    A schedule can be linked to **multiple CrawlConfigurations** (via
    ``ScheduleConfigLink``) and **multiple target URLs** (via
    ``ScheduleUrlTarget``).  When triggered, every (config, url) pair
    produces a separate ``CrawlJob``.

    For ``proxy_source`` schedules, it links to ProxySourceConfig via
    ``ScheduleProxySourceLink``.  On trigger, each linked proxy source
    is fetched and validated.

    Exactly one of ``cron_expression`` or ``interval_seconds`` should be
    set.  Enforcement is done at the application / schema level.
    """

    __tablename__ = "crawl_schedules"

    # ── Metadata ─────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(200), nullable=False,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True,
    )

    # ── Schedule type ────────────────────────────────────────────
    schedule_type: Mapped[ScheduleType] = mapped_column(
        SQLEnum(ScheduleType, name="schedule_type_enum"),
        nullable=False,
        default=ScheduleType.CRAWL,
        server_default="crawl",
    )

    # ── Schedule definition ──────────────────────────────────────
    timezone: Mapped[str] = mapped_column(
        String(64), nullable=False, default="UTC",
    )
    cron_expression: Mapped[str | None] = mapped_column(
        String(128), nullable=True,
    )
    interval_seconds: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )

    # ── Queue routing ────────────────────────────────────────────
    default_queue: Mapped[str] = mapped_column(
        String(64), nullable=False, default="crawl_default",
    )

    # ── Run tracking ─────────────────────────────────────────────
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True, nullable=True,
    )
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    run_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
    )

    # ── Relationships ────────────────────────────────────────────
    config_links: Mapped[list["ScheduleConfigLink"]] = relationship(
        "ScheduleConfigLink",
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduleConfigLink.priority",
    )
    proxy_source_links: Mapped[list["ScheduleProxySourceLink"]] = relationship(
        "ScheduleProxySourceLink",
        back_populates="schedule",
        cascade="all, delete-orphan",
        order_by="ScheduleProxySourceLink.priority",
    )
    callback: Mapped["CallbackConfig | None"] = relationship(
        "CallbackConfig",
        back_populates="schedule",
        uselist=False,
        cascade="all, delete-orphan",
    )
    callback_logs: Mapped[list["CallbackLog"]] = relationship(
        "CallbackLog",
        back_populates="schedule",
        cascade="all, delete-orphan",
    )
    email_notification: Mapped["EmailNotificationConfig | None"] = relationship(
        "EmailNotificationConfig",
        back_populates="schedule",
        uselist=False,
        cascade="all, delete-orphan",
    )
    email_notification_logs: Mapped[list["EmailNotificationLog"]] = relationship(
        "EmailNotificationLog",
        back_populates="schedule",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        schedule_type = (
            f"cron='{self.cron_expression}'"
            if self.cron_expression
            else f"interval={self.interval_seconds}s"
        )
        return f"<CrawlSchedule(id={self.id}, name='{self.name}', {schedule_type})>"
