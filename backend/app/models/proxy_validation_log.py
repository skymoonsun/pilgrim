"""ProxyValidationLog model — audit record for each proxy validation run."""

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class ProxyValidationLog(Base, UUIDMixin, TimestampMixin):
    """Records the outcome of each proxy validation run."""

    __tablename__ = "proxy_validation_logs"

    source_config_id: Mapped[str] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_source_configs.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # ── Outcome ──
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    proxies_tested: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_healthy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_degraded: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_unhealthy: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    proxies_removed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # ── Relationships ──
    source_config: Mapped["ProxySourceConfig"] = relationship(
        "ProxySourceConfig", back_populates="validation_logs",
    )
    url_checks: Mapped[list["ProxyUrlCheckLog"]] = relationship(
        "ProxyUrlCheckLog", back_populates="validation_log",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ProxyValidationLog(id={self.id}, source={self.source_config_id}, status={self.status})>"