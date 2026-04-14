# syntax=docker/dockerfile:1
# ─────────────────────────────────────────────────────────────────
# Pilgrim — Multi-stage Dockerfile
# Targets: api (slim), worker (Scrapling + browsers)
# ─────────────────────────────────────────────────────────────────

# ── Base ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

# ── Builder ──────────────────────────────────────────────────────
FROM base AS builder
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

# Copy project metadata and app code
COPY pyproject.toml ./
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# Install project and its dependencies
RUN pip install --no-cache-dir .

# ── API target (slim — no browsers) ─────────────────────────────
FROM base AS api
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# ── Worker target (Scrapling + browser dependencies) ─────────────
FROM base AS worker
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-liberation \
        libnss3 \
        libnspr4 \
        libatk1.0-0 \
        libatk-bridge2.0-0 \
        libcups2 \
        libdrm2 \
        libxkbcommon0 \
        libxcomposite1 \
        libxdamage1 \
        libxrandr2 \
        libgbm1 \
        libpango-1.0-0 \
        libcairo2 \
        libasound2 \
        libx11-xcb1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app

# Download browser binaries (pip deps already in builder layer)
RUN scrapling install || true

CMD ["celery", "-A", "app.workers.celery_app", "worker", \
     "-Q", "crawl_high,crawl_default,crawl_low", \
     "--concurrency=2", "-l", "info"]
