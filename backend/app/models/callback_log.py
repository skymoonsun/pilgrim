"""CallbackLog — audit trail for outbound webhook calls."""

from uuid import UUID

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CallbackLog(Base, UUIDMixin, TimestampMixin):
    """Records each callback attempt (success or failure).

    Provides a full audit trail including the request payload sent,
    the response received, and retry attempt number.
    """

    __tablename__ = "callback_logs"

    callback_config_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("callback_configs.id", ondelete="CASCADE"),
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

    # ── Request ──────────────────────────────────────────────────
    request_url: Mapped[str] = mapped_column(
        String(2000), nullable=False,
    )
    request_method: Mapped[str] = mapped_column(
        String(10), nullable=False,
    )
    request_body: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )

    # ── Response ─────────────────────────────────────────────────
    response_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
    )
    response_body: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )

    # ── Outcome ──────────────────────────────────────────────────
    success: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False,
    )
    error_message: Mapped[str | None] = mapped_column(
        Text, nullable=True,
    )
    duration_ms: Mapped[float] = mapped_column(
        Float, nullable=False, default=0,
    )
    attempt_number: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1,
    )

    # ── Relationships ────────────────────────────────────────────
    callback_config: Mapped["CallbackConfig"] = relationship(
        "CallbackConfig",
    )
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="callback_logs",
    )

    def __repr__(self) -> str:
        return (
            f"<CallbackLog(id={self.id}, "
            f"success={self.success}, attempt={self.attempt_number})>"
        )
