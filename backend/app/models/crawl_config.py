"""CrawlConfiguration model — the scraping recipe."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Boolean, Enum as SQLEnum, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDMixin
from app.models.enums import ScraperProfile


class CrawlConfiguration(Base, UUIDMixin, TimestampMixin):
    """Versioned crawl recipe: how workers fetch and extract data.

    This model is site-URL agnostic — the target URL is provided at
    runtime when a scrape or crawl job is triggered.
    """

    __tablename__ = "crawl_configurations"

    # ── Metadata ─────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True
    )

    # ── Scrapling profile ────────────────────────────────────────
    scraper_profile: Mapped[ScraperProfile] = mapped_column(
        SQLEnum(ScraperProfile, name="scraper_profile_enum"),
        nullable=False,
        default=ScraperProfile.FETCHER,
        index=True,
    )

    # ── Fetch behaviour (JSONB) ──────────────────────────────────
    # Timeouts, retries, impersonate, stealthy_headers, etc.
    fetch_options: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── Extraction spec (JSONB) ──────────────────────────────────
    # CSS / XPath selectors, field mappings, post-processors
    extraction_spec: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict
    )

    # ── Optional spider entrypoint ───────────────────────────────
    spider_entrypoint: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )

    # ── Proxy & headers ──────────────────────────────────────────
    use_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    rotate_user_agent: Mapped[bool] = mapped_column(Boolean, default=True)
    custom_headers: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )
    cookies: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True
    )

    # ── Rate limiting ────────────────────────────────────────────
    custom_delay: Mapped[Decimal | None] = mapped_column(
        Numeric(5, 2), nullable=True
    )
    max_concurrent: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    # ── Sanitizer ────────────────────────────────────────────────
    sanitizer_config_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sanitizer_configs.id"),
        nullable=True,
        index=True,
    )

    # ── Relationships ────────────────────────────────────────────
    crawl_jobs: Mapped[list["CrawlJob"]] = relationship(
        "CrawlJob",
        back_populates="crawl_configuration",
        cascade="all, delete-orphan",
    )
    sanitizer_config: Mapped["SanitizerConfig | None"] = relationship(
        "SanitizerConfig",
    )

    def __repr__(self) -> str:
        return (
            f"<CrawlConfiguration(id={self.id}, name='{self.name}', "
            f"profile={self.scraper_profile.value})>"
        )
