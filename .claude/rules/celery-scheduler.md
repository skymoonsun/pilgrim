---
paths:
  - "app/workers/**/*"
---

> Claude Code: modular rules in `.claude/rules/` — [Memory & rules](https://code.claude.com/docs/en/memory). Cursor equivalent: `.cursor/rules/celery-scheduler.mdc`.

# Celery Scheduler - Pilgrim Service

Pilgrim uses **Celery** with **Redis** as broker and (typically) result backend. **Celery Beat** drives periodic crawls from PostgreSQL-backed schedule definitions.

## 1. Application layout

```python
# app/workers/celery_app.py
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "pilgrim",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.tasks.scrape", "app.workers.tasks.maintenance"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=settings.celery_task_soft_time_limit_seconds,
    worker_prefetch_multiplier=1,  # fair distribution for long IO tasks
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)
```

## 2. Task naming and conventions

- **Module**: `app/workers/tasks/<domain>.py`
- **Name**: `pilgrim.<domain>.<verb>` e.g. `pilgrim.scrape.run_job`
- **Arguments**: JSON-serializable primitives + UUIDs as strings; reconstruct ORM objects inside the task via DB load.
- **Return**: small dict or job status payload; large payloads go to PostgreSQL or object storage, not Redis.

```python
# app/workers/tasks/scrape.py
from app.workers.celery_app import celery_app

@celery_app.task(
    name="pilgrim.scrape.run_job",
    bind=True,
    queue="crawl_default",
    autoretry_for=(TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
)
def run_crawl_job(self, crawl_job_id: str) -> dict[str, str]:
    """Execute a single crawl job by ID."""
    # Load job from DB, run pipeline, persist results
    return {"crawl_job_id": crawl_job_id, "status": "completed"}
```

## 3. Queues and routing

| Queue | Purpose |
|-------|---------|
| `crawl_high` | Manual / priority runs |
| `crawl_default` | Standard periodic workload |
| `crawl_low` | Backfill, large spiders |
| `maintenance` | Housekeeping |

```python
celery_app.conf.task_routes = {
    "pilgrim.scrape.run_job_high": {"queue": "crawl_high"},
    "pilgrim.scrape.run_job": {"queue": "crawl_default"},
    "pilgrim.scrape.backfill": {"queue": "crawl_low"},
    "pilgrim.maintenance.*": {"queue": "maintenance"},
}
```

Start workers with explicit queues:

```bash
celery -A app.workers.celery_app worker -Q crawl_high,crawl_default --concurrency=4
```

## 4. Beat: database-driven schedules

- Prefer storing **cron / interval** + **crawl_config_id** in PostgreSQL.
- Beat process runs a **lightweight tick task** that reads due schedules and enqueues `run_crawl_job` or `enqueue_config_targets`.

```python
# Illustrative beat entry — call from celery beat schedule
@celery_app.task(name="pilgrim.scheduler.tick", queue="maintenance")
def scheduler_tick() -> None:
    """Find due schedules and enqueue crawl tasks."""
    ...
```

Alternative: `django-celery-beat`-style DB scheduler is optional; if unused, document static `beat_schedule` only for dev.

## 5. Retries and idempotency

- Use **`autoretry_for`** only for **transient** exceptions.
- For HTTP 429, implement **custom retry** with `self.retry(countdown=retry_after)` when `Retry-After` is present.
- **`task_id`**: for critical tasks, pass `task_id` from API when enqueueing to support idempotent client retries (`apply_async(..., task_id=...)`).

## 6. Signals (monitoring, metrics)

```python
from celery import signals

@signals.task_failure.connect
def on_task_failure(sender=None, task_id=None, exception=None, **kwargs) -> None:
    # Log + metric; optional Sentry capture
    ...

@signals.task_postrun.connect
def on_task_postrun(sender=None, task_id=None, retval=None, **kwargs) -> None:
    ...
```

## 7. Results: Redis + PostgreSQL

- **Redis result backend**: short TTL for progress (`state`, `meta`).
- **PostgreSQL**: canonical job row (`status`, `started_at`, `finished_at`, `error_code`, `stats` JSON).

Avoid storing full scrape payloads in Redis.

## 8. Flower (operations)

- Run Flower in Docker Compose with **auth** (basic auth or reverse proxy).
- Do not expose Flower to the public internet.

```bash
celery -A app.workers.celery_app flower --basic_auth=user:pass
```

## 9. Dead-letter pattern

- After **max retries**, persist failure in DB with `error_code` and optional `last_traceback` (truncated).
- Optional: route to **`crawl_dlq`** queue via chained task or manual replay admin API.

## 10. Checklist

- [ ] Time limits set for all long-running tasks
- [ ] `acks_late` + idempotent side effects where possible
- [ ] Queue per SLA; workers subscribed explicitly
- [ ] Beat schedules documented and timezone = UTC
- [ ] No secrets in task arguments

This rule complements `architecture.mdc` and `docker-infrastructure.mdc` for a production-grade scheduler layer.
