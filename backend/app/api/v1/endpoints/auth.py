"""Auth endpoints — POST /login (JWT) and GET /me.

Mounted *without* the router-level auth gate on purpose: a client must be
able to reach /login without a token to obtain one.  Everything else on the
v1 router goes through ``app.core.security.authorize`` (see app/main.py).
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import authenticate_user, create_access_token, get_current_user
from app.db.database import get_async_session
from app.models.user import User
from app.schemas.auth import CurrentUserResponse, LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest,
    session: Annotated[AsyncSession, Depends(get_async_session)],
) -> TokenResponse:
    """Validate credentials and return a signed JWT.

    The password itself never leaves the CLI that created the user —
    ``python -m app.cli.create_user <username>`` prints it once.
    """
    user = await authenticate_user(session, body.username, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return TokenResponse(
        token=create_access_token(
            user_id=str(user.id), username=user.username
        )
    )


@router.get("/me", response_model=CurrentUserResponse)
async def me(user: User = Depends(get_current_user)) -> CurrentUserResponse:
    """Return the authenticated user (handy for smoke-testing a token)."""
    return CurrentUserResponse(
        id=str(user.id),
        username=user.username,
        is_active=user.is_active,
    )


__all__ = ["router"]
