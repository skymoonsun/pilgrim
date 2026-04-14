---
trigger: glob
globs: "tests/**/*"
description: "Pilgrim service: testing-guidelines — segment 4/4. Mirrors .cursor/rules/testing-guidelines.mdc."
---

# Pilgrim — testing guidelines (part 4/4)

> Antigravity workspace rule. Canonical copy: `.cursor/rules/testing-guidelines.mdc`.

## 7. Celery, Redis, Scrapling, and Docker Compose

### Celery tasks (unit-level)
- Prefer **`task_always_eager=True`** in a `pytest` settings profile so `apply_async` runs the body in-process (good for service logic that enqueues then returns 202).
- For **isolated** task tests, patch **`apply_async`** or the task’s **`run`** method and assert call args (`queue`, `args`, `kwargs`).
- Use **`CELERY_TASK_EAGER_PROPAGATES = True`** so exceptions fail the test.
- Do not share a real Redis broker between parallel `pytest-xdist` workers unless each worker uses a **distinct DB index** or **key prefix**.

```python
# tests/unit/test_workers/test_crawl_tasks.py
from unittest.mock import MagicMock
import pytest

from app.workers.tasks.scrape import run_crawl_job


@pytest.fixture
def celery_eager_app():
    from app.workers.celery_app import celery_app

    celery_app.conf.update(task_always_eager=True, task_eager_propagates=True)
    yield celery_app


def test_run_crawl_job_invokes_pipeline(celery_eager_app, monkeypatch):
    monkeypatch.setattr(
        "app.workers.tasks.scrape.execute_crawl_pipeline",
        MagicMock(return_value={"ok": True}),
    )
    run_crawl_job.apply(args=["00000000-0000-0000-0000-000000000001"])
```

### Redis
- **Unit tests:** `fakeredis` async API to test cache/proxy pool helpers without a server.
- **Integration:** real Redis from **Docker Compose** or **testcontainers**.

```python
# tests/conftest.py (optional)
import pytest_asyncio
from fakeredis import aioredis as fake_aioredis


@pytest_asyncio.fixture
async def fake_redis():
    redis = fake_aioredis.FakeRedis()
    yield redis
    await redis.flushall()
```

### Scrapling / fetchers
- Mock at the **boundary**: patch what the worker calls (e.g. fetcher `get` / session `fetch`) and return fixture HTML/JSON from `tests/fixtures/html_responses/`.
- Assert **parsed output**, not full HTML equality.
- **Playwright:** `pytest-playwright` or `@pytest.mark.integration` in CI with browsers installed.

### Docker Compose integration tests
- Mark **`@pytest.mark.integration`**; default run: `pytest -m "not integration"`.
- CI: `docker compose -f docker-compose.yml -f docker-compose.test.yml up -d`, then `pytest -m integration` with URLs pointing at compose services.
- **Health:** wait for Postgres + Redis (optional Celery **inspect ping**) before tests.

Use **section 7** together with **sections 3–5** so API tests stay fast while workers and Scrapling stay verifiable in CI.