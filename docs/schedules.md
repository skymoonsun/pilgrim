# Schedules & Callbacks Guide

Schedules let you automate crawl jobs on a recurring basis and optionally send results to external APIs via webhook callbacks.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Architecture](#architecture)
- [Creating a Schedule](#creating-a-schedule)
- [Schedule Timing](#schedule-timing)
- [Config Links & URL Targets](#config-links--url-targets)
- [Callback System](#callback-system)
- [Field Mapping Reference](#field-mapping-reference)
- [API Reference](#api-reference)
- [Seed Schedules](#seed-schedules)
- [Operational Notes](#operational-notes)

---

## Core Concepts

```
CrawlSchedule
├── name, description, timezone
├── timing (cron_expression OR interval_seconds)
├── config_links[]                         ← one per crawl config
│   ├── config_id → CrawlConfiguration
│   ├── priority
│   └── url_targets[]                      ← URLs for THIS config only
│       ├── url
│       ├── label
│       └── is_active
├── callback (optional, 1:1)
│   ├── url, method, headers
│   ├── field_mapping                      ← payload transformation
│   ├── batch_results, retry_count
│   └── callback_logs[]                    ← audit trail
└── tracking
    ├── next_run_at, last_run_at
    └── run_count
```

**Key principle:** URLs belong to their config — not to the schedule directly. When a schedule triggers, each config only crawls its own URLs. There is no cartesian product.

---

## Architecture

```
┌─────────────┐
│  Celery Beat │─── 30s tick ──▶ check_schedules task
└──────────────┘                     │
                                     ▼
                          ┌─────────────────────┐
                          │ For each due schedule│
                          │ (next_run_at ≤ now)  │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │  For each config_link│
                          │   → for each URL     │
                          │     → create CrawlJob│
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │ Enqueue run_crawl_job│
                          │ to Celery workers    │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │ Job completes →      │
                          │ if callback active:  │
                          │ enqueue send_callback│
                          └─────────────────────┘
```

**How scheduling works:**

1. Celery Beat runs `check_schedules` every 30 seconds
2. It queries `crawl_schedules` where `is_active=True` and `next_run_at ≤ now`
3. For each due schedule, it creates `CrawlJob` rows for every (config, url) pair
4. Each job is enqueued to Celery workers for execution
5. `next_run_at` is updated to the next occurrence
6. When a job completes, if the schedule has an active callback, `send_callback` fires

---

## Creating a Schedule

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/schedules/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My Hourly Scrape",
    "description": "Scrapes product prices every hour",
    "timezone": "Europe/Istanbul",
    "interval_seconds": 3600,
    "default_queue": "crawl_default",
    "config_links": [
      {
        "config_id": "uuid-of-config",
        "urls": [
          {"url": "https://example.com/products", "label": "Products Page"},
          {"url": "https://example.com/deals", "label": "Deals Page"}
        ]
      }
    ]
  }'
```

### Via Dashboard

1. Navigate to **Schedules** → **New Schedule**
2. Fill in the general info (name, timezone, queue)
3. Choose timing type (interval or cron)
4. Click configs from the available list — each gets its own URL entry card
5. Add target URLs for each config
6. Optionally enable callback with field mapping
7. Click **Create Schedule**

### Via Seed

See `backend/seeds/0002_sample_schedules.py` for examples.

---

## Schedule Timing

### Interval-Based

Set `interval_seconds` to repeat at a fixed interval:

| Interval | Seconds | Example |
|----------|---------|---------|
| Every 30 min | `1800` | Quick monitoring |
| Hourly | `3600` | Standard monitoring |
| Every 6 hours | `21600` | Moderate checking |
| Daily | `86400` | Daily snapshots |

### Cron-Based

Set `cron_expression` for precise control:

```
┌───────────── minute (0-59)
│ ┌───────────── hour (0-23)
│ │ ┌───────────── day of month (1-31)
│ │ │ ┌───────────── month (1-12)
│ │ │ │ ┌───────────── day of week (0-6, Sun=0)
│ │ │ │ │
* * * * *
```

| Cron | Description |
|------|-------------|
| `0 */6 * * *` | Every 6 hours |
| `30 9 * * 1-5` | Weekdays at 09:30 |
| `0 0 * * *` | Midnight daily |
| `0 8,20 * * *` | 08:00 and 20:00 |
| `*/15 * * * *` | Every 15 minutes |

> **Note:** Only one of `cron_expression` or `interval_seconds` should be set.

---

## Config Links & URL Targets

### How It Works

Each schedule contains **config links** — each link pairs a `CrawlConfiguration` with its own set of target URLs:

```json
{
  "config_links": [
    {
      "config_id": "books-listing-config-uuid",
      "urls": [
        {"url": "https://books.toscrape.com/", "label": "Page 1"},
        {"url": "https://books.toscrape.com/catalogue/page-2.html", "label": "Page 2"}
      ]
    },
    {
      "config_id": "books-detail-config-uuid",
      "urls": [
        {"url": "https://books.toscrape.com/catalogue/some-book/index.html", "label": "Book Detail"}
      ]
    }
  ]
}
```

### Trigger Output

When this schedule triggers, it creates **3 jobs** (not 6):

| Job | Config | URL |
|-----|--------|-----|
| 1 | books-listing | Page 1 |
| 2 | books-listing | Page 2 |
| 3 | books-detail | Book Detail |

### Managing URLs at Runtime

Add/remove URLs without recreating the schedule:

```bash
# Add URL to a specific config link
curl -X POST http://localhost:8000/api/v1/schedules/{id}/config-links/{link_id}/urls \
  -H "Content-Type: application/json" \
  -d '{"url": "https://books.toscrape.com/catalogue/page-4.html", "label": "Page 4"}'

# Remove URL
curl -X DELETE http://localhost:8000/api/v1/schedules/{id}/urls/{url_id}
```

---

## Callback System

Callbacks let you send crawl results to external APIs automatically after a schedule run completes.

### Enabling a Callback

```bash
curl -X PUT http://localhost:8000/api/v1/schedules/{id}/callback \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://api.example.com/webhook",
    "method": "POST",
    "headers": {
      "Authorization": "Bearer your-token"
    },
    "field_mapping": {
      "field_mapping": {
        "product_name": "$.data.title",
        "price": "$.data.price",
        "source": "$.url"
      },
      "static_fields": {
        "source_system": "pilgrim"
      },
      "wrap_key": "results"
    },
    "batch_results": true,
    "retry_count": 3,
    "retry_delay_seconds": 30
  }'
```

### Callback Modes

| Mode | `batch_results` | Behaviour |
|------|-----------------|-----------|
| **Individual** | `false` | One HTTP request per completed job |
| **Batch** | `true` | One HTTP request with all results after all jobs complete |

### Retry Behaviour

- `retry_count`: Maximum retry attempts (0-10)
- `retry_delay_seconds`: Delay between retries (multiplied by attempt number)
- Example: `retry_count=3, retry_delay_seconds=30` → retries at 30s, 60s, 90s

### Callback Logs

Every callback attempt is logged with:
- Request URL, method, body
- Response status, body
- Success/failure, error message
- Duration, attempt number

View logs via API:

```bash
curl http://localhost:8000/api/v1/schedules/{id}/callback/logs
```

Or in the Dashboard on the Schedule Detail page.

---

## Field Mapping Reference

The `field_mapping` JSON controls how crawl results are transformed before sending to the callback endpoint.

### Structure

```json
{
  "field_mapping": {
    "target_field_name": "$.source.path",
    ...
  },
  "static_fields": {
    "constant_key": "constant_value",
    ...
  },
  "wrap_key": "results"
}
```

### Path Syntax

| Path | Source | Example Value |
|------|--------|---------------|
| `$.data.*` | Extraction result fields | `$.data.title` → `"iPhone 15"` |
| `$.url` | Source URL | `"https://example.com/page"` |
| `$.metadata.timestamp` | ISO timestamp | `"2026-04-15T21:00:00Z"` |
| `$.metadata.job_id` | Job UUID | `"abc-123-..."` |
| `$.metadata.schedule_id` | Schedule UUID | `"def-456-..."` |
| `$.metadata.http_status` | HTTP status code | `200` |

### Example Transformation

**Extraction result:**
```json
{
  "data": {"title": "iPhone 15", "price": "999.99"},
  "url": "https://shop.com/iphone",
  "http_status": 200
}
```

**Field mapping:**
```json
{
  "field_mapping": {
    "product_name": "$.data.title",
    "product_price": "$.data.price",
    "source_url": "$.url"
  },
  "static_fields": {
    "source": "pilgrim",
    "version": "1.0"
  },
  "wrap_key": "payload"
}
```

**Resulting callback payload:**
```json
{
  "payload": {
    "product_name": "iPhone 15",
    "product_price": "999.99",
    "source_url": "https://shop.com/iphone"
  },
  "source": "pilgrim",
  "version": "1.0",
  "_metadata": {
    "schedule_id": "...",
    "job_id": "...",
    "timestamp": "2026-04-15T21:00:00Z"
  }
}
```

---

## API Reference

### Schedule CRUD

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/schedules/` | Create schedule |
| `GET` | `/api/v1/schedules/` | List schedules |
| `GET` | `/api/v1/schedules/{id}` | Get schedule detail |
| `PATCH` | `/api/v1/schedules/{id}` | Update schedule |
| `DELETE` | `/api/v1/schedules/{id}` | Delete schedule |

### Trigger

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/schedules/{id}/trigger` | Manual trigger |

### URL Management

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/v1/schedules/{id}/config-links/{link_id}/urls` | Add URL to config |
| `DELETE` | `/api/v1/schedules/{id}/urls/{url_id}` | Remove URL |

### Callback

| Method | Path | Description |
|--------|------|-------------|
| `PUT` | `/api/v1/schedules/{id}/callback` | Set callback |
| `DELETE` | `/api/v1/schedules/{id}/callback` | Remove callback |
| `GET` | `/api/v1/schedules/{id}/callback/logs` | Get logs |

---

## Seed Schedules

The `0002_sample_schedules.py` seed creates 3 sample schedules:

### 1. Books Listing Monitor

| Field | Value |
|-------|-------|
| **Timing** | Hourly (interval: 3600s) |
| **Queue** | `crawl_default` |
| **Config 1** | `books-toscrape-listing` (3 URLs: pages 1-3) |
| **Config 2** | `books-toscrape-detail` (2 URLs: specific books) |
| **Callback** | None |
| **Total jobs per run** | 5 |

### 2. Quotes Daily Monitor

| Field | Value |
|-------|-------|
| **Timing** | Cron: `0 */6 * * *` (every 6 hours) |
| **Timezone** | `Europe/Istanbul` |
| **Config** | `quotes-toscrape-listing` (2 URLs: pages 1-2) |
| **Callback** | None |
| **Total jobs per run** | 2 |

### 3. HN Headlines Tracker

| Field | Value |
|-------|-------|
| **Timing** | Every 30 min (interval: 1800s) |
| **Queue** | `crawl_high` |
| **Config** | `hackernews-frontpage` (1 URL: front page) |
| **Callback** | ✅ POST to webhook |
| **Total jobs per run** | 1 |

Callback transforms HN extraction data into:
```json
{
  "payload": {
    "headlines": ["...", "..."],
    "links": ["...", "..."],
    "scores": ["...", "..."],
    "source_url": "https://news.ycombinator.com/",
    "scraped_at": "2026-04-15T21:00:00Z"
  },
  "source_system": "pilgrim",
  "feed": "hackernews"
}
```

---

## Operational Notes

### Queue Routing

| Queue | Use Case |
|-------|----------|
| `crawl_high` | Time-sensitive, user-triggered |
| `crawl_default` | Routine scheduled jobs |
| `crawl_low` | Backfill, bulk jobs |
| `maintenance` | check_schedules, send_callback |

### Polling vs Dynamic Beat

Pilgrim uses **polling-based scheduling** (not dynamic Celery Beat). The `check_schedules` task runs every 30 seconds and queries the DB for due schedules. This is simpler to debug and doesn't require a custom Beat scheduler.

**Trade-off:** Maximum schedule latency is ~30 seconds. For sub-second precision, a custom DB-backed Celery Beat scheduler would be needed.

### Deduplication

- The scheduler checks `next_run_at ≤ now` and updates it after trigger
- If a schedule is still running when the next tick arrives, it won't be re-triggered (because `next_run_at` was already advanced)

### Monitoring

Check schedule health:

```bash
# List active schedules with next run times
curl "http://localhost:8000/api/v1/schedules/?active_only=true"

# Check callback delivery
curl "http://localhost:8000/api/v1/schedules/{id}/callback/logs?limit=10"
```
