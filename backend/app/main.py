"""Pilgrim FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_router
from app.api.v1.endpoints import auth
from app.core.config import get_settings
from app.core.error_handlers import (
    app_exception_handler,
    database_exception_handler,
    generic_exception_handler,
    validation_exception_handler,
)
from app.core.exceptions import AppException
from app.core.logging import configure_logging
from app.core.security import authorize

settings = get_settings()


# ── Lifespan ─────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application startup / shutdown hooks."""
    configure_logging()
    yield
    # Shutdown: dispose DB engine pool
    from app.db.database import engine

    await engine.dispose()


# ── App ──────────────────────────────────────────────────────────
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description=(
        "**Pilgrim** — config-driven scraping & crawling microservice.\n\n"
        "Define scraping recipes (crawl configurations) via the API, "
        "then trigger scrapes by supplying a config ID and a target URL."
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# ── Exception handlers ───────────────────────────────────────────
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(
    RequestValidationError, validation_exception_handler
)
app.add_exception_handler(IntegrityError, database_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# ── Routers ──────────────────────────────────────────────────────
# The auth gate rides the whole v1 router.  It is method-aware: in the
# default ``read-open`` mode GET/HEAD/OPTIONS stay public and every
# mutation (POST/PATCH/PUT/DELETE) requires a bearer token; ``strict``
# gates reads too.  The auth router is mounted separately so /auth/login
# stays reachable without a token (that is the endpoint that issues one).
app.include_router(api_router, prefix="/api/v1", dependencies=[Depends(authorize)])
app.include_router(auth.router, prefix="/api/v1")


# ── Root redirect to docs ────────────────────────────────────────
@app.get("/", include_in_schema=False)
async def root() -> dict[str, str]:
    """Redirect callers to the interactive API docs."""
    return {
        "service": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
    }
