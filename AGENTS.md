# Pilgrim — cross-tool agent rules

This file gives **shared context** for Antigravity, Cursor, Claude Code, and other tools that read `AGENTS.md`.

## Where full standards live

| Tool | Location | Notes |
|------|----------|--------|
| **Cursor** | `.cursor/rules/*.mdc` | Cursor frontmatter (`alwaysApply`, `applyIntelligently`, …) |
| **Claude Code** | `.claude/rules/*.md` | Optional YAML `paths:` globs — see [Claude memory docs](https://code.claude.com/docs/en/memory) |
| **Antigravity** | `.agents/rules/*.md` | YAML `trigger` (`always_on`, `glob`, `manual`, `model_decision`); **≤ 12,000 characters per file** |

Keep these in sync when team standards change (same stems: e.g. `api-design`).

> Some Antigravity docs refer to `.agent/rules/` (singular). This repo uses **`.agents/rules/`** as the workspace rules directory.

## Stack (short)

FastAPI (async), **Scrapling-first** crawlers in `app/crawlers/`, Celery + Redis, PostgreSQL (SQLAlchemy 2 async), Docker Compose. Canonical job state in Postgres, not Redis.

## Human-oriented vision

See `.docs/project-overview.md` (Turkish).
