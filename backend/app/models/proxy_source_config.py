"""ProxySourceConfig model — defines a proxy list source."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum as SQLEnum, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ProxyFormatType


class ProxySourceConfig(Base, UUIDMixin, TimestampMixin):
    """A source URL that provides a list of proxy servers."""

    __tablename__ = "proxy_source_configs"

    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True
    )

    # ── Source config ──────────────────────────────────────────
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    format_type: Mapped[ProxyFormatType] = mapped_column(
        SQLEnum(ProxyFormatType, name="proxy_format_type_enum"),
        nullable=False,
        default=ProxyFormatType.RAW_TEXT,
    )
    extraction_spec: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    source_headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── Validation config ─────────────────────────────────────
    validation_urls: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )
    require_all_urls: Mapped[bool] = mapped_column(Boolean, default=True)
    validation_timeout: Mapped[int] = mapped_column(
        Integer, default=10
    )

    # ── Fetch config ──────────────────────────────────────────
    fetch_interval_seconds: Mapped[int] = mapped_column(
        Integer, default=3600
    )
    proxy_ttl_seconds: Mapped[int] = mapped_column(
        Integer, default=86400
    )

    # ── Status ────────────────────────────────────────────────
    last_fetched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_fetch_error: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )

    # ── Relationships ─────────────────────────────────────────
    valid_proxies: Mapped[list["ValidProxy"]] = relationship(
        "ValidProxy",
        back_populates="source_config",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return (
            f"<ProxySourceConfig(id={self.id}, name='{self.name}', "
            f"format={self.format_type.value})>"
        )