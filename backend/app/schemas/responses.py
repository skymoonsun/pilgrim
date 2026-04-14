"""Generic response wrappers."""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic paginated response envelope."""

    items: list[T]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool = Field(..., description="Whether there are more pages")
    has_prev: bool = Field(
        ..., description="Whether there are previous pages"
    )

    @classmethod
    def create(
        cls,
        items: list[T],
        total: int,
        page: int,
        per_page: int,
    ) -> "PaginatedResponse[T]":
        pages = max(1, (total + per_page - 1) // per_page)
        return cls(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1,
        )


class ErrorResponse(BaseModel):
    """Standard error response model for Swagger documentation."""

    error: dict = Field(..., description="Error details")
