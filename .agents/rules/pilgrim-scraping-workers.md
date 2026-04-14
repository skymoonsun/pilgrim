---
trigger: glob
globs: "app/workers/**/*"
description: "Pilgrim: Scrapling-first scraping in Celery workers — same constraints as scraping-strategies. Mirrors .cursor/rules/scraping-strategies.mdc for worker context."
---

# Pilgrim — scraping in workers

> Full spec: `.cursor/rules/scraping-strategies.mdc` and `pilgrim-scraping-strategies.md` (crawler package). This file reminds worker/task code paths.

## Non-negotiables

- **Scrapling-first** for fetch/parse in **`app/crawlers/`** (and call from tasks from there). Do not use **httpx** or ad-hoc **BeautifulSoup** as the default HTML pipeline.
- **Browser / Playwright / dynamic fetchers** run in **worker** processes and images only — not in the slim API service unless explicitly documented and reviewed.
- Use **JSON-safe** Celery task arguments; reload ORM rows inside the task.
- Task names: **`pilgrim.<domain>.<verb>`** with explicit **queue** (see `pilgrim-celery-scheduler.md`).
- Respect **proxy / rate-limit** configuration from crawl config and Redis where applicable.

## When touching tasks

- Import crawler logic from **`app/crawlers/`**; keep `app/workers/tasks/` thin (orchestration, retries, DB updates).
- Persist canonical job status and results in **PostgreSQL**, not Redis.
