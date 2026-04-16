"""EmailNotificationLog — audit trail for outbound email notifications."""

from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class EmailNotificationLog(Base, UUIDMixin, TimestampMixin):
    """Records each email notification attempt (success or failure).

    Provides a full audit trail including the recipients, subject,
    rendered HTML body, and SMTP response details.
    """

    __tablename__ = "email_notification_logs"

    email_notification_config_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("email_notification_configs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    crawl_job_id: Mapped[UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    schedule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_schedules.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # ── Email details ──────────────────────────────────────────────
    recipients: Mapped[dict] = mapped_column(
        JSONB, nullable=False,
        comment='List of email addresses sent to',
    )
    subject: Mapped[str] = mapped_column(
        String(500), nullable=False,
    )
    body_html: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    trigger_reason: Mapped[str] = mapped_column(
        String(32), nullable=False,
        comment='"success" or "failure"',
    )

    # ── Outcome ────────────────────────────────────────────────────
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    smtp_response_code: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )
    duration_ms: Mapped[float] = mapped_column(
        Float, nullable=False, default=0,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )

    # ── Relationships ──────────────────────────────────────────────
    email_notification_config: Mapped["EmailNotificationConfig"] = relationship(
        "EmailNotificationConfig",
    )
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="email_notification_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<EmailNotificationLog(id={self.id}, "
            f"success={self.success}, trigger={self.trigger_reason})>"
        )