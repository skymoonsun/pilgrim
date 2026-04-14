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
  <img src="https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white" alt="Docker" />
</p>

---

Pilgrim is a **"Scraping as a Service"** microservice that automates web data collection. Scraping recipes (crawl configs) are stored in the database; the target URL is provided only as a runtime parameter.

## Quick Start

```bash
# Create the .env file
cp .env.example .env

# Build and start the stack
make dev-build

# Apply database migrations
make migrate

# Open Swagger UI
open http://localhost:8000/docs
```

## Useful Commands

| Command | Description |
|---------|-------------|
| `make dev-build` | Build and start the dev stack |
| `make dev-down` | Stop the stack |
| `make dev-logs` | Follow service logs |
| `make migrate` | Apply migrations |
| `make migrate-create MSG="..."` | Create a new migration |
| `make db-shell` | Open PostgreSQL shell |
| `make test` | Run tests |
| `make help` | List all available commands |

## License

MIT
