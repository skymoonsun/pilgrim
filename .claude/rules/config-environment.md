---
paths:
  - "app/core/**/*.py"
  - "app/integrations/**/*.py"
---

> Claude Code: modular rules in `.claude/rules/` — [Memory & rules](https://code.claude.com/docs/en/memory). Cursor equivalent: `.cursor/rules/config-environment.mdc`.

# Configuration and Environment - Pilgrim Service

Use **Pydantic Settings v2** (`pydantic-settings`) for all configuration. **English** env documentation in `.env.example`.

## 1. Naming convention

- Prefix: **`PILGRIM_`** for application-owned variables (optional `env_nested_delimiter="__"` for nested models).
- Standard third-party vars may stay unprefixed if required (`REDIS_URL`, `DATABASE_URL`) but prefer one style per deployment file and document it.

## 2. Settings module pattern

```python
# app/core/config.py
from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    environment: Literal["local", "dev", "staging", "prod"] = Field(
        default="local",
        validation_alias="PILGRIM_ENVIRONMENT",
    )
    debug: bool = Field(default=False, validation_alias="PILGRIM_DEBUG")

    database_url: PostgresDsn = Field(..., validation_alias="DATABASE_URL")
    database_pool_size: int = Field(default=10, ge=1, validation_alias="DB_POOL_SIZE")
    database_max_overflow: int = Field(default=20, ge=0, validation_alias="DB_MAX_OVERFLOW")

    redis_url: RedisDsn = Field(..., validation_alias="REDIS_URL")

    celery_broker_url: str = Field(
        default="",
        validation_alias="CELERY_BROKER_URL",
    )
    celery_result_backend: str = Field(
        default="",
        validation_alias="CELERY_RESULT_BACKEND",
    )
    celery_task_soft_time_limit_seconds: int = Field(
        default=300,
        ge=1,
        validation_alias="CELERY_SOFT_TIME_LIMIT",
    )
    celery_task_time_limit_seconds: int = Field(
        default=360,
        ge=1,
        validation_alias="CELERY_TIME_LIMIT",
    )

    scrapling_browser_install: bool = Field(
        default=False,
        validation_alias="PILGRIM_SCRAPLING_BROWSER_INSTALL",
    )

    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def default_celery_broker(cls, v: str, info) -> str:
        if v:
            return v
        data = info.data
        return str(data.get("redis_url", ""))

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def default_celery_backend(cls, v: str, info) -> str:
        if v:
            return v
        data = info.data
        return str(data.get("redis_url", ""))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
```

## 3. Database URL

- Async SQLAlchemy: **`postgresql+asyncpg://...`**
- Validate in a `@field_validator` if you need to reject sync drivers in API/worker.

## 4. Redis

- **Broker** and **result backend** may share one Redis with **key prefixes** or use separate logical DB indexes (`/0`, `/1`).
- Document **maxmemory** and **eviction** policy for production (avoid evicting broker keys unexpectedly).

## 5. Celery

- `CELERY_SOFT_TIME_LIMIT` < `CELERY_TIME_LIMIT` always.
- For JSON tasks, forbid `pickle` serializer in production.

## 6. Scrapling / Playwright

- **`PILGRIM_SCRAPLING_BROWSER_INSTALL`**: CI vs worker image (images should pre-run `scrapling install`).
- Worker-only env: `PLAYWRIGHT_BROWSERS_PATH`, `SCRAPLING_*` if the library adds env knobs — document in README.

## 7. Logging

- **structlog** + stdlib logging; JSON in prod, console in local.
- Log level via `LOG_LEVEL` (INFO default).

## 8. Secrets

- Never commit `.env`; provide `.env.example` with dummy values.
- Docker Compose: `env_file` + **secrets** for `DATABASE_URL` / API keys in prod.
- Rotate **JWT** / API keys independently of DB passwords.

## 9. Testing

- `ENVIRONMENT=test` triggers test defaults (e.g. in-memory SQLite only if explicitly allowed; prefer Docker Postgres for integration).
- Override `get_settings` in tests via `dependency_overrides` or `monkeypatch.setenv`.

## 10. Checklist

- [ ] All sensitive values loaded from env or secret store
- [ ] One settings object; no scattered `os.environ.get`
- [ ] Worker and API share compatible settings modules
- [ ] Timeouts and pool sizes tuned per environment

This aligns FastAPI, Celery, Redis, PostgreSQL, and Scrapling under one typed configuration surface.
