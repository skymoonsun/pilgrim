"""ValidProxy model — a validated proxy server."""

from datetime import datetime

from sqlalchemy import DateTime, Enum as SQLEnum, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ProxyHealthStatus, ProxyProtocol


class ValidProxy(Base, UUIDMixin, TimestampMixin):
    """A proxy server that has been fetched and validated."""

    __tablename__ = "valid_proxies"
    __table_args__ = (
        UniqueConstraint("ip", "port", "protocol", name="uq_proxy_ip_port_protocol"),
    )

    source_config_id: Mapped[str | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("proxy_source_configs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    ip: Mapped[str] = mapped_column(String(45), nullable=False, index=True)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    protocol: Mapped[ProxyProtocol] = mapped_column(
        SQLEnum(ProxyProtocol, name="proxy_protocol_enum"),
        nullable=False,
        index=True,
        default=ProxyProtocol.HTTP,
    )
    username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    password: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # ── Health metrics ────────────────────────────────────────
    health: Mapped[ProxyHealthStatus] = mapped_column(
        SQLEnum(ProxyHealthStatus, name="proxy_health_status_enum"),
        nullable=False,
        default=ProxyHealthStatus.HEALTHY,
        index=True,
    )
    avg_response_ms: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)

    # ── Timestamps ────────────────────────────────────────────
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )

    # ── Relationships ──────────────────────────────────────────
    source_config: Mapped["ProxySourceConfig | None"] = relationship(
        "ProxySourceConfig", back_populates="valid_proxies", foreign_keys=[source_config_id]
    )

    def __repr__(self) -> str:
        return (
            f"<ValidProxy(id={self.id}, ip={self.ip}:{self.port}, "
            f"protocol={self.protocol.value}, health={self.health.value})>"
        )