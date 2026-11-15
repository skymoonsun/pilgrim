"""Auth request/response schemas."""

from pydantic import BaseModel, ConfigDict, Field


class LoginRequest(BaseModel):
    """POST /api/v1/auth/login body."""

    username: str = Field(min_length=1, max_length=180)
    password: str = Field(min_length=1)


class TokenResponse(BaseModel):
    """``{token: ...}`` — byte-realm login response parity."""

    token: str


class UserOut(BaseModel):
    """Safe user representation (never includes the password hash)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    is_active: bool


class CurrentUserResponse(UserOut):
    """Response for GET /api/v1/auth/me (authenticated user info)."""
