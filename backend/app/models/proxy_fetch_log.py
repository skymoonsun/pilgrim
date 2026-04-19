"""ProxyFetchLog model — audit record for each proxy source fetch."""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProxyFetchLog(Base, UUIDMixin, TimestampMixin):
    """Records the outcome of each proxy source fetch attempt."""

    __tablename__ = "proxy_fetch_logs"

    source_config_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_source_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Outcome ──
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    proxies_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_new: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_truncated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    content_length: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──
    source_config: Mapped["ProxySourceConfig"] = relationship(
        "ProxySourceConfig", back_populates="fetch_logs",
    )

    def __repr__(self) -> str:
        return f"<ProxyFetchLog(id={self.id}, source={self.source_config_id}, status={self.status})>"