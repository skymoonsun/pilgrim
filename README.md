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
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" alt="React" />
  <img src="https://img.shields.io/badge/PostgreSQL-16-336791?logo=postgresql&logoColor=white" alt="PostgreSQL" />
  <img src="https://img.shields.io/badge/Celery-5.4+-37814A?logo=celery&logoColor=white" alt="Celery" />
  <img src="https://img.shields.io/badge/Scrapling-0.4+-FF6F00" alt="Scrapling" />
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
</p>

---

Pilgrim is a **"Scraping as a Service"** microservice that automates web data collection. Scraping recipes (crawl configurations) are stored in the database; the target URL is provided only as a runtime parameter.

## ✨ Features

- **Config-driven scraping** — Define extraction rules (CSS/XPath selectors) once, reuse across multiple URLs
- **Data sanitizers** — Reusable post-processing rules to clean up extracted values (strip currency symbols, normalize whitespace, convert types)
- **AI-powered config generation** — Describe what to extract in natural language; AI generates the selectors for you
- **AI-powered sanitizer generation** — Let AI suggest sanitizer rules based on sample extracted data
- **Proxy management** — Fetch, parse, validate, and rotate proxies from configurable sources with health monitoring
- **Manual proxy support** — Add paid/custom proxies individually or in bulk; they persist until deleted
- **AI-powered proxy source analysis** — Paste a proxy list URL and let AI detect the format and suggest extraction settings
- **Proxy source verification** — Test parsing config against a real URL before saving
- **Scrapling-first** — Uses [Scrapling](https://github.com/D4Vinci/Scrapling) for fetching & parsing with multiple profiles (static, stealth, dynamic)
- **Schedule management** — Cron & interval-based scheduling with config-to-URL mapping
- **Webhook callbacks** — Post results to external services with field mapping and retry logic
- **Email notifications** — SMTP-based notifications on job success or failure with templated emails
- **React dashboard** — Modern dark-themed UI for managing configs, testing scrapes, and monitoring jobs
- **Async job execution** — Heavy scraping runs via Celery workers, not the API process
- **Sync scrape endpoint** — Quick one-off test scrapes directly from the API
- **Provider-agnostic LLM integration** — Ollama today, other providers via the abstraction layer
- **Versioned seed system** — Migration-like seed runner for managing initial data
- **PostgreSQL as source of truth** — Configs, jobs, results, and schedules all persisted
- **Full Docker Compose stack** — API, worker, beat, frontend, PostgreSQL, Redis in one command
- **Swagger UI** — Interactive API documentation at `/docs`

## 🏗 Architecture

```
┌──────────────┐     ┌───────────┐     ┌─────────────┐
│   Frontend   │────▶│  FastAPI  │────▶│  PostgreSQL │
│  (React/TS)  │     │  (API)    │     └─────────────┘
│  :3000       │     └─────┬─────┘
└──────────────┘           │ enqueue
                           ▼
                     ┌───────────┐     ┌─────────────┐
                     │   Redis   │────▶│   Celery    │
                     │  (Broker) │     │  (Worker)   │
                     └───────────┘     └──────┬──────┘
                                              │ Scrapling
                                              ▼
                                       ┌─────────────┐
                                       │  Target URL │
                                       └─────────────┘
```

## 🚀 Quick Start

### Prerequisites
- [Docker](https://docs.docker.com/get-docker/) & Docker Compose v2

### Setup

```bash
# Clone the repository
git clone https://github.com/skymoonsun/pilgrim.git
cd pilgrim

# Create the .env file
cp .env.example .env

# Build and start the full stack (API + Worker + Frontend + DB + Redis)
make dev-build

# Apply database migrations
make migrate

# Seed initial crawl configurations
make seed

# Open the dashboard
open http://localhost:3000

# Open Swagger UI (API docs)
open http://localhost:8000/docs
```

## 🖥 Frontend Dashboard

The React dashboard runs on `http://localhost:3000` and provides:

| Page | Route | Description |
|------|-------|-------------|
| **Dashboard** | `/` | System health, metrics, recent jobs |
| **Configurations** | `/configurations` | Manage crawl configs (CRUD) |
| **Scrape Playground** | `/scrape` | Test configs with real URLs (live) |
| **Jobs** | `/jobs` | Monitor async crawl jobs |
| **Sanitizers** | `/sanitizer-configs` | Manage sanitizer configs (CRUD) + AI generation |
| **Proxy Sources** | `/proxy-sources` | Manage proxy list sources (CRUD) |
| **Proxies** | `/proxies` | View and filter validated proxies |
| **Settings** | `/settings` | Application configuration |

- Dark theme with glassmorphism cards and subtle animations
- Clean outline SVG icons (Lucide-style)
- Real-time API health monitoring (API, Database, Redis)
- Vite dev server with hot reload
- API proxy to backend via Docker networking

## 📖 API Reference

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
| `POST` | `/api/v1/schedules/` | Create a schedule |
| `GET` | `/api/v1/schedules/` | List all schedules |
| `GET` | `/api/v1/schedules/{id}` | Get schedule by ID |
| `PATCH` | `/api/v1/schedules/{id}` | Update a schedule |
| `DELETE` | `/api/v1/schedules/{id}` | Delete a schedule |
| `POST` | `/api/v1/schedules/{id}/trigger` | Manually trigger a schedule |
| `PUT` | `/api/v1/schedules/{id}/callback` | Set or update a webhook callback |
| `DELETE` | `/api/v1/schedules/{id}/callback` | Remove a webhook callback |
| `PUT` | `/api/v1/schedules/{id}/email-notification` | Set or update email notification |
| `DELETE` | `/api/v1/schedules/{id}/email-notification` | Remove email notification |
| `POST` | `/api/v1/ai/generate-spec` | Generate extraction spec via AI |
| `POST` | `/api/v1/ai/verify-spec` | Verify extraction spec against a URL |
| `POST` | `/api/v1/ai/suggest-proxy-source` | AI-analyze a proxy source URL |
| `POST` | `/api/v1/ai/suggest-sanitizer` | AI-generate sanitizer rules from URL + extraction spec |
| `GET` | `/api/v1/ai/status` | Check AI feature availability |
| `POST` | `/api/v1/sanitizer-configs/` | Create a sanitizer config |
| `GET` | `/api/v1/sanitizer-configs/` | List sanitizer configs (`?active_only=true`) |
| `GET` | `/api/v1/sanitizer-configs/{id}` | Get sanitizer config by ID |
| `PATCH` | `/api/v1/sanitizer-configs/{id}` | Update a sanitizer config |
| `DELETE` | `/api/v1/sanitizer-configs/{id}` | Delete a sanitizer config |
| `POST` | `/api/v1/proxy-sources/` | Create a proxy source config |
| `GET` | `/api/v1/proxy-sources/` | List all proxy source configs |
| `GET` | `/api/v1/proxy-sources/{id}` | Get proxy source by ID |
| `PATCH` | `/api/v1/proxy-sources/{id}` | Update a proxy source config |
| `DELETE` | `/api/v1/proxy-sources/{id}` | Delete a proxy source config |
| `POST` | `/api/v1/proxy-sources/{id}/fetch` | Trigger proxy fetch for a source |
| `GET` | `/api/v1/proxies/` | List validated proxies (with filters) |
| `GET` | `/api/v1/proxies/{id}` | Get proxy by ID |
| `DELETE` | `/api/v1/proxies/{id}` | Delete a proxy |
| `POST` | `/api/v1/proxies/{source_id}/validate` | Trigger proxy validation for a source |

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
│   │   ├── cli/                # CLI tools (seed runner)
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
│   ├── seeds/                  # Versioned seed scripts (0001_*.py)
│   ├── Dockerfile              # Multi-stage: api (slim) + worker (browsers)
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/                # Typed API client
│   │   ├── components/         # Layout (Sidebar, Header) + Icons
│   │   ├── pages/              # Dashboard, Configurations, Scrape, Jobs, Schedules, ProxySources, Proxies, Sanitizers, Settings
│   │   ├── App.tsx             # React Router setup
│   │   └── index.css           # Design system (CSS variables, dark theme)
│   ├── Dockerfile              # Node 22 Alpine + Vite dev server
│   └── vite.config.ts          # API proxy to backend
├── docs/
│   ├── crawl-configs.md        # Crawl configuration guide
│   ├── sanitizer-configs.md    # Sanitizer configs & transform reference
│   ├── proxy-management.md     # Proxy management guide
│   └── assets/
├── docker-compose.dev.yml      # Full dev stack (6 services)
├── docker-compose.yml          # Production (external DB & Redis)
└── Makefile                    # Developer workflow commands
```

## 🛠 Makefile Commands

| Command | Description |
|---------|-------------|
| `make dev-build` | Build and start the full dev stack |
| `make dev` | Start dev stack (no rebuild) |
| `make dev-down` | Stop the stack |
| `make dev-reset` | Stop and destroy all volumes |
| `make dev-logs` | Follow all service logs |
| `make dev-logs-api` | Follow API logs only |
| `make dev-logs-frontend` | Follow frontend logs only |
| `make migrate` | Apply pending migrations |
| `make migrate-create MSG="..."` | Generate a new migration |
| `make migrate-history` | View migration history |
| `make seed` | Apply pending seed scripts |
| `make seed-status` | Show seed status (applied/pending) |
| `make setup` | Run migrations + seeds in sequence |
| `make db-shell` | Open PostgreSQL shell |
| `make redis-shell` | Open Redis CLI |
| `make shell` | Open Python shell in API container |
| `make test` | Run test suite |
| `make lint` | Run linter (ruff) |
| `make help` | List all available commands |

## 🌱 Seed System

Seeds work like migrations — versioned Python scripts in `backend/seeds/` that are tracked in a `seed_versions` table:

```bash
# Apply pending seeds
make seed

# Check seed status
make seed-status
```

Create new seeds as `backend/seeds/NNNN_description.py` with an `async def run(session)` function. See the [crawl configs guide](docs/crawl-configs.md) for examples.

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
| `PILGRIM_AI_ENABLED` | Enable AI-powered features | `false` |
| `PILGRIM_LLM_PROVIDER` | LLM provider (`ollama`) | `ollama` |
| `PILGRIM_OLLAMA_BASE_URL` | Ollama API base URL | `http://host.docker.internal:11434` |
| `PILGRIM_OLLAMA_MODEL` | Ollama model name | `llama3.2` |
| `PILGRIM_OLLAMA_TOKEN` | Ollama bearer token (optional) | — |
| `PILGRIM_AI_MAX_HTML_CHARS` | Max HTML chars sent to LLM | `30000` |

## 🤖 AI-Powered Config Generation

Pilgrim can generate extraction specs automatically using an LLM. Instead of writing CSS/XPath selectors by hand, describe what you want to extract in natural language and let the AI do the work.

### How it works

1. You provide a **target URL** and a **natural language description** (e.g., "Extract the product name, price, and availability")
2. Pilgrim fetches the page using Scrapling, sanitizes the HTML, and sends it to the configured LLM
3. The LLM generates an `extraction_spec` with CSS/XPath selectors
4. You review and optionally edit the result before saving

### Setup (Ollama)

1. [Install Ollama](https://ollama.com) and pull a model:
   ```bash
   ollama pull llama3.2
   # or for better structured output:
   ollama pull qwen2.5:7b
   ```
2. Enable AI in your `.env`:
   ```env
   PILGRIM_AI_ENABLED=true
   PILGRIM_OLLAMA_BASE_URL=http://host.docker.internal:11434
   PILGRIM_OLLAMA_MODEL=llama3.2
   ```
3. The dashboard will show an **"Generate with AI"** button in the config creation page

### API Usage

```bash
# Check AI availability
curl http://localhost:8000/api/v1/ai/status

# Generate an extraction spec
curl -X POST http://localhost:8000/api/v1/ai/generate-spec \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/product/123",
    "description": "Extract the product title, price, stock status, and image URLs"
  }'
```

### Provider architecture

The LLM integration uses a provider abstraction (`app/integrations/llm_base.py`). Ollama is the first implementation, but adding new providers (OpenAI, Anthropic, etc.) requires only:

1. A new subclass of `LLMProvider`
2. A new `elif` branch in `create_llm_provider()`
3. Corresponding config settings

No changes to the service or API layer are needed.

### Scraper profile selection

The AI endpoint accepts an optional `scraper_profile` parameter. Use `fetcher` (default) for static pages or `http_session` for sites requiring cookies. The `stealth` and `dynamic` profiles require browser binaries that are only available in the worker container.

### AI-powered sanitizer generation

The AI can also suggest sanitizer rules based on sample extracted data. After creating a crawl config and verifying its extraction spec, use the suggest-sanitizer endpoint:

```bash
curl -X POST http://localhost:8000/api/v1/ai/suggest-sanitizer \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://store.example.com/product/123",
    "extraction_spec": {
      "fields": {
        "price": {"selector": ".price::text", "type": "css"},
        "title": {"selector": "h1::text", "type": "css"}
      }
    },
    "description": "Price fields contain currency symbols, titles have extra whitespace"
  }'
```

The response includes suggested `rules`, `sample_before` (raw data), and `sample_after` (cleaned data). See the [Sanitizer Configs Guide](docs/sanitizer-configs.md) for transform types and examples.

## 🔌 Proxy Management

Pilgrim includes a built-in proxy management system for fetching, parsing, validating, and rotating proxies from configurable sources.

### Supported formats

| Format | Description |
|--------|-------------|
| `raw_text` | Plain text lists — `ip:port`, `protocol://ip:port`, `ip:port:user:pass` |
| `json` | JSON arrays/objects with extraction specs for field mapping |
| `csv` | CSV data with configurable delimiters and column mapping |
| `xml` | XML documents with XPath-based element selection |

### Creating a proxy source

```bash
# Simple raw text source
curl -X POST http://localhost:8000/api/v1/proxy-sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Free Proxy List",
    "url": "https://example.com/proxies.txt",
    "format_type": "raw_text",
    "validation_urls": {"urls": ["https://httpbin.org/ip"]},
    "fetch_interval_seconds": 3600,
    "proxy_ttl_seconds": 86400
  }'

# JSON source with extraction spec
curl -X POST http://localhost:8000/api/v1/proxy-sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "JSON Proxy API",
    "url": "https://api.example.com/proxies",
    "format_type": "json",
    "extraction_spec": {
      "list_path": "data",
      "fields": {"ip": "ip_address", "port": "port", "protocol": "type"}
    },
    "validation_urls": {"urls": ["https://httpbin.org/ip"]}
  }'
```

### Fetching & validating

```bash
# Trigger a fetch (downloads and parses the proxy list)
curl -X POST http://localhost:8000/api/v1/proxy-sources/{id}/fetch

# Validate fetched proxies against test URLs
curl -X POST http://localhost:8000/api/v1/proxies/{source_id}/validate

# List healthy proxies
curl http://localhost:8000/api/v1/proxies/?health=healthy&limit=50
```

### AI-powered proxy source analysis

When AI is enabled (`PILGRIM_AI_ENABLED=true`), the "New Proxy Source" page shows an **AI Analysis** panel. Paste a proxy list URL and click **Analyze** — Pilgrim will:

1. Fetch the content from the URL
2. Detect the format (raw_text, JSON, CSV, XML) — raw_text detection is heuristic (no LLM call needed)
3. For structured formats, call the LLM to suggest an extraction spec, name, and description
4. Auto-fill the form with the detected settings and show sample proxies

```bash
# API endpoint for AI proxy source analysis
curl -X POST http://localhost:8000/api/v1/ai/suggest-proxy-source \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/proxies.txt"}'
```

### Celery tasks

| Task | Queue | Description |
|------|-------|-------------|
| `pilgrim.proxy.fetch_proxy_source` | `maintenance` | Fetch and parse proxies from a source URL |
| `pilgrim.proxy.validate_proxies` | `maintenance` | Test proxy connectivity against validation URLs |
| `pilgrim.proxy.expire_proxies` | `maintenance` | Remove expired proxies (runs hourly via beat) |

## 📧 Email Notifications

Schedules can send email notifications when jobs complete. Configure SMTP settings and attach email notifications to any schedule:

```bash
# Set up email notification for a schedule
curl -X PUT http://localhost:8000/api/v1/schedules/{id}/email-notification \
  -H "Content-Type: application/json" \
  -d '{
    "recipient_emails": ["team@example.com"],
    "subject_template": "Crawl Complete: {schedule_name}",
    "on_success": true,
    "on_failure": true
  }'
```

Email notifications support field mapping (same syntax as webhook callbacks) to include extracted data in the email body.

## 🔗 Webhook Callbacks

Schedules can trigger HTTP callbacks (webhooks) when jobs complete. Configure the URL, method, headers, and field mapping:

```bash
curl -X PUT http://localhost:8000/api/v1/schedules/{id}/callback \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://your-service.example.com/webhook",
    "method": "POST",
    "field_mapping": {
      "product_name": "$.data.title",
      "price": "$.data.price",
      "source_url": "$.url"
    }
  }'
```

## 🐳 Docker

The project uses **multi-stage Dockerfiles**:

| Image | Purpose | Base |
|-------|---------|------|
| **`api`** | FastAPI server (slim, no browsers) | `python:3.12-slim` |
| **`worker`** | Celery + Scrapling + browser engines | `python:3.12-slim` + playwright |
| **`frontend`** | Vite dev server + React | `node:22-alpine` |

Two Compose files are provided:

- **`docker-compose.dev.yml`** — Full local development (6 services: postgres, redis, api, worker, beat, frontend)
- **`docker-compose.yml`** — Production with external database & Redis

## 📚 Documentation

- [Crawl Configurations Guide](docs/crawl-configs.md) — Extraction specs, scraper profiles, fetch options, and real-world examples
- [Sanitizer Configs Guide](docs/sanitizer-configs.md) — Transform types, AI-powered generation, and usage examples
- [Proxy Management Guide](docs/proxy-management.md) — Proxy sources, formats, validation, manual proxies, AI analysis, and rotation

## License

MIT
