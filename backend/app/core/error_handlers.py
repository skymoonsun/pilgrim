"""Global exception handlers registered on the FastAPI application."""

import logging

from fastapi import HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import AppException

logger = logging.getLogger(__name__)

# ── Status mapping ───────────────────────────────────────────────
_STATUS_MAP: dict[str | None, int] = {
    "CONFIG_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "JOB_NOT_FOUND": status.HTTP_404_NOT_FOUND,
    "CRAWLING_ERROR": status.HTTP_502_BAD_GATEWAY,
    "RATE_LIMIT_EXCEEDED": status.HTTP_429_TOO_MANY_REQUESTS,
    "EXTRACTION_ERROR": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "AI_DISABLED": status.HTTP_503_SERVICE_UNAVAILABLE,
    "AI_LLM_ERROR": status.HTTP_502_BAD_GATEWAY,
    "AI_CONNECTION_ERROR": status.HTTP_502_BAD_GATEWAY,
    "AI_INVALID_PAGE": status.HTTP_422_UNPROCESSABLE_ENTITY,
    "AI_EMPTY_SPEC": status.HTTP_422_UNPROCESSABLE_ENTITY,
}


async def app_exception_handler(
    request: Request,
    exc: AppException,
) -> JSONResponse:
    """Handle custom application exceptions."""
    logger.error("Application error: %s", exc.message, extra={"code": exc.code})

    response_status = _STATUS_MAP.get(
        exc.code, status.HTTP_500_INTERNAL_SERVER_ERROR
    )
    headers: dict[str, str] = {}
    if hasattr(exc, "retry_after"):
        headers["Retry-After"] = str(exc.retry_after)

    return JSONResponse(
        status_code=response_status,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "type": "application_error",
            }
        },
        headers=headers,
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """Handle request validation errors."""
    logger.warning("Validation error: %s", exc.errors())
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Request validation failed",
                "type": "validation_error",
                "details": exc.errors(),
            }
        },
    )


async def database_exception_handler(
    request: Request,
    exc: IntegrityError,
) -> JSONResponse:
    """Handle database integrity errors."""
    logger.error("Database integrity error: %s", str(exc))
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": {
                "code": "DATABASE_CONSTRAINT_ERROR",
                "message": "Database constraint violation",
                "type": "database_error",
            }
        },
    )


async def generic_exception_handler(
    request: Request,
    exc: Exception,
) -> JSONResponse:
    """Handle unexpected exceptions."""
    logger.error("Unexpected error: %s", str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "An unexpected error occurred",
                "type": "server_error",
            }
        },
    )
