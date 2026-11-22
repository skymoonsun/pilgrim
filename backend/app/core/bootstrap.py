"""Env-tanımlı seed kullanıcı bootstrap (byte-realm parity).

``PILGRIM_USERNAME`` / ``PILGRIM_PASSWORD`` env'leri ayarlıysa, startup'ta
idempotent şekilde o kullanıcıyı yaratır: DB'de varsa dokunmaz, yoksa
scrypt hash'le ekler.  Env boşsa seed atlanır.

Bu aynı credentials'lar core tarafında (``app/services/pilgrim.py`` +
core settings ``PILGRIM_USERNAME/PILGRIM_PASSWORD``) core → pilgrim
dispatch'lerin login akışında kullanılır — değeri core .env ile senkron tut.
"""

from __future__ import annotations

import logging

from sqlalchemy import select

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.database import async_session_factory
from app.models.user import User

logger = logging.getLogger(__name__)


async def ensure_seed_user() -> None:
    """Create the env-configured seed user if configured and missing."""
    settings = get_settings()
    username = getattr(settings, "seed_username", None)
    password = getattr(settings, "seed_password", None)
    if not username or not password:
        logger.info(
            "SEED USER: PILGRIM_USERNAME/PILGRIM_PASSWORD (veya PILGRIM_SEED_*) set edilmemiş — "
            "seed atlandı"
        )
        return

    async with async_session_factory() as session:
        existing = (
            await session.execute(select(User).where(User.username == username))
        ).scalar_one_or_none()
        if existing is not None:
            logger.info("SEED USER: '%s' mevcut — seed atlandı", username)
            return

        user = User(username=username, password=hash_password(password))
        session.add(user)
        await session.commit()
        await session.refresh(user)
        logger.info("SEED USER: '%s' yaratıldı (id=%s)", username, user.id)
