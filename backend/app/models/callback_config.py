"""CallbackConfig — webhook definition for post-crawl callbacks."""

from uuid import UUID

from sqlalchemy import Boolean, Enum as SQLEnum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import CallbackMethod


class CallbackConfig(Base, UUIDMixin, TimestampMixin):
    """Webhook configuration attached to a CrawlSchedule (1:1).

    After all jobs from a schedule run complete, the callback is fired
    with the extraction results mapped according to ``field_mapping``.

    ``field_mapping`` format
    ------------------------
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
    - ``$.data.*``      — extraction result fields
    - ``$.url``         — source URL
    - ``$.metadata.*``  — job_id, schedule_id, timestamp, http_status, duration_ms
    - ``static_fields`` — constant fields added to every payload
    - ``wrap_key``      — wrap the mapped result under this key (null = flat)
    """

    __tablename__ = "callback_configs"

    schedule_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_schedules.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # ── Endpoint ─────────────────────────────────────────────────
    url: Mapped[str] = mapped_column(
        String(2000), nullable=False,
    )
    method: Mapped[CallbackMethod] = mapped_column(
        SQLEnum(CallbackMethod, name="callback_method_enum"),
        nullable=False,
        default=CallbackMethod.POST,
    )

    # ── Auth / Headers ───────────────────────────────────────────
    headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True,
    )

    # ── Payload mapping ──────────────────────────────────────────
    field_mapping: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict,
    )

    # ── Behaviour ────────────────────────────────────────────────
    include_metadata: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )
    batch_results: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )

    # ── Retry ────────────────────────────────────────────────────
    retry_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=3,
    )
    retry_delay_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=30,
    )

    # ── Status ───────────────────────────────────────────────────
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True,
    )

    # ── Relationships ────────────────────────────────────────────
    schedule: Mapped["CrawlSchedule"] = relationship(
        "CrawlSchedule", back_populates="callback",
    )

    def __repr__(self) -> str:
        return (
            f"<CallbackConfig(id={self.id}, "
            f"url='{self.url[:60]}', method={self.method.value})>"
        )
