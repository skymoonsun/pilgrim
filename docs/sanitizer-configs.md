# Sanitizer Configurations Guide

Sanitizer configs define post-processing rules that clean up raw extracted data. They are standalone, reusable configurations that can be linked to any crawl config.

## Table of Contents

- [Core Concepts](#core-concepts)
- [Transform Types Reference](#transform-types-reference)
- [Creating a Sanitizer Config](#creating-a-sanitizer-config)
- [Linking to a Crawl Config](#linking-to-a-crawl-config)
- [AI-Powered Sanitizer Generation](#ai-powered-sanitizer-generation)
- [How Sanitizers Are Applied](#how-sanitizers-are-applied)
- [Examples](#examples)

---

## Core Concepts

Extraction specs pull raw data from web pages, but that data often needs cleanup:

| Raw value | Problem | After sanitizer |
|-----------|---------|-----------------|
| `"$18.99 USD"` | Currency symbol + suffix | `18.99` |
| `"  iPhone 15 Pro  "` | Extra whitespace | `"iPhone 15 Pro"` |
| `"In Stock"` | Needs boolean or normalization | `"in stock"` |
| `"$1,299.00"` | Currency + thousands separator | `1299.0` |
| `"https://store.com/cat/phone"` | Only want the last segment | `"phone"` |

A **sanitizer config** contains:

- **Name & description** — for identifying the config
- **Active flag** — inactive configs are skipped
- **Rules** — an ordered list of field-level transform chains

Each rule targets a single field from the extraction spec and applies one or more transforms in sequence.

### Rule structure

```json
{
  "field": "price",
  "transforms": [
    { "type": "regex_replace", "pattern": "[^0-9.]", "replacement": "" },
    { "type": "to_number" }
  ]
}
```

The transforms are applied **in order**: first `regex_replace` strips everything except digits and dots, then `to_number` converts the result to a float.

---

## Transform Types Reference

| Type | Parameters | Description | Example |
|------|-----------|-------------|---------|
| `strip` | — | Strip leading/trailing whitespace | `"  hello  "` → `"hello"` |
| `to_lower` | — | Convert to lowercase | `"Hello World"` → `"hello world"` |
| `to_upper` | — | Convert to uppercase | `"hello"` → `"HELLO"` |
| `to_number` | — | Remove non-numeric chars, convert to float | `"$18.99"` → `18.99` |
| `to_int` | — | Remove non-numeric chars, convert to integer | `"42 items"` → `42` |
| `regex_replace` | `pattern`, `replacement` | Apply regex substitution | See example below |
| `extract_number` | — | Extract first number from string | `"Price: $18.99"` → `18.99` |
| `trim_prefix` | `value` | Remove a prefix if present | `"SKU-1234"` → `"1234"` |
| `trim_suffix` | `value` | Remove a suffix if present | `"5.0 kg"` → `"5.0"` |
| `default` | `value` | Replace empty/null values with a default | `""` → `"N/A"` |
| `split_take` | `pattern` (separator), `index` | Split by separator, take element at index | `"a,b,c"` → `"b"` |

### Parameter details

- **`regex_replace`** — `pattern` is a Python regex, `replacement` is the replacement string (supports backreferences like `\1`).
- **`trim_prefix`** / **`trim_suffix`** — `value` is the string to trim. Only trims if the value actually starts/ends with it.
- **`default`** — Only applies when the value is `null` or an empty string. Existing non-empty values pass through unchanged.
- **`split_take`** — `pattern` is the separator (default: `,`), `index` is the 0-based position (default: `0`). Negative indices work like Python.
- **`to_number`** / **`to_int`** — Strip all non-numeric characters first, then convert. If no number is found, the original value is returned unchanged.
- **`extract_number`** — Finds the first number (integer or float) in the string. Returns the original value if no number is found.

---

## Creating a Sanitizer Config

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/sanitizer-configs/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Price Cleaner",
    "description": "Strips currency symbols and converts prices to numbers",
    "is_active": true,
    "rules": [
      {
        "field": "price",
        "transforms": [
          { "type": "regex_replace", "pattern": "[^0-9.]", "replacement": "" },
          { "type": "to_number" }
        ]
      },
      {
        "field": "title",
        "transforms": [
          { "type": "strip" },
          { "type": "regex_replace", "pattern": "\\s+", "replacement": " " }
        ]
      }
    ]
  }'
```

### Via Dashboard

1. Navigate to **Sanitizers** in the sidebar
2. Click **New Sanitizer Config**
3. Fill in name, description, and add rules
4. Each rule targets a field name from your extraction spec
5. Add transforms to the rule — the type dropdown shows available options
6. Some transforms require parameters (pattern, replacement, value, index)

---

## Linking to a Crawl Config

A sanitizer config is linked to a crawl config via the `sanitizer_config_id` field:

```bash
# Create a crawl config with a sanitizer
curl -X POST http://localhost:8000/api/v1/crawl-configs/ \
  -H "Content-Type: application/json" \
  -d '{
    "name": "product-scraper",
    "scraper_profile": "fetcher",
    "extraction_spec": {
      "fields": {
        "title": { "selector": "h1::text", "type": "css" },
        "price": { "selector": ".price::text", "type": "css" }
      }
    },
    "sanitizer_config_id": "<sanitizer-config-uuid>"
  }'
```

You can also set or change the sanitizer on an existing config:

```bash
# Link a sanitizer to an existing config
curl -X PATCH http://localhost:8000/api/v1/crawl-configs/{config_id} \
  -H "Content-Type: application/json" \
  -d '{"sanitizer_config_id": "<sanitizer-config-uuid>"}'

# Unlink the sanitizer
curl -X PATCH http://localhost:8000/api/v1/crawl-configs/{config_id} \
  -H "Content-Type: application/json" \
  -d '{"sanitizer_config_id": null}'
```

### From the Dashboard

In the crawl config creation or edit page, use the **Sanitizer Config** dropdown to select an existing sanitizer. You can also generate one inline via AI (see below).

---

## AI-Powered Sanitizer Generation

When AI is enabled (`PILGRIM_AI_ENABLED=true`), you can generate sanitizer rules automatically:

### From the Sanitizer Config page

1. Click **Generate with AI**
2. Enter the **Target URL** and **Extraction Spec** (JSON)
3. Optionally describe what to sanitize (e.g., "Price fields contain currency symbols like $18.99 USD")
4. Click **Generate Sanitizer Rules**
5. Review the suggested rules and before/after comparison
6. Click **Apply These Rules** to populate the form

### From the Crawl Config page (after verification)

1. Create or edit a crawl config
2. Use **Generate with AI** to create the extraction spec
3. Click **Verify Spec** to test it against a real URL
4. After verification, the **Sanitize Extracted Data** section appears
5. Describe what needs sanitizing (e.g., "Prices have currency symbols, titles need whitespace cleanup")
6. Click **Generate Sanitizer with AI**
7. Review the suggested rules and before/after comparison
8. Click **Create & Select This Sanitizer** to create the sanitizer config and auto-select it for this crawl config

### Via API

```bash
curl -X POST http://localhost:8000/api/v1/ai/suggest-sanitizer \
  -H "Content-Type: application/json" \
  -d '{
    "url": "https://store.example.com/product/123",
    "extraction_spec": {
      "fields": {
        "price": { "selector": ".price::text", "type": "css" },
        "title": { "selector": "h1::text", "type": "css" }
      }
    },
    "description": "Price fields contain currency symbols, titles have extra whitespace"
  }'
```

The response includes:

- `rules` — Suggested sanitizer rules
- `sample_before` — Raw extracted data
- `sample_after` — Data after applying the suggested rules

---

## How Sanitizers Are Applied

Sanitizers run **after** data extraction, in both:

1. **Synchronous scrape** (`POST /api/v1/scrape/`) — Applied immediately in the API process
2. **Async crawl jobs** — Applied by the Celery worker after extraction

The flow:

```
URL + Extraction Spec → Scrapling fetch → extract_data() → apply_sanitizer() → Final result
```

If a field in the sanitizer rules doesn't exist in the extracted data, it's skipped silently. If a transform produces `None` (e.g., `to_number` on a string with no numeric content), the remaining transforms in the chain are skipped for that field.

---

## Examples

### E-commerce price cleaner

```json
{
  "name": "Price Cleaner",
  "rules": [
    {
      "field": "price",
      "transforms": [
        { "type": "regex_replace", "pattern": "[^0-9.]", "replacement": "" },
        { "type": "to_number" }
      ]
    },
    {
      "field": "original_price",
      "transforms": [
        { "type": "extract_number" }
      ]
    }
  ]
}
```

**Input:** `{ "price": "$1,299.00 USD", "original_price": "was $1,599.00" }`
**Output:** `{ "price": 1299.0, "original_price": 1599.0 }`

### Title and category normalizer

```json
{
  "name": "Title Normalizer",
  "rules": [
    {
      "field": "title",
      "transforms": [
        { "type": "strip" },
        { "type": "regex_replace", "pattern": "\\s+", "replacement": " " },
        { "type": "to_lower" }
      ]
    },
    {
      "field": "category",
      "transforms": [
        { "type": "trim_prefix", "value": "Category: " },
        { "type": "to_lower" }
      ]
    }
  ]
}
```

**Input:** `{ "title": "  iPhone   15 Pro  ", "category": "Category: Electronics" }`
**Output:** `{ "title": "iphone 15 pro", "category": "electronics" }`

### URL segment extractor with defaults

```json
{
  "name": "URL Segment Extractor",
  "rules": [
    {
      "field": "slug",
      "transforms": [
        { "type": "split_take", "pattern": "/", "index": -1 }
      ]
    },
    {
      "field": "availability",
      "transforms": [
        { "type": "strip" },
        { "type": "to_lower" },
        { "type": "default", "value": "unknown" }
      ]
    }
  ]
}
```

**Input:** `{ "slug": "https://store.com/products/phone", "availability": "" }`
**Output:** `{ "slug": "phone", "availability": "unknown" }`

### Stock status normalizer

```json
{
  "name": "Stock Status",
  "rules": [
    {
      "field": "stock",
      "transforms": [
        { "type": "strip" },
        { "type": "to_lower" },
        { "type": "regex_replace", "pattern": "in stock|available", "replacement": "available" },
        { "type": "regex_replace", "pattern": "out of stock|unavailable|sold out", "replacement": "unavailable" }
      ]
    }
  ]
}
```

**Input:** `{ "stock": "  In Stock  " }`
**Output:** `{ "stock": "available" }`

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/sanitizer-configs/` | Create a sanitizer config |
| `GET` | `/api/v1/sanitizer-configs/` | List all sanitizer configs (`?active_only=true`) |
| `GET` | `/api/v1/sanitizer-configs/{id}` | Get sanitizer config by ID |
| `PATCH` | `/api/v1/sanitizer-configs/{id}` | Partially update a sanitizer config |
| `DELETE` | `/api/v1/sanitizer-configs/{id}` | Delete a sanitizer config |
| `POST` | `/api/v1/ai/suggest-sanitizer` | AI-generate sanitizer rules from URL + extraction spec |