---
paths:
  - "app/models/proxy*"
  - "app/services/proxy*"
  - "app/services/ai_service.py"
  - "app/services/ai_prompts.py"
  - "app/schemas/proxy*"
  - "app/api/v1/endpoints/proxies.py"
  - "app/api/v1/endpoints/proxy_sources.py"
  - "app/api/v1/endpoints/ai.py"
  - "app/workers/tasks/proxy.py"
  - "app/integrations/llm*"
  - "frontend/src/pages/ProxySources/**/*"
  - "frontend/src/pages/Proxies/**/*"
---

> Claude Code: modular rules in `.claude/rules/` — [Memory & rules](https://code.claude.com/docs/en/memory). Cursor equivalent: `.cursor/rules/proxy-ai.mdc`.

# Proxy Management & AI Integration - Pilgrim Service

Pilgrim's proxy system fetches, parses, validates, and rotates proxies from configurable sources. The AI integration generates extraction specs and analyzes proxy source formats via an LLM provider (Ollama).

## 1. Two-table design

```
ProxySourceConfig                    ValidProxy
├── id (UUID)                        ├── id (UUID)
├── name (unique, str)               ├── source_config_id (FK → NULL = manual)
├── url (str, up to 2000)            ├── ip + port + protocol (unique key)
├── format_type (raw_text|json|      ├── username, password (nullable)
│                csv|xml)            ├── health (healthy|degraded|unhealthy)
├── extraction_spec (JSONB, null)     ├── avg_response_ms, success/failure_count
├── source_headers (JSONB, null)     ├── last_checked_at, last_success_at
├── validation_urls (JSONB)          └── expires_at (NULL for manual proxies)
├── require_all_urls (bool)
├── validation_timeout, fetch_interval_seconds,
│   proxy_ttl_seconds
└── last_fetched_at, last_fetch_error
```

**Key constraint:** `uq_proxy_ip_port_protocol` on `(ip, port, protocol)`.

## 2. Manual proxies

Manual proxies have `source_config_id = NULL` and `expires_at = NULL`. They never expire and are not affected by source fetches or the expiry task.

**Duplicate handling:** If a manually-added proxy already exists (by ip+port+protocol), it is **converted to manual** — source link removed, expiry cleared, credentials updated.

Endpoints:
- `POST /proxies/` — single manual proxy
- `POST /proxies/bulk` — bulk from raw text lines (MUST be before `/{proxy_id}` routes)
- `GET /proxies/?manual_only=true` — filter source-less proxies

## 3. Proxy parser

`app/services/proxy_parser.py` — dispatches by `ProxyFormatType`:

| Format | Parser | Notes |
|--------|--------|-------|
| `raw_text` | `parse_raw_text()` | Regex-based; supports `ip:port`, `proto://user:pass@ip:port`, `ip:port:user:pass`; skips `#` comments |
| `json` | `parse_json()` | Auto-detects keys (`ip`/`ip_address`/`host`, `port`) or uses `extraction_spec.list_path` + `fields` mapping |
| `csv` | `parse_csv()` | `DictReader`; tries common column names |
| `xml` | `parse_xml()` | Iterates `<proxy>`/`<item>`/`<row>` elements; case-insensitive tag lookup |

Entry point: `parse_proxy_list(content, format_type, extraction_spec=None)`

## 4. Fetch & validate flow

### Fetch (`pilgrim.proxy.fetch_proxy_source`, queue: `maintenance`)
1. Load `ProxySourceConfig` by ID
2. `httpx.AsyncClient.get(url, timeout=30, follow_redirects=True)`
3. `parse_proxy_list(content, format_type, extraction_spec)`
4. For each parsed proxy: `upsert_proxy()` by `(ip, port, protocol)`
5. Set `expires_at = now + proxy_ttl_seconds`
6. Update `last_fetched_at` (or `last_fetch_error` on failure)
7. Auto-retry on `httpx.TimeoutException` / `httpx.ConnectError` (max 3, backoff)

### Validate (`pilgrim.proxy.validate_proxies`, queue: `maintenance`)
1. Load config → `validation_urls`, `require_all_urls`, `validation_timeout`
2. For each proxy: test each validation URL via `httpx` through the proxy
3. Health determination:
   - `require_all_urls=true` → HEALTHY only if all succeed; DEGRADED if some; UNHEALTHY if none
   - `require_all_urls=false` → HEALTHY if any succeed; UNHEALTHY if none
4. Update `avg_response_ms`, counts, timestamps

### Expire (`pilgrim.proxy.expire_proxies`, queue: `maintenance`, hourly via Beat)
- `DELETE FROM valid_proxies WHERE expires_at IS NOT NULL AND expires_at < now`
- Manual proxies (`expires_at = NULL`) are never expired

## 5. Proxy rotation

When `use_proxy=true` on a `CrawlConfiguration`, `get_random_healthy(protocol=None)` selects a random healthy proxy via `ORDER BY RANDOM() LIMIT 1`.

## 6. AI integration

### Provider architecture

```
LLMProvider (base class)        app/integrations/llm_base.py
├── OllamaProvider               app/integrations/ollama.py
└── (future: OpenAI, Anthropic)
```

`create_llm_provider()` in `app/integrations/llm_provider.py` — factory based on `PILGRIM_LLM_PROVIDER`.

### AI endpoints

| Endpoint | Purpose | LLM call? |
|----------|---------|-----------|
| `POST /ai/generate-spec` | Generate extraction spec from URL + description | Yes |
| `POST /ai/verify-spec` | Verify spec against URL, optional self-healing loop | Yes (if refining) |
| `POST /ai/suggest-proxy-source` | Detect format & suggest extraction spec | Yes (for JSON/CSV/XML); heuristic for raw_text |
| `POST /ai/verify-proxy-source` | Verify parsing config against URL | No — pure fetch + parse |
| `GET /ai/status` | Check AI availability & LLM reachability | No |

### Proxy source suggestion flow

1. Fetch content from URL via `httpx` (30s timeout)
2. **Raw text shortcut:** `_looks_like_raw_text()` heuristic — if ≥50% of first 20 lines match raw text patterns, return immediately without LLM call (`model_used="heuristic"`)
3. **LLM path:** Send first 3000 chars to LLM with `PROXY_SOURCE_SUGGESTION_PROMPT`, get back `ProxySourceSuggestionSchema`
4. Parse sample proxies using detected format (use full content for JSON/XML — truncation breaks `json.loads`)

### Spec verification flow

1. Fetch page with Scrapling (respects `scraper_profile`)
2. Run extraction engine against the HTML
3. If fields fail and `max_iterations > 1`, send failures + HTML to LLM for refinement
4. Return `SpecVerificationResponse` with per-field results and optional `refined_spec`

## 7. Key patterns

### Celery workers manage their own DB sessions
Each proxy task creates/disposes its own `AsyncEngine` — workers run outside API's dependency injection.

### Health metrics are additive
`success_count` and `failure_count` accumulate across fetch and validation cycles. A proxy with `success:50, failure:2` is more reliable than `success:1, failure:5` even if both are currently `healthy`.

### Cascade deletion
Deleting a `ProxySourceConfig` cascades to all its `ValidProxy` rows via `ON DELETE CASCADE`.

### JSON/XML content must not be truncated
The parser needs complete JSON/XML to parse correctly. Only raw_text/CSV can safely truncate (first 10K chars).

## 8. Environment variables

| Variable | Description | Default |
|----------|-------------|---------|
| `PILGRIM_AI_ENABLED` | Enable AI-powered features | `false` |
| `PILGRIM_LLM_PROVIDER` | LLM provider (`ollama`) | `ollama` |
| `PILGRIM_OLLAMA_BASE_URL` | Ollama API base URL | `http://host.docker.internal:11434` |
| `PILGRIM_OLLAMA_MODEL` | Ollama model name | `llama3.2` |
| `PILGRIM_OLLAMA_TOKEN` | Ollama bearer token (optional) | — |
| `PILGRIM_AI_MAX_HTML_CHARS` | Max HTML chars sent to LLM | `30000` |

## 9. Frontend conventions

- Proxy pages: `ProxySources/` (list, create, detail, edit) and `Proxies/` (list with add modal)
- "Add Proxy" modal uses `createPortal(modal, document.body)` — the `.animate-in` CSS class uses `transform: translateY()` which creates a new containing block, breaking `position: fixed` for child modals
- AI Analysis panel on `ProxySourceCreate` and `ProxySourceEdit` — shows "Analyze" and "Verify Parsing" buttons
- Manual proxies shown with cyan "Manual" badge in the Source column
- Source filter dropdown: "All sources", "Manual", each source name