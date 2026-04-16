"""EmailNotificationConfig — email notification definition for post-crawl emails."""

from uuid import UUID

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class EmailNotificationConfig(Base, UUIDMixin, TimestampMixin):
    """Email notification configuration attached to a CrawlSchedule (1:1).

    After crawl jobs from a schedule run complete, an email is sent to the
    configured recipients with the extraction results (or failure notice)
    mapped according to ``field_mapping`` (same syntax as CallbackConfig).

    ``field_mapping`` format
    ------------------------
    Same as CallbackConfig:
    ```json
    {
        "field_mapping": {
            "product_name": "$.data.title",
            "source": "$.url",
            "scraped_at": "$.metadata.timestamp"
        },
        "static_fields": {
            "source_system": "pilgrim"
        },
        "wrap_key": "results"
    }
    ```
    """

    __tablename__ = "email_notification_configs"

    schedule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_schedules.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Recipients ──────────────────────────────────────────────────
    recipient_emails: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment='List of email addresses, e.g. ["user@example.com"]',
    )

    # ── Content ────────────────────────────────────────────────────
    subject_template: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        default="Pilgrim: {{schedule_name}} completed",
        comment="Subject line with optional {{var}} placeholders",
    )
    field_mapping: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
    )

    # ── Behaviour ──────────────────────────────────────────────────
    include_metadata: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )
    batch_results: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="True = all results in one email; False = one per job",
    )
    on_success: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="Send email when job succeeds",
    )
    on_failure: Mapped[bool] = mapped_column(
        Boolean, default=True,
        comment="Send email when job fails",
    )

    # ── Status ─────────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )

    # ── Relationships ───────────────────────────────────────────────
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="email_notification",
    )

    def __repr__(self) -> str:
        return (
            f"<EmailNotificationConfig(id={self.id}, "
            f"recipients={self.recipient_emails})>"
        )