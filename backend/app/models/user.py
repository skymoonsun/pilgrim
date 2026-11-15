"""User model — login account for the API auth gate.

One row per login account.  Passwords are stored as scrypt hashes
(passlib); plaintext never touches the database.  Users are created
via the ``create-user`` CLI command, which generates and prints the
password once — there is no registration endpoint by design.
"""

from typing import Any

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, UUIDMixin


class User(Base, UUIDMixin, TimestampMixin):
    """API user (JWT ``sub`` = user id)."""

    __tablename__ = "users"

    # unique=True keeps exactly ONE unique index on username (the
    # constraint's backing index).  The old explicit ``ix_users_username``
    # duplicate was dropped in migration k0l9m8n7o6p5.
    username: Mapped[str] = mapped_column(
        String(180), unique=True, nullable=False
    )
    # scrypt hash (passlib CryptContext); never store plaintext.
    password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(
        nullable=False,
        default=True,
        server_default="true",
    )

    def __repr__(self) -> str:
        return (
            f"<User id={self.id} username={self.username!r} is_active={self.is_active}>"
        )

    def to_token_claims(self) -> dict[str, Any]:
        """Claims embedded into the JWT payload."""
        return {"sub": str(self.id), "username": self.username}
