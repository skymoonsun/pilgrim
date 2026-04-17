"""Application configuration via Pydantic Settings.

All env vars are documented in `.env.example`.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, PostgresDsn, RedisDsn, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed, validated application settings.

    Values are loaded from environment variables and an optional ``.env`` file.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── Application ──────────────────────────────────────────────
    app_name: str = "Pilgrim"
    app_version: str = "0.1.0"
    environment: Literal["local", "dev", "staging", "prod"] = Field(
        default="local",
        validation_alias="PILGRIM_ENVIRONMENT",
    )
    debug: bool = Field(default=False, validation_alias="PILGRIM_DEBUG")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # ── Database ─────────────────────────────────────────────────
    database_url: PostgresDsn = Field(..., validation_alias="DATABASE_URL")
    database_pool_size: int = Field(
        default=10, ge=1, validation_alias="DB_POOL_SIZE"
    )
    database_max_overflow: int = Field(
        default=20, ge=0, validation_alias="DB_MAX_OVERFLOW"
    )

    # ── Redis ────────────────────────────────────────────────────
    redis_url: RedisDsn = Field(..., validation_alias="REDIS_URL")

    # ── Celery ───────────────────────────────────────────────────
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

    # ── Scrapling ────────────────────────────────────────────────
    scrapling_browser_install: bool = Field(
        default=False,
        validation_alias="PILGRIM_SCRAPLING_BROWSER_INSTALL",
    )

    # ── SMTP ──────────────────────────────────────────────────────
    smtp_host: str = Field(
        default="localhost",
        validation_alias="PILGRIM_SMTP_HOST",
    )
    smtp_port: int = Field(
        default=587,
        validation_alias="PILGRIM_SMTP_PORT",
    )
    smtp_username: str | None = Field(
        default=None,
        validation_alias="PILGRIM_SMTP_USERNAME",
    )
    smtp_password: str | None = Field(
        default=None,
        validation_alias="PILGRIM_SMTP_PASSWORD",
    )
    smtp_use_tls: bool = Field(
        default=True,
        validation_alias="PILGRIM_SMTP_USE_TLS",
    )
    smtp_from_address: str = Field(
        default="pilgrim@localhost",
        validation_alias="PILGRIM_SMTP_FROM_ADDRESS",
    )

    # ── AI / LLM ────────────────────────────────────────────────
    ai_enabled: bool = Field(
        default=False,
        validation_alias="PILGRIM_AI_ENABLED",
    )
    llm_provider: Literal["ollama"] = Field(
        default="ollama",
        validation_alias="PILGRIM_LLM_PROVIDER",
    )
    ollama_base_url: str = Field(
        default="http://host.docker.internal:11434",
        validation_alias="PILGRIM_OLLAMA_BASE_URL",
    )
    ollama_model: str = Field(
        default="llama3.2",
        validation_alias="PILGRIM_OLLAMA_MODEL",
    )
    ollama_token: str | None = Field(
        default=None,
        validation_alias="PILGRIM_OLLAMA_TOKEN",
    )
    ai_max_html_chars: int = Field(
        default=30000,
        ge=1000,
        le=500000,
        validation_alias="PILGRIM_AI_MAX_HTML_CHARS",
    )

    # ── Observability ────────────────────────────────────────────
    sentry_dsn: str | None = Field(default=None, validation_alias="SENTRY_DSN")

    # ── Validators ───────────────────────────────────────────────
    @field_validator("database_url", mode="after")
    @classmethod
    def require_async_driver(cls, v: PostgresDsn) -> PostgresDsn:
        if not str(v).startswith("postgresql+asyncpg://"):
            raise ValueError(
                "DATABASE_URL must use the postgresql+asyncpg:// driver"
            )
        return v

    @field_validator("celery_broker_url", mode="before")
    @classmethod
    def default_celery_broker(cls, v: str, info) -> str:
        if v:
            return v
        return str(info.data.get("redis_url", ""))

    @field_validator("celery_result_backend", mode="before")
    @classmethod
    def default_celery_backend(cls, v: str, info) -> str:
        if v:
            return v
        return str(info.data.get("redis_url", ""))


@lru_cache
def get_settings() -> Settings:
    """Return a cached ``Settings`` instance."""
    return Settings()
