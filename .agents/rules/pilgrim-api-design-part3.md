---
trigger: glob
globs: "app/api/**/*.py"
description: "Pilgrim service: api-design — segment 3/3. Mirrors .cursor/rules/api-design.mdc."
---

# Pilgrim — api design (part 3/3)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/api-design.mdc`.

## 5. Operational endpoints (crawl, configs, schedules, Celery)

### Crawl job lifecycle (enqueue via Celery)
```python
# File: app/api/v1/endpoints/crawl.py
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_admin_user, get_async_session, get_current_user
from app.schemas.crawl import CrawlJobCreate, CrawlJobResponse, CrawlStats
from app.services.crawl_job_service import CrawlJobService
from app.workers.tasks.scrape import run_crawl_job

router = APIRouter()


@router.post("/jobs", status_code=status.HTTP_202_ACCEPTED)
async def enqueue_crawl_job(
    body: CrawlJobCreate,
    session: AsyncSession = Depends(get_async_session),
    _: dict = Depends(get_admin_user),
) -> dict[str, str]:
    """Create job row and enqueue Celery task (do not run Scrapling in-process)."""
    service = CrawlJobService(session)
    job = await service.create_and_enqueue(body)
    run_crawl_job.apply_async(args=[str(job.id)], queue=body.queue or "crawl_default")
    return {"crawl_job_id": str(job.id), "status": "queued"}


@router.get("/jobs/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_job(
    job_id: UUID,
    session: AsyncSession = Depends(get_async_session),
    _: dict = Depends(get_current_user),
) -> CrawlJobResponse:
    service = CrawlJobService(session)
    job = await service.get_by_id(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found")
    return CrawlJobResponse.model_validate(job)


@router.get("/stats", response_model=CrawlStats)
async def get_crawl_stats(
    store_id: Optional[int] = Query(None),
    days: int = Query(7, ge=1, le=90),
    session: AsyncSession = Depends(get_async_session),
    _: dict = Depends(get_current_user),
) -> CrawlStats:
    return await CrawlJobService(session).aggregate_stats(store_id=store_id, days=days)
```

### Crawl configuration CRUD
```python
# File: app/api/v1/endpoints/crawl_configs.py
# REST: GET/POST /crawl-configs, GET/PATCH/DELETE /crawl-configs/{id}
# Payloads include scraper_profile (http|http_session|stealth|dynamic|spider),
# fetch_options JSON, extraction_spec JSON, store_id, is_active.
```

### Schedule CRUD (drives Celery Beat)
```python
# File: app/api/v1/endpoints/schedules.py
# REST: GET/POST /schedules, GET/PATCH/DELETE /schedules/{id}
# Fields: crawl_config_id, cron or interval_seconds, timezone (UTC), is_active, queue.
# Beat process loads due rows and enqueues run_crawl_job (or dedicated batch task).
```

### Celery task inspection (optional)
```python
# File: app/api/v1/endpoints/tasks.py
from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_admin_user
from app.integrations.celery_inspect import get_task_meta

router = APIRouter()


@router.get("/celery/{task_id}")
async def get_celery_task_state(
    task_id: str,
    _: dict = Depends(get_admin_user),
) -> dict:
    """Return Celery AsyncResult state/meta (Redis backend). Not a substitute for DB job row."""
    meta = get_task_meta(task_id)
    if meta is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown task id")
    return meta
```

### Health check endpoints
```python
# File: app/api/v1/endpoints/health.py
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_async_session
from app.integrations.redis import ping_redis

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, str]:
    return {"status": "healthy", "service": "Pilgrim", "version": "1.0.0"}


@router.get("/readiness")
async def readiness_check(session: AsyncSession = Depends(get_async_session)) -> dict[str, str]:
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="database_unavailable",
        )
    try:
        await ping_redis()
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="redis_unavailable",
        )
    return {"status": "ready"}


@router.get("/detailed")
async def detailed_health(session: AsyncSession = Depends(get_async_session)) -> JSONResponse:
    """Optional: Celery inspect ping from workers — can be slow; use behind admin auth."""
    components = {
        "database": "ok",
        "redis": "ok",
        "celery_workers": "unknown",
    }
    code = status.HTTP_200_OK
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        components["database"] = "error"
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    try:
        await ping_redis()
    except Exception:
        components["redis"] = "error"
        code = status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content={"components": components})


@router.get("/liveness")
async def liveness_check() -> dict[str, str]:
    return {"status": "alive"}
```

## 6. Response Models and Documentation

### Comprehensive Response Models
```python
# File: app/schemas/responses.py
from typing import Generic, TypeVar, Optional, List
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar('T')

class APIResponse(BaseModel, Generic[T]):
    """Generic API response wrapper."""
    success: bool = True
    data: Optional[T] = None
    message: Optional[str] = None
    
class PaginatedResponse(BaseModel, Generic[T]):
    """Paginated response wrapper."""
    items: List[T]
    total: int
    page: int
    per_page: int
    pages: int
    has_next: bool = Field(..., description="Whether there are more pages")
    has_prev: bool = Field(..., description="Whether there are previous pages")
    
    @classmethod
    def create(
        cls, 
        items: List[T], 
        total: int, 
        page: int, 
        per_page: int
    ) -> "PaginatedResponse[T]":
        """Create paginated response."""
        pages = (total + per_page - 1) // per_page
        return cls(
            items=items,
            total=total,
            page=page,
            per_page=per_page,
            pages=pages,
            has_next=page < pages,
            has_prev=page > 1
        )

class ErrorResponse(BaseModel):
    """Error response model."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": {
                    "code": "GAME_NOT_FOUND",
                    "message": "Game with ID 123 not found",
                    "type": "application_error",
                }
            }
        }
    )

    error: dict = Field(..., description="Error details")
```

These guidelines keep Pilgrim APIs consistent with Celery-backed crawling and Scrapling workers.