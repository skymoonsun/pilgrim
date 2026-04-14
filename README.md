<p align="center">
  <img src="docs/assets/cover.png" alt="Pilgrim" width="100%" />
</p>

<h1 align="center">Pilgrim</h1>

<p align="center">
  <strong>Config-driven scraping & crawling microservice</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue?logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-0.115+-009688?logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Celery-5.4+-37814A?logo=celery&logoColor=white" alt="Celery" />
  <img src="https://img.shields.io/badge/Scrapling-first-orange?logo=data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjQiIGhlaWdodD0iMjQiLz4=" alt="Scrapling" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
</p>

---

Pilgrim is a **"Scraping as a Service"** microservice that automates web data collection. Scraping recipes (crawl configurations) are stored in the database; the target URL is provided only as a runtime parameter.

## ✨ Features

- **Config-driven scraping** — Define extraction rules (CSS/XPath selectors) once, reuse across multiple URLs
- **Scrapling-first** — Uses [Scrapling](https://github.com/D4Vinci/Scrapling) for fetching & parsing with multiple profiles (static, stealth, dynamic)
- **Async job execution** — Heavy scraping runs via Celery workers, not the API process
- **Sync scrape endpoint** — Quick one-off test scrapes directly from the API
- **PostgreSQL as source of truth** — Configs, jobs, results, and schedules all persisted
- **Full Docker Compose stack** — API, worker, beat, PostgreSQL, Redis in one command
- **Swagger UI** — Interactive API documentation at `/docs`

## 🏗 Architecture

```
┌─────────┐     ┌───────────┐     ┌─────────────┐
│  Client  │────▶│  FastAPI   │────▶│  PostgreSQL  │
└─────────┘     │  (API)     │     └─────────────┘
                └─────┬─────┘
                      │ enqueue
                      ▼
                ┌───────────┐     ┌─────────────┐
                │   Redis    │────▶│   Celery     │
                │  (Broker)  │     │  (Worker)    │
                └───────────┘     └──────┬──────┘
                                         │ Scrapling
                                         ▼
                                  ┌─────────────┐
                                  │  Target URL  │
                                  └─────────────┘
```

## 🚀 Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose v2

### Setup

```bash
# Clone the repository
git clone https://github.com/your-org/pilgrim.git
cd pilgrim

# Create the .env file
cp .env.example .env

# Build and start the full stack
make dev-build

# Apply database migrations
make migrate

# Open Swagger UI
open http://localhost:8000/docs
```

## 📖 API Overview

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/v1/health/` | Liveness check |
| `GET` | `/api/v1/health/readiness` | Readiness check (DB + Redis) |
| `POST` | `/api/v1/crawl-configs/` | Create a crawl configuration |
| `GET` | `/api/v1/crawl-configs/` | List all configurations |
| `GET` | `/api/v1/crawl-configs/{id}` | Get configuration by ID |
| `PATCH` | `/api/v1/crawl-configs/{id}` | Update a configuration |
| `DELETE` | `/api/v1/crawl-configs/{id}` | Delete a configuration |
| `POST` | `/api/v1/scrape/` | Synchronous scrape (config_id + url) |
| `POST` | `/api/v1/crawl/jobs` | Enqueue async crawl job |
| `GET` | `/api/v1/crawl/jobs/{id}` | Poll job status |

### Example: Create a Config & Scrape

```bash
# 1. Create a crawl configuration
curl -X POST http://localhost:8000/api/v1/crawl-configs/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "example-titles",
    "scraper_profile": "fetcher",
    "extraction_spec": {
      "fields": {
        "title": {"selector": "h1::text", "type": "css"},
        "links": {"selector": "a::attr(href)", "type": "css", "multiple": true}
      }
    }
  }'

# 2. Use the config to scrape a URL
curl -X POST http://localhost:8000/api/v1/scrape/ \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "<config-uuid-from-step-1>",
    "url": "https://example.com"
  }'
```

## 📂 Project Structure

```
pilgrim/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # FastAPI route handlers
│   │   ├── core/               # Config, logging, exceptions
│   │   ├── crawlers/           # Scrapling factory & extraction
│   │   ├── db/                 # Async SQLAlchemy engine & session
│   │   ├── integrations/       # Redis client wrapper
│   │   ├── models/             # SQLAlchemy ORM models
│   │   ├── schemas/            # Pydantic request/response schemas
│   │   ├── services/           # Business logic layer
│   │   ├── workers/            # Celery app & task definitions
│   │   └── main.py             # FastAPI application entry point
│   ├── migrations/             # Alembic migration files
│   ├── Dockerfile              # Multi-stage: api (slim) + worker (browsers)
│   └── pyproject.toml
├── frontend/                   # (Coming soon)
├── docker-compose.dev.yml      # Local dev (includes Postgres & Redis)
├── docker-compose.yml          # Production (external DB & Redis)
└── Makefile                    # Developer workflow commands
```

## 🛠 Makefile Commands

| Command | Description |
|---------|-------------|
| `make dev-build` | Build and start the dev stack |
| `make dev` | Start dev stack (no rebuild) |
| `make dev-down` | Stop the stack |
| `make dev-reset` | Stop and destroy all volumes |
| `make dev-logs` | Follow all service logs |
| `make dev-logs-api` | Follow API logs only |
| `make migrate` | Apply pending migrations |
| `make migrate-create MSG="..."` | Generate a new migration |
| `make migrate-history` | View migration history |
| `make db-shell` | Open PostgreSQL shell |
| `make redis-shell` | Open Redis CLI |
| `make shell` | Open Python shell in API container |
| `make test` | Run test suite |
| `make lint` | Run linter (ruff) |
| `make help` | List all available commands |

## ⚙️ Configuration

All configuration is managed via environment variables. See [`.env.example`](.env.example) for the full list.

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string (asyncpg) | — |
| `REDIS_URL` | Redis connection string | — |
| `PILGRIM_ENVIRONMENT` | `local` / `dev` / `staging` / `prod` | `local` |
| `PILGRIM_DEBUG` | Enable debug mode | `false` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `CELERY_SOFT_TIME_LIMIT` | Task soft timeout (seconds) | `300` |
| `CELERY_TIME_LIMIT` | Task hard timeout (seconds) | `360` |

## 🐳 Docker

The project uses a **multi-stage Dockerfile** with two targets:

- **`api`** — Slim image for FastAPI (no browser dependencies)
- **`worker`** — Full image with Scrapling fetchers & Playwright browsers

Two Compose files are provided:

- **`docker-compose.dev.yml`** — Local development with built-in PostgreSQL & Redis
- **`docker-compose.yml`** — Production with external database & Redis

## License

MIT
