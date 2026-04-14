# Crawl Configurations Guide

Crawl Configurations are the core concept in Pilgrim. A configuration defines **how** to scrape a page — which fetcher to use, what data to extract, and how to behave (rate limiting, headers, proxy). The **target URL** is provided separately at runtime.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Creating a Configuration](#creating-a-configuration)
- [Extraction Spec Reference](#extraction-spec-reference)
- [Scraper Profiles](#scraper-profiles)
- [Fetch Options](#fetch-options)
- [Using a Configuration](#using-a-configuration)
- [Advanced Patterns](#advanced-patterns)
- [Examples](#examples)

---

## Core Concepts

```
CrawlConfiguration (stored in DB)
├── name                  → unique identifier
├── scraper_profile       → which Scrapling fetcher to use
├── extraction_spec       → CSS/XPath selectors for data extraction
├── fetch_options         → timeouts, impersonation, etc.
├── use_proxy             → whether to use proxy rotation
├── rotate_user_agent     → randomize User-Agent header
├── custom_headers        → additional HTTP headers
├── custom_delay          → delay between requests (seconds)
└── max_concurrent        → max parallel requests
```

A configuration is **URL-agnostic** — you define it once and reuse it with different URLs. For example, one config can scrape any listing page from the same site, because the HTML structure is consistent.

---

## Creating a Configuration

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/crawl-configs/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "my-config",
    "scraper_profile": "fetcher",
    "extraction_spec": {
      "fields": {
        "title": {"selector": "h1::text", "type": "css"}
      }
    }
  }'
```

### Via Swagger UI

Open `http://localhost:8000/docs` and use the `POST /api/v1/crawl-configs/` endpoint.

### Via Seeds

Create a Python file in `backend/seeds/` with a version prefix:

```python
# backend/seeds/0002_my_new_config.py

async def run(session):
    from app.models.crawl_config import CrawlConfiguration
    from app.models.enums import ScraperProfile

    config = CrawlConfiguration(
        name="my-new-config",
        scraper_profile=ScraperProfile.FETCHER,
        extraction_spec={
            "fields": {
                "title": {"selector": "h1::text", "type": "css"}
            }
        },
    )
    session.add(config)
    await session.flush()
```

Then run: `make seed`

---

## Extraction Spec Reference

The `extraction_spec` field is a JSON object that tells the extraction engine what data to pull from the HTML response.

### Basic Structure

```json
{
  "fields": {
    "field_name": {
      "selector": "CSS or XPath expression",
      "type": "css" | "xpath",
      "multiple": false
    }
  }
}
```

### Field Options

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| `selector` | string | — | CSS or XPath selector expression |
| `type` | string | `"css"` | Selector type: `"css"` or `"xpath"` |
| `multiple` | bool | `false` | If `true`, returns a list of all matches; if `false`, returns the first match |
| `children` | object | — | Nested fields for structured extraction (see [Nested Extraction](#nested-extraction)) |

### CSS Selector Syntax

Pilgrim uses Scrapling's CSS selector extensions:

```
h1::text                     → Text content of <h1>
a::attr(href)                → href attribute of <a>
p.price::text                → Text of <p class="price">
div#main h2::text            → Text of <h2> inside <div id="main">
ul > li::text                → Direct child <li> text
span.rate::attr(class)       → class attribute value
table tr:nth-child(2) td     → Second row cells
```

### XPath Selector Syntax

```
//h1/text()                  → Text of <h1>
//a/@href                    → href attribute
//div[@class='price']/text() → Text of <div class="price">
//table/tr[2]/td/text()      → Second row cell text
```

### Nested Extraction

For repeating elements (e.g., product cards on a listing page), use `children`:

```json
{
  "fields": {
    "products": {
      "selector": "div.product-card",
      "type": "css",
      "multiple": true,
      "children": {
        "name": {"selector": "h3::text", "type": "css"},
        "price": {"selector": ".price::text", "type": "css"},
        "url": {"selector": "a::attr(href)", "type": "css"}
      }
    }
  }
}
```

> **Note:** Nested extraction via `children` is planned for a future release. Currently, use flat field definitions with `:nth-child()` or `:first-child` selectors for structured data.

---

## Scraper Profiles

Each profile maps to a different Scrapling fetcher class:

| Profile | Class | Use Case | Requires Browser? |
|---------|-------|----------|-------------------|
| `fetcher` | `Fetcher` | Static HTML pages, APIs | No |
| `http_session` | `FetcherSession` | Session-based scraping (cookies persist) | No |
| `stealth` | `StealthyFetcher` | Anti-bot protected sites | Yes |
| `dynamic` | `DynamicFetcher` | JavaScript-rendered pages (SPA) | Yes |
| `spider` | Spider classes | Multi-page crawls | Depends |

### When to Choose Which

- **`fetcher`** (default) — Start here. Works for most static sites. Fastest and lightest.
- **`http_session`** — When you need cookies to persist across requests (login flows, pagination with session state).
- **`stealth`** — When the target site uses Cloudflare, Imperva, or similar bot protection. Uses real browser fingerprints.
- **`dynamic`** — When critical content is loaded via JavaScript (React/Vue/Angular SPAs). Launches a headless browser.
- **`spider`** — For multi-page crawls with link following. Define spider classes in `app/crawlers/spiders/`.

> **Important:** `stealth` and `dynamic` profiles only work in the **worker** container (which includes browser dependencies). The slim **API** container does not have these libraries.

---

## Fetch Options

The `fetch_options` field is a JSON object passed to the Scrapling fetcher constructor:

```json
{
  "timeout": 30,
  "stealthy_headers": true,
  "follow_redirects": true
}
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `timeout` | int | 30 | Request timeout in seconds |
| `stealthy_headers` | bool | `true` | Use realistic browser headers |
| `follow_redirects` | bool | `true` | Follow HTTP redirects |

---

## Using a Configuration

### Synchronous Scrape (Quick Test)

```bash
curl -X POST http://localhost:8000/api/v1/scrape/ \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "uuid-of-config",
    "url": "https://books.toscrape.com/"
  }'
```

Response:
```json
{
  "config_id": "uuid-of-config",
  "url": "https://books.toscrape.com/",
  "http_status": 200,
  "data": {
    "titles": ["A Light in the Attic", "Tipping the Velvet", ...],
    "prices": ["£51.77", "£53.74", ...]
  },
  "duration_ms": 342.5
}
```

> **Note:** Sync scraping runs in the API process. It's suitable for quick tests but blocks the request. For production workloads, use async jobs.

### Asynchronous Crawl Job (Production)

```bash
# 1. Enqueue a job
curl -X POST http://localhost:8000/api/v1/crawl/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "config_id": "uuid-of-config",
    "url": "https://books.toscrape.com/",
    "queue": "crawl_default",
    "priority": 5
  }'

# Response: {"crawl_job_id": "job-uuid", "status": "queued"}

# 2. Poll for completion
curl http://localhost:8000/api/v1/crawl/jobs/job-uuid
```

The job runs in a Celery worker and writes results to the `crawl_job_results` table.

---

## Advanced Patterns

### Rate Limiting

```json
{
  "custom_delay": 2.0,
  "max_concurrent": 3
}
```

This adds a 2-second delay between requests and limits to 3 concurrent requests.

### Custom Headers

```json
{
  "custom_headers": {
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.google.com/"
  }
}
```

### Config Versioning

Updating a config via `PATCH` changes it in place. For auditable changes, consider:
1. Creating new configs with versioned names (`my-config-v2`)
2. Deactivating old configs (`is_active: false`)

---

## Examples

### E-commerce Product Listing

```json
{
  "name": "shop-product-listing",
  "scraper_profile": "fetcher",
  "extraction_spec": {
    "fields": {
      "product_names": {
        "selector": "h2.product-title a::text",
        "type": "css",
        "multiple": true
      },
      "prices": {
        "selector": "span.price::text",
        "type": "css",
        "multiple": true
      },
      "image_urls": {
        "selector": "img.product-image::attr(src)",
        "type": "css",
        "multiple": true
      },
      "next_page": {
        "selector": "a.pagination-next::attr(href)",
        "type": "css"
      }
    }
  },
  "custom_delay": 1.5,
  "rotate_user_agent": true
}
```

### News Headlines

```json
{
  "name": "news-headlines",
  "scraper_profile": "fetcher",
  "extraction_spec": {
    "fields": {
      "headlines": {
        "selector": "//h2[contains(@class,'headline')]/a/text()",
        "type": "xpath",
        "multiple": true
      },
      "urls": {
        "selector": "//h2[contains(@class,'headline')]/a/@href",
        "type": "xpath",
        "multiple": true
      },
      "timestamps": {
        "selector": "time::attr(datetime)",
        "type": "css",
        "multiple": true
      }
    }
  }
}
```

### JavaScript-Rendered SPA

```json
{
  "name": "spa-dashboard",
  "scraper_profile": "dynamic",
  "extraction_spec": {
    "fields": {
      "chart_data": {
        "selector": "div.chart-container::attr(data-values)",
        "type": "css"
      },
      "table_rows": {
        "selector": "table.data-table tbody tr td::text",
        "type": "css",
        "multiple": true
      }
    }
  },
  "fetch_options": {
    "timeout": 60
  }
}
```

> Remember: `dynamic` profile requires the **worker** container with browser dependencies.
