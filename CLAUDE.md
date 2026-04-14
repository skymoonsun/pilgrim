# Pilgrim — guidance for Claude (Code / IDE)

This repository is **Pilgrim**, a config-driven scraping/crawling service.

## Where the rules live (Cursor + Claude Code + Antigravity)

| Tool | Location | Format |
|------|----------|--------|
| **Claude Code** | **`.claude/rules/*.md`** | Markdown; optional YAML frontmatter with `paths:` (globs) — see [Memory & rules](https://code.claude.com/docs/en/memory) |
| **Cursor** | **`.cursor/rules/*.mdc`** | Markdown + Cursor-specific frontmatter (`alwaysApply`, `applyIntelligently`, …) |
| **Antigravity** | **`.agents/rules/*.md`** | YAML `trigger`: `always_on`, `glob` (+ `globs`), `manual`, `model_decision`; **≤ 12,000 characters per file** — see root **`AGENTS.md`** |

**Maintenance:** When you change team standards, update **`.mdc`**, **`.claude/rules/*.md`**, and **`.agents/rules/pilgrim-*.md`** (or re-run `scripts/generate_antigravity_rules.py`) so tools stay aligned.

### Claude Code behavior (official)

- Rules are plain **`.md`** files under **`.claude/rules/`** (subdirectories allowed; discovered recursively).
- **No `paths` in frontmatter** → rule is loaded **every session** (like global context).
- **`paths:`** (array of glob strings) → rule loads when Claude works with **matching files**, saving context on unrelated edits.
- Keep each file **one topic**, **descriptive filename**; prefer path-scoping for large guides (see [docs](https://code.claude.com/docs/en/memory#organize-rules-with-claude/rules/)).

### Pilgrim `.claude/rules/` map

| Rule file | Scope (`paths`) | Cursor twin |
|-----------|-----------------|-------------|
| `architecture.md` | *(always loaded)* | `architecture.mdc` |
| `code-conventions.md` | `**/*.py` | `code-conventions.mdc` |
| `api-design.md` | `app/api/**/*.py` | `api-design.mdc` |
| `database-design.md` | models, schemas, db, alembic | `database-design.mdc` |
| `scraping-strategies.md` | `app/crawlers/**/*` (workers: see Antigravity `pilgrim-scraping-workers.md`) | `scraping-strategies.mdc` |
| `celery-scheduler.md` | `app/workers/**/*` | `celery-scheduler.mdc` |
| `config-environment.md` | `app/core`, `app/integrations` | `config-environment.mdc` |
| `docker-infrastructure.md` | Dockerfiles, compose, `docker/` | `docker-infrastructure.mdc` |
| `testing-guidelines.md` | `tests/**/*` | `testing-guidelines.mdc` |

## Stack (non-negotiable)

- **API:** FastAPI (async).
- **Scraping:** Scrapling in **`app/crawlers/`**; browser-heavy code **only in worker** images/processes unless explicitly documented.
- **Queue:** Celery + Redis; canonical job state in **PostgreSQL**, not Redis.
- **DB:** PostgreSQL + SQLAlchemy 2.0 async (`postgresql+asyncpg://` for app/workers).
- **Local dev:** Prefer **`docker compose`** per `docker-infrastructure` rules.

## Product / vision (human-oriented)

See **`.docs/project-overview.md`** (Turkish) for narrative; implementation follows the English rule files above.

## What not to do

- Do not replace Scrapling-first HTML fetching with raw **httpx** or ad-hoc BeautifulSoup as the default path.
- Do not run dynamic/Playwright stacks in the slim API container without an explicit, reviewed exception.
- Do not invent env var names: use **`PILGRIM_`*** prefix and patterns from `config-environment`.

When in doubt, open the matching rule file for your editor (`.md` or `.mdc`) and align with the examples there.
