"""CLI — create an API user; the password is printed to the terminal once.

Usage (inside the API container)::

    python -m app.cli.create_user <username>
    python -m app.cli.create_user <username> --password <plaintext>

No ``--password`` = a random high-entropy password is generated.  The
plaintext password exists only in this output (and the scrypt hash in the
database) — passlib scrypt, same scheme the login endpoint verifies.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.security import generate_password, hash_password


async def _create_user(username: str, password: str | None) -> int:
    """Insert the user; returns a process exit code."""
    from app.models.user import User

    settings = get_settings()
    engine = create_async_engine(str(settings.database_url))
    factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    try:
        async with factory() as session:
            existing = await session.execute(
                select(User).where(User.username == username)
            )
            if existing.scalar_one_or_none() is not None:
                print(f"ERROR: user {username!r} already exists", file=sys.stderr)
                return 2

            plaintext = password or generate_password()
            session.add(
                User(username=username, password=hash_password(plaintext))
            )
            await session.commit()
    finally:
        await engine.dispose()

    print(f"User created: {username}")
    print(
        "Password (printed once — store it now, it is never shown again):"
    )
    print(plaintext)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m app.cli.create_user",
        description="Create an API login user (scrypt hashed password).",
    )
    parser.add_argument("username", help="Login username (<= 180 chars)")
    parser.add_argument(
        "--password",
        default=None,
        help="Plaintext password; omit to generate a random one",
    )
    args = parser.parse_args()
    sys.exit(asyncio.run(_create_user(args.username, args.password)))


if __name__ == "__main__":
    main()
