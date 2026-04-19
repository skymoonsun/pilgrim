# Proxy Management Guide

Pilgrim includes a built-in proxy management system for fetching, parsing, validating, and rotating proxies from configurable sources — as well as adding paid/custom proxies manually.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Architecture](#architecture)
- [Proxy Sources](#proxy-sources)
- [Supported Formats](#supported-formats)
- [Creating a Proxy Source](#creating-a-proxy-source)
- [Fetching & Validation](#fetching--validation)
- [Health Status](#health-status)
- [Manual Proxies](#manual-proxies)
- [AI-Powered Source Analysis](#ai-powered-source-analysis)
- [Source Verification](#source-verification)
- [Proxy Rotation](#proxy-rotation)
- [Celery Tasks](#celery-tasks)
- [API Reference](#api-reference)

---

## Core Concepts

```
ProxySourceConfig (stored in DB)
├── name, description
├── url                        → where to fetch the proxy list
├── format_type                → raw_text, json, csv, xml
├── extraction_spec            → field mapping for structured formats
├── source_headers             → HTTP headers for fetching the source
├── validation_urls            → URLs to test proxy connectivity
├── require_all_urls           → all URLs must pass for "healthy"
├── validation_timeout         → per-request timeout (seconds)
├── fetch_interval_seconds     → auto-refresh period
├── proxy_ttl_seconds          → when fetched proxies expire
└── last_fetched_at, last_fetch_error

ValidProxy (stored in DB)
├── source_config_id           → FK to ProxySourceConfig (NULL = manual)
├── ip, port, protocol         → unique key: (ip, port, protocol)
├── username, password          → optional credentials
├── health                     → healthy | degraded | unhealthy
├── avg_response_ms            → average validation response time
├── success_count, failure_count → cumulative health signal
├── last_checked_at, last_success_at
└── expires_at                 → NULL for manual proxies
```

**Key principle:** Proxy sources define **where** and **how** to get proxies. Individual proxies are stored as `ValidProxy` rows. Manual proxies have no source link and never expire — they persist until explicitly deleted.

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Proxy Management Flow                      │
└──────────────────────────────────────────────────────────────┘

  ┌─────────────┐     fetch      ┌──────────────┐    parse     ┌──────────────┐
  │ Proxy Source │──────────────▶│   httpx GET   │────────────▶│  Proxy Parser│
  │  Config URL  │               │  (30s timeout)│             │ (raw/json/   │
  └─────────────┘               └──────────────┘              │  csv/xml)    │
                                                               └──────┬───────┘
                                                                      │ upsert
                                                                      ▼
                                                               ┌──────────────┐
                                                               │  ValidProxy  │
                                                               │    table     │
                                                               └──────┬───────┘
                                                                      │ validate
                                                                      ▼
                                                               ┌──────────────┐     ┌──────────────┐
                                                               │  httpx via   │────▶│ Validation   │
                                                               │  proxy URL   │     │  URL(s)      │
                                                               └──────────────┘     └──────────────┘
                                                                      │
                                                                      ▼
                                                              update health, response_ms,
                                                              success/failure counts

  ┌─────────────┐
  │ Manual Proxy│──── create (single/bulk) ────▶ ValidProxy table
  │  (no source)│                                  (source_config_id = NULL)
  └─────────────┘

  ┌─────────────┐     hourly      ┌──────────────┐
  │  Celery Beat │──────────────▶│expire_proxies │─── DELETE expired proxies
  └─────────────┘               └──────────────┘    (expires_at < now)
```

---

## Proxy Sources

A **proxy source** is a URL that serves a list of proxies in a known format. Pilgrim fetches, parses, and validates proxies from these sources on a configurable schedule.

### Source Configuration Fields

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `name` | string | — | Unique identifier (1-100 chars) |
| `description` | string? | `null` | Optional description |
| `url` | string | — | Proxy list URL (up to 2000 chars) |
| `format_type` | enum | `raw_text` | Format: `raw_text`, `json`, `csv`, `xml` |
| `extraction_spec` | JSON? | `null` | Field mapping for structured formats |
| `source_headers` | JSON? | `null` | HTTP headers sent when fetching the source |
| `validation_urls` | JSON | `{"urls": []}` | URLs to test proxy connectivity |
| `require_all_urls` | bool | `true` | All validation URLs must succeed for "healthy" |
| `validation_timeout` | int | `10` | Per-validation-request timeout (1-120s) |
| `fetch_interval_seconds` | int | `3600` | Auto-refresh interval (min 60s) |
| `proxy_ttl_seconds` | int | `86400` | Time until fetched proxies expire (min 60s) |
| `is_active` | bool | `true` | Whether the source is active |

### Proxy TTL

Fetched proxies have an `expires_at` timestamp set to `fetched_at + proxy_ttl_seconds`. The `expire_proxies` Celery task (runs hourly via Beat) deletes proxies past their expiry. This ensures stale proxies from free lists are cleaned up automatically.

Manual proxies have `expires_at = NULL` and are **never** expired.

---

## Supported Formats

### raw_text

Plain text lists — one proxy per line. Supports multiple conventions:

```
# Basic host:port
1.2.3.4:8080

# With protocol prefix
socks5://5.6.7.8:1080
https://9.10.11.12:3128

# With credentials
http://user:pass@13.14.15.16:80

# Host:port:user:pass format
1.2.3.4:8080:user:pass

# Comments are supported
# This is a comment line
```

Lines starting with `#` are skipped. Blank lines are ignored.

The parser recognizes IPv4 and IPv6 addresses.

### JSON

JSON arrays or objects with optional extraction spec for field mapping:

**Without extraction spec** (auto-detects common keys):
```json
[
  {"ip": "1.2.3.4", "port": 8080, "type": "http"},
  {"ip_address": "5.6.7.8", "port": 3128}
]
```

The parser automatically looks for keys like `ip`, `ip_address`, `host` for the address, and `port` for the port number.

**With extraction spec:**
```json
{
  "data": {
    "proxies": [
      {"addr": "1.2.3.4", "prt": 8080, "proto": "socks5"}
    ]
  }
}
```

```json
{
  "list_path": "data.proxies",
  "fields": {
    "ip": "addr",
    "port": "prt",
    "protocol": "proto"
  }
}
```

### CSV

CSV data with auto-detected column names:

```csv
ip,port,protocol,username,password
1.2.3.4,8080,http,,
5.6.7.8,1080,socks5,user,pass
```

The parser tries common column names: `ip`, `ip_address`, `host`, `port`, `protocol`, `type`, `username`, `user`, `password`, `pass`.

### XML

XML documents with proxy entries:

```xml
<proxies>
  <proxy>
    <ip>1.2.3.4</ip>
    <port>8080</port>
    <protocol>http</protocol>
  </proxy>
</proxies>
```

The parser iterates over `<proxy>`, `<item>`, or `<row>` elements and looks for child elements by common tag names (case-insensitive).

---

## Creating a Proxy Source

### Via API

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
    "validation_urls": {"urls": ["https://httpbin.org/ip"]},
    "require_all_urls": false
  }'

# Source with custom headers (e.g., API key)
curl -X POST http://localhost:8000/api/v1/proxy-sources/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Premium Proxy Feed",
    "url": "https://premium.example.com/feed",
    "format_type": "raw_text",
    "source_headers": {"Authorization": "Bearer your-api-key"},
    "validation_urls": {"urls": ["https://httpbin.org/ip", "https://example.com"]},
    "require_all_urls": true,
    "validation_timeout": 15
  }'
```

### Via Dashboard

1. Navigate to **Proxy Sources** → **New Proxy Source**
2. Fill in name, URL, and format type
3. For structured formats (JSON/CSV/XML), provide extraction spec
4. Set validation URLs and health criteria
5. Optionally use **AI Analysis** to auto-detect format and settings
6. Click **Create**

### Via Swagger UI

Open `http://localhost:8000/docs` and use the `POST /api/v1/proxy-sources/` endpoint.

---

## Fetching & Validation

### Triggering a Fetch

Fetching downloads the proxy list, parses it, and upserts proxies into the database:

```bash
# Trigger fetch for a source
curl -X POST http://localhost:8000/api/v1/proxy-sources/{id}/fetch
```

This enqueues a Celery task. Each parsed proxy is upserted by `(ip, port, protocol)`:
- **New proxy** → created with `healthy` status
- **Existing proxy** → source link updated, health refreshed, credentials updated

After fetching, the source's `last_fetched_at` is updated. On failure, `last_fetch_error` is set.

### Triggering Validation

Validation tests each proxy against the configured validation URLs:

```bash
# Trigger validation for a source
curl -X POST http://localhost:8000/api/v1/proxies/{source_id}/validate
```

For each proxy, the validator attempts an HTTP request through the proxy to each validation URL. Health is determined based on the results:

| `require_all_urls` | All succeed | Some succeed | None succeed |
|--------------------|-------------|--------------|--------------|
| `true` (default) | `healthy` | `degraded` | `unhealthy` |
| `false` | `healthy` | `healthy` | `unhealthy` |

After validation, each proxy's `avg_response_ms`, `success_count`/`failure_count`, `last_checked_at`, and `last_success_at` are updated.

---

## Health Status

| Status | Color | Meaning |
|--------|-------|---------|
| `healthy` | Green | Successfully connecting through the proxy |
| `degraded` | Amber | Partial connectivity (some validation URLs failing) |
| `unhealthy` | Red | No validation URLs are reachable through the proxy |

### Health Metrics

Each proxy tracks cumulative statistics:

| Metric | Description |
|--------|-------------|
| `avg_response_ms` | Average response time across validations |
| `success_count` | Cumulative successful validations |
| `failure_count` | Cumulative failed validations |
| `last_checked_at` | Last time this proxy was validated |
| `last_success_at` | Last time this proxy passed validation |

These metrics provide a longitudinal quality signal — a proxy with `success_count: 50, failure_count: 2` is clearly more reliable than one with `success_count: 1, failure_count: 5`, even if both are currently `healthy`.

### Querying by Health

```bash
# List only healthy proxies
curl "http://localhost:8000/api/v1/proxies/?health=healthy&limit=50"

# List degraded proxies from a specific source
curl "http://localhost:8000/api/v1/proxies/?source_id={uuid}&health=degraded"

# List unhealthy proxies
curl "http://localhost:8000/api/v1/proxies/?health=unhealthy"
```

---

## Manual Proxies

Manual proxies are paid or custom proxies that you add directly — they are **not** fetched from a URL source and **never** expire. They persist until explicitly deleted.

### Adding a Single Manual Proxy

```bash
curl -X POST http://localhost:8000/api/v1/proxies/ \
  -H "Content-Type: application/json" \
  -d '{
    "ip": "203.0.113.50",
    "port": 8080,
    "protocol": "http",
    "username": "myuser",
    "password": "mypass"
  }'
```

### Bulk-Adding Manual Proxies

```bash
curl -X POST http://localhost:8000/api/v1/proxies/bulk \
  -H "Content-Type: application/json" \
  -d '{
    "raw_text": "203.0.113.50:8080\nsocks5://user:pass@198.51.100.1:1080\nhttps://192.0.2.10:3128",
    "default_protocol": "http"
  }'
```

The `default_protocol` is applied to lines that don't specify a protocol prefix. The response includes created and skipped counts:

```json
{
  "created": 2,
  "skipped": 1,
  "items": [...]
}
```

### Duplicate Handling

If a manually-added proxy already exists (by `ip + port + protocol`), it is **converted to manual**:
- `source_config_id` is set to `NULL`
- `expires_at` is cleared (no TTL)
- Credentials are updated

This means you can "claim" a proxy that was previously fetched from a source — it becomes manual and won't be affected by source fetches or the expiry task.

### Via Dashboard

1. Navigate to **Proxies** page
2. Click **Add Proxy**
3. Choose **Single** or **Bulk Add** tab
4. Fill in the details and submit

Manual proxies are shown with a cyan **Manual** badge in the Source column.

### Listing Manual Proxies

```bash
# List only manual (source-less) proxies
curl "http://localhost:8000/api/v1/proxies/?manual_only=true"
```

---

## AI-Powered Source Analysis

When AI is enabled (`PILGRIM_AI_ENABLED=true`), Pilgrim can analyze a proxy source URL and automatically detect the format and suggest extraction settings.

### How It Works

1. You provide a **proxy list URL**
2. Pilgrim fetches the content
3. For **raw text**: a fast heuristic detects the format (no LLM call needed — if ≥50% of the first 20 lines match raw text patterns)
4. For **structured formats** (JSON, CSV, XML): the content is sent to the LLM, which suggests `format_type`, `extraction_spec`, `name`, and `description`
5. Sample proxies are parsed and displayed
6. The form is auto-filled with the detected settings

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/ai/suggest-proxy-source \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/proxies.txt"}'
```

Response:

```json
{
  "format_type": "raw_text",
  "extraction_spec": null,
  "suggested_name": "Example Proxy List",
  "description": "A list of HTTP/HTTPS proxies in plain text format",
  "sample_proxies": [
    {"ip": "1.2.3.4", "port": 8080, "protocol": "http"},
    {"ip": "5.6.7.8", "port": 3128, "protocol": "https"}
  ],
  "model_used": "heuristic",
  "content_length": 15420
}
```

### Via Dashboard

On the **New Proxy Source** page, the **AI Analysis** panel lets you paste a URL and click **Analyze**. The form is auto-filled with detected settings.

---

## Source Verification

Before saving a proxy source, you can **verify** that the format and extraction spec correctly parse the proxy list. This works like the "Verify Spec" feature for crawl configurations.

### How It Works

1. Pilgrim fetches the source URL content
2. Parses it with the given `format_type` and `extraction_spec`
3. Returns the total count and sample parsed proxies
4. No LLM call — this is pure fetch + parse verification

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/ai/verify-proxy-source \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://example.com/proxies.json",
    "format_type": "json",
    "extraction_spec": {
      "list_path": "data",
      "fields": {"ip": "ip_address", "port": "port", "protocol": "type"}
    }
  }'
```

Response:

```json
{
  "success": true,
  "total_parsed": 150,
  "sample_proxies": [
    {"ip": "1.2.3.4", "port": 8080, "protocol": "http"},
    {"ip": "5.6.7.8", "port": 3128, "protocol": "https"}
  ],
  "format_type": "json",
  "content_length": 28500,
  "error": null
}
```

### Via Dashboard

On the **New Proxy Source** or **Edit Proxy Source** page, click **Verify Parsing** after configuring the format and extraction spec. Results show success/failure, total parsed count, and sample proxies.

---

## Proxy Rotation

Crawl configurations with `use_proxy: true` will request a random healthy proxy for each request:

```bash
# Enable proxy rotation on a crawl config
curl -X PATCH http://localhost:8000/api/v1/crawl-configs/{id} \
  -H "Content-Type: application/json" \
  -d '{"use_proxy": true}'
```

The proxy selection uses `get_random_healthy()`, which:
1. Queries `ValidProxy` rows with `health = 'healthy'`
2. Optionally filters by `protocol`
3. Returns a random proxy using `ORDER BY RANDOM() LIMIT 1`

If no healthy proxy is available, the request proceeds without a proxy.

---

## Celery Tasks

| Task | Queue | Trigger | Description |
|------|-------|---------|-------------|
| `pilgrim.proxy.fetch_proxy_source` | `maintenance` | Manual (`POST /proxy-sources/{id}/fetch`) | Fetch, parse, and upsert proxies from a source URL |
| `pilgrim.proxy.validate_proxies` | `maintenance` | Manual (`POST /proxies/{source_id}/validate`) | Test proxy connectivity against validation URLs |
| `pilgrim.proxy.expire_proxies` | `maintenance` | Hourly (Beat) | Delete proxies past their `expires_at` |

### Fetch Task Details

- Auto-retries on `httpx.TimeoutException` and `httpx.ConnectError` (up to 3 retries with backoff)
- Fetches the source URL with a 30-second timeout
- Parses with the configured `format_type` and `extraction_spec`
- Upserts each proxy by `(ip, port, protocol)` unique key
- Sets `expires_at = now + proxy_ttl_seconds` on each proxy
- Updates `last_fetched_at` on success; sets `last_fetch_error` on failure

### Validation Task Details

- Tests each proxy against all `validation_urls`
- Respects `require_all_urls` and `validation_timeout` settings
- Updates health status, response metrics, and success/failure counts

### Expiry Task Details

- Bulk deletes all proxies where `expires_at IS NOT NULL AND expires_at < now`
- **Manual proxies** (`expires_at = NULL`) are never expired
- Runs hourly via Celery Beat

---

## API Reference

### Proxy Sources

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/proxy-sources/` | Create a proxy source config |
| `GET` | `/api/v1/proxy-sources/` | List all proxy sources |
| `GET` | `/api/v1/proxy-sources/{id}` | Get proxy source by ID |
| `PATCH` | `/api/v1/proxy-sources/{id}` | Update a proxy source config |
| `DELETE` | `/api/v1/proxy-sources/{id}` | Delete a proxy source config |
| `POST` | `/api/v1/proxy-sources/{id}/fetch` | Trigger proxy fetch for a source |

### Valid Proxies

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/proxies/` | Add a single manual proxy |
| `POST` | `/api/v1/proxies/bulk` | Bulk-add manual proxies from raw text |
| `GET` | `/api/v1/proxies/` | List proxies (with filters) |
| `GET` | `/api/v1/proxies/{id}` | Get proxy by ID |
| `DELETE` | `/api/v1/proxies/{id}` | Delete a proxy |
| `POST` | `/api/v1/proxies/{source_id}/validate` | Trigger validation for a source |

### AI Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/ai/suggest-proxy-source` | AI-analyze a proxy source URL |
| `POST` | `/api/v1/ai/verify-proxy-source` | Verify parsing config against a URL |

### Query Parameters for `GET /proxies/`

| Parameter | Type | Description |
|-----------|------|-------------|
| `source_id` | UUID | Filter by proxy source |
| `manual_only` | bool | Show only manual (source-less) proxies |
| `protocol` | string | Filter by protocol: `http`, `https`, `socks4`, `socks5` |
| `health` | string | Filter by health: `healthy`, `degraded`, `unhealthy` |
| `skip` | int | Pagination offset (default 0) |
| `limit` | int | Page size (1-200, default 50) |