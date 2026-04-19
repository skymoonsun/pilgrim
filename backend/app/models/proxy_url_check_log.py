"""ProxyUrlCheckLog model — per-URL validation metrics (performance matrix)."""

from sqlalchemy import Float, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProxyUrlCheckLog(Base, UUIDMixin, TimestampMixin):
    """Per-URL proxy validation results — the performance matrix."""

    __tablename__ = "proxy_url_check_logs"

    validation_log_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_validation_logs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    source_config_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_source_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Per-URL metrics ──
    url: Mapped[str] = mapped_column(String(2000), nullable=False)
    proxies_tested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_passed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_response_ms: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ── Relationships ──
    validation_log: Mapped["ProxyValidationLog"] = relationship(
        "ProxyValidationLog", back_populates="url_checks",
    )
    source_config: Mapped["ProxySourceConfig"] = relationship("ProxySourceConfig")

    def __repr__(self) -> str:
        return f"<ProxyUrlCheckLog(id={self.id}, url={self.url[:50]})>"