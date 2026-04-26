"""SanitizerConfig model — field-level transformation rules for extracted data."""

from sqlalchemy import Boolean, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class SanitizerConfig(Base, UUIDMixin, TimestampMixin):
    """Reusable set of sanitizer rules applied after extraction.

    Each rule targets a field name and defines an ordered list of
    transforms (strip, regex_replace, to_number, etc.).
    Linked to CrawlConfiguration via ``sanitizer_config_id`` FK.
    """

    __tablename__ = "sanitizer_configs"

    # ── Metadata ─────────────────────────────────────────────────
    name: Mapped[str] = mapped_column(
        String(100), nullable=False, unique=True, index=True,
    )
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, nullable=False, index=True,
    )

    # ── Rules (JSONB) ─────────────────────────────────────────────
    # [
    #   {"field": "price", "transforms": [
    #     {"type": "regex_replace", "pattern": "[^0-9.]", "replacement": ""},
    #     {"type": "to_number"}
    #   ]},
    #   {"field": "title", "transforms": [{"type": "strip"}, {"type": "to_lower"}]}
    # ]
    rules: Mapped[list] = mapped_column(
        JSONB, nullable=False, default=list,
    )

    def __repr__(self) -> str:
        return f"<SanitizerConfig(id={self.id}, name='{self.name}')>"