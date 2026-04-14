"""SeedVersion model — tracks which seed files have been applied."""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class SeedVersion(Base):
    """Tracks applied seed versions, similar to Alembic's version table."""

    __tablename__ = "seed_versions"

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True
    )
    version: Mapped[str] = mapped_column(
        String(50), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(
        String(255), nullable=False
    )
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<SeedVersion(version='{self.version}', name='{self.name}')>"
