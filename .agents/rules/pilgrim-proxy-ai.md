---
trigger: glob
globs: "app/models/proxy*,app/services/proxy*,app/services/ai_service.py,app/services/ai_prompts.py,app/schemas/proxy*,app/api/v1/endpoints/proxies.py,app/api/v1/endpoints/proxy_sources.py,app/api/v1/endpoints/ai.py,app/workers/tasks/proxy.py,app/integrations/llm*,frontend/src/pages/ProxySources/**,frontend/src/pages/Proxies/**"
description: "Pilgrim: proxy management & AI integration — sources, validation, manual proxies, parser, fetch/expire tasks, LLM provider, AI spec generation. Mirrors .cursor/rules/proxy-ai.mdc."
---

# Pilgrim — proxy management & AI integration

> Antigravity workspace rule. Canonical copy: `.cursor/rules/proxy-ai.mdc`.

## 1. Two-table design

`ProxySourceConfig` — where/how to fetch proxies (URL, format_type, extraction_spec, validation_urls, TTLs).
`ValidProxy` — individual proxies with health metrics. `source_config_id = NULL` for manual proxies. Unique key: `(ip, port, protocol)`.

## 2. Manual proxies

Manual proxies (`source_config_id=NULL`, `expires_at=NULL`) never expire. On duplicate (same ip+port+protocol), existing proxy is **converted to manual** — source link removed, expiry cleared.

Endpoints: `POST /proxies/` (single), `POST /proxies/bulk` (raw text), `GET /proxies/?manual_only=true`.

## 3. Proxy parser (`app/services/proxy_parser.py`)

| Format | Key details |
|--------|-------------|
| `raw_text` | Regex; `ip:port`, `proto://user:pass@ip:port`, `ip:port:user:pass`; skips `#` |
| `json` | Auto-detect keys or use `extraction_spec.list_path` + `fields` |
| `csv` | DictReader; common column names |
| `xml` | `<proxy>`/`<item>`/`<row>` elements; case-insensitive |

## 4. Celery tasks (queue: `maintenance`)

- **fetch_proxy_source**: httpx GET → parse → upsert each proxy, set `expires_at`, auto-retry on timeout (max 3)
- **validate_proxies**: test each proxy against `validation_urls`; health = healthy/degraded/unhealthy based on `require_all_urls`
- **expire_proxies**: hourly via Beat; delete where `expires_at < now` (manual proxies never expired)

Each task creates its own `AsyncEngine` (workers outside API DI).

## 5. AI integration

Provider: `LLMProvider` base → `OllamaProvider`. Factory in `app/integrations/llm_provider.py`.

| Endpoint | LLM? | Purpose |
|----------|------|---------|
| `POST /ai/generate-spec` | Yes | Generate extraction spec from URL + description |
| `POST /ai/verify-spec` | Yes (refining) | Verify spec, optional self-healing loop |
| `POST /ai/suggest-proxy-source` | Yes (JSON/CSV/XML); heuristic (raw_text) | Detect format & suggest extraction spec |
| `POST /ai/verify-proxy-source` | No | Pure fetch + parse verification |
| `GET /ai/status` | No | AI availability check |

**Raw text shortcut:** ≥50% of first 20 lines match proxy patterns → no LLM call.
**JSON/XML:** Never truncate content before parsing (breaks `json.loads`).

## 6. Frontend patterns

- Proxy pages: `ProxySources/` (list/create/detail/edit), `Proxies/` (list + add modal)
- "Add Proxy" modal uses `createPortal(modal, document.body)` — `.animate-in` CSS `transform` breaks `position: fixed`
- AI Analysis panel: "Analyze" + "Verify Parsing" buttons on create/edit pages
- Manual proxies: cyan "Manual" badge; source filter dropdown includes "Manual" option