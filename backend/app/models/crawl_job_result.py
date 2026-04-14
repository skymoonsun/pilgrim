"""CrawlJobResult model — per-URL extraction outcome."""

from uuid import UUID

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin


class CrawlJobResult(Base, UUIDMixin, TimestampMixin):
    """Individual extraction result attached to a crawl job."""

    __tablename__ = "crawl_job_results"

    crawl_job_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("crawl_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    source_url: Mapped[str] = mapped_column(
        String(2000), nullable=False
    )
    http_status: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
    payload: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(
        String(64), nullable=True
    )

    # ── Relationships ────────────────────────────────────────────
    crawl_job: Mapped["CrawlJob"] = relationship(
        "CrawlJob", back_populates="results"
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlJobResult(id={self.id}, "
            f"url='{self.source_url[:60]}', "
            f"http_status={self.http_status})>"
        )
