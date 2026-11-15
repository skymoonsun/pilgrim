"""Password hashing (scrypt), JWT issuing/verification and the auth gate.

Adapted from byte-realm's ``app.core.security`` (JWT + passlib scrypt):
scrypt hashes, a signed JWT whose ``sub`` carries the user id, and FastAPI
dependencies for protected routes.

Gate modes (``PILGRIM_AUTH_MODE``)
---------------------------------
- ``read-open`` (default): GET/HEAD/OPTIONS stay public for local
  single-operator use; every mutating request (POST/PATCH/PUT/DELETE)
  requires a valid bearer token.
- ``strict``: everything requires a token — reads included — except
  ``/auth/login`` (which must stay public to obtain a token) and the
  ``/health/*`` probes (kept reachable for process monitors).

The webhook callback flow is outbound (pilgrim POSTs to *your* endpoints
with its own ``X-Signature`` secret), so the gate deliberately ignores it.
"""

import logging
import uuid
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.database import get_async_session
from app.models.user import User

logger = logging.getLogger(__name__)

# scrypt — memory-hard KDF (matches the byte-realm login contract).
pwd_context = CryptContext(schemes=["scrypt"], deprecated="auto")

# 401 instead of 403 when the header is missing entirely (byte-realm parity).
bearer_scheme = HTTPBearer(auto_error=False)

# Methods that count as reads for the read-open mode.
READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# Path prefixes always exempt from the gate.  Login is exempt by
# construction (mounted without the gate dependency); the health probes stay
# reachable for process monitors in strict deployments.
_EXEMPT_PATH_PREFIXES = ("/api/v1/health",)

# Length of the entropy payload for create-user generated passwords
# (token_urlsafe(20) ≈ 96 bits).
GENERATED_PASSWORD_LENGTH = 20


def hash_password(password: str) -> str:
    """Hash a plaintext password with scrypt."""
    return str(pwd_context.hash(password))


def generate_password() -> str:
    """Generate a one-time password for the create-user CLI."""
    return token_urlsafe(GENERATED_PASSWORD_LENGTH)


def verify_password(plain: str, hashed: str) -> bool:
    """Verify a plaintext password against a scrypt hash."""
    return bool(pwd_context.verify(plain, hashed))


def create_access_token(
    *,
    user_id: str,
    username: str,
    ttl_seconds: int | None = None,
) -> str:
    """Create a signed JWT for a user (byte-realm parity: TTL default 3600)."""
    settings = get_settings()
    ttl = ttl_seconds if ttl_seconds is not None else settings.jwt_ttl_seconds
    now = datetime.now(tz=UTC)
    payload: dict[str, str | int] = {
        "sub": user_id,
        "username": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(seconds=ttl)).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return str(jwt.encode(payload, settings.jwt_secret, algorithm="HS256"))


def decode_access_token(token: str) -> dict[str, str | int]:
    """Decode and verify a JWT.

    Raises ``jwt.PyJWTError`` on invalid/expired tokens.
    """
    settings = get_settings()
    decoded: dict[str, str | int] = jwt.decode(
        token,
        settings.jwt_secret,
        algorithms=["HS256"],
    )
    return decoded


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    """Fetch a user by username or return ``None``."""
    result = await session.execute(
        select(User).where(User.username == username)
    )
    return result.scalar_one_or_none()


async def authenticate_user(
    session: AsyncSession, username: str, password: str
) -> User | None:
    """Return the active user when credentials match, ``None`` otherwise."""
    user = await get_user_by_username(session, username)
    if user is None:
        # Still burn a scrypt hash to keep timing roughly uniform and avoid
        # username probing (byte-realm parity).
        verify_password(password, hash_password(password))
        return None
    if not verify_password(password, user.password):
        return None
    return user


def _credentials_error(detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"},
    )


async def resolve_user(
    credentials: HTTPAuthorizationCredentials | None,
    session: AsyncSession,
) -> User:
    """Validate a bearer token and load the user it refers to.

    Raises ``HTTPException(401)`` for missing/invalid tokens or unknown /
    deactivated users.
    """
    if credentials is None:
        raise _credentials_error("Missing bearer token")

    try:
        payload = decode_access_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        logger.info("Rejected invalid token: %s", exc)
        raise _credentials_error("Invalid or expired token") from exc

    try:
        user_pk = uuid.UUID(str(payload["sub"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise _credentials_error("Invalid token subject") from exc

    user = await session.get(User, user_pk)
    if user is None:
        raise _credentials_error("User not found")
    if not user.is_active:
        raise _credentials_error("User is deactivated")
    return user


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> User:
    """Dependency: require a valid bearer token and return the user."""
    return await resolve_user(credentials, session)


async def authorize(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_async_session),
) -> None:
    """Router-level gate: method-aware auth per ``PILGRIM_AUTH_MODE``.

    Mutations are always gated; the mode only decides whether reads are
    also gated (``strict``) or stay public (``read-open``).
    """
    path = request.url.path
    if any(path.startswith(p) for p in _EXEMPT_PATH_PREFIXES):
        return

    settings = get_settings()
    is_read = request.method in READ_METHODS
    if is_read and settings.auth_mode == "read-open":
        return

    await resolve_user(credentials, session)
