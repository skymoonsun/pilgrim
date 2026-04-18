"""Config-driven data extraction from Scrapling responses.

The ``extraction_spec`` JSONB stored in ``CrawlConfiguration`` defines
*what* to extract.  This module interprets that spec against a fetched
page.

## Spec format (example)

```json
{
  "fields": {
    "title": {"selector": "h1.product-title::text", "type": "css"},
    "price": {"selector": "//span[@class='price']/text()", "type": "xpath"},
    "images": {"selector": "img.gallery::attr(src)", "type": "css", "multiple": true},
    "formatted_price": {"selector": "props.pageProps.product.prices[0].formattedPrice", "type": "json_path", "source": "next_data"}
  }
}
```

* ``selector`` — CSS, XPath, or JSON path expression
* ``type`` — ``"css"`` (default), ``"xpath"``, or ``"json_path"``
* ``source`` — for ``json_path`` type: ``"next_data"`` or ``"json_ld"``
  (which embedded data source to resolve against)
* ``multiple`` — if ``true`` return a list; otherwise first match only

## CSS pseudo-elements

Scrapling (like Scrapy) supports ``::text`` and ``::attr(name)`` pseudo-elements:

* ``h1::text`` — extracts the text content of the matched element
* ``a::attr(href)`` — extracts the ``href`` attribute
* Without a pseudo-element, ``.css(selector).get()`` returns the element's
  outer HTML — almost never what you want.

**Auto-normalisation**: if a CSS selector does **not** end with ``::text`` or
``::attr(...)``, the extraction engine automatically appends ``::text`` so
that text content is returned instead of raw HTML.  XPath selectors are
left unchanged (the caller is expected to include ``/text()`` explicitly).

## JSON path extraction

For React/Next.js sites where product data is embedded in
``<script id="__NEXT_DATA__">`` or JSON-LD, the ``json_path`` type
resolves a dot-notation path (e.g. ``props.pageProps.product.prices[0].formattedPrice``)
against the extracted structured data.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Literal


def _resolve_json_path(data: Any, path: str) -> Any:
    """Resolve a dot-notation JSON path against a nested dict/list.

    Supports keys and array indices:
    - ``props.pageProps.product.name``
    - ``props.pageProps.product.prices[0].formattedPrice``
    - ``items[2].offers[0].price``

    Returns ``None`` if the path cannot be fully resolved.
    """
    if data is None:
        return None

    # Tokenize: split on dots, but handle array indices like [0]
    tokens: list[str | int] = []
    for part in path.split("."):
        # Check for array index suffix: key[0] or bare [0]
        bracket_match = re.match(r"^(.*?)\[(\d+)\]$", part)
        if bracket_match:
            key, idx = bracket_match.group(1), int(bracket_match.group(2))
            if key:
                tokens.append(key)
            tokens.append(idx)
        else:
            tokens.append(part)

    current = data
    for token in tokens:
        if current is None:
            return None
        if isinstance(token, int):
            if isinstance(current, list) and 0 <= token < len(current):
                current = current[token]
            else:
                return None
        elif isinstance(current, dict):
            current = current.get(token)
        else:
            return None

    return current

logger = logging.getLogger(__name__)

# Regex to detect ::text or ::attr(...) at the end of a CSS selector
_CSS_PSEUDO_RE = re.compile(r"::(?:text|attr\([^)]+\))\s*$")

# Regex to detect HTML tags in extracted values
_HTML_TAG_RE = re.compile(r"<[a-zA-Z/]")


def _normalise_css_selector(selector: str) -> str:
    """Append ``::text`` to a CSS selector that lacks a pseudo-element.

    Without a trailing ``::text`` or ``::attr(...)`` pseudo-element,
    Scrapling's ``.css(selector).get()`` returns the element's outer HTML.
    Almost every extraction field wants the *text content*, so we default
    to ``::text`` automatically.  Callers who need raw HTML can explicitly
    end their selector with something like ``::outer-html`` (not a real
    pseudo-element — it will simply be left alone).
    """
    if _CSS_PSEUDO_RE.search(selector):
        return selector
    return f"{selector}::text"


def assess_value_quality(value: Any) -> Literal["good", "html", "empty", "none"]:
    """Assess the quality of an extracted value.

    Returns
    -------
    "good"
        Clean text or attribute value.
    "html"
        Value contains HTML tags — likely a bare element selector
        that should use ``::text`` or ``::attr()``.
    "empty"
        Value is an empty string.
    "none"
        No value was extracted (None or empty list).
    """
    if value is None:
        return "none"
    if isinstance(value, list):
        if not value:
            return "none"
        # Check first item for HTML
        first = str(value[0])
        if _HTML_TAG_RE.search(first):
            return "html"
        if not first.strip():
            return "empty"
        return "good"
    str_val = str(value)
    if not str_val.strip():
        return "empty"
    if _HTML_TAG_RE.search(str_val):
        return "html"
    return "good"


@dataclass
class FieldResult:
    """Per-field extraction result with metadata."""

    field_name: str
    selector: str
    selector_type: str  # "css" or "xpath"
    multiple: bool
    matched: bool  # True if at least one element matched
    match_count: int  # Number of elements matched
    value: Any  # The extracted value (None for failed single, [] for failed multiple)
    sample: str | None  # First extracted value truncated for display


def extract_data(
    response: Any,
    extraction_spec: dict,
    next_data: dict | None = None,
    json_ld: list[dict] | None = None,
) -> dict[str, Any]:
    """Apply *extraction_spec* to a Scrapling *response*.

    Returns a flat dict mapping field names to extracted values.

    Parameters
    ----------
    response
        Scrapling response object (supports ``.css()`` and ``.xpath()``).
    extraction_spec
        The extraction specification dict.
    next_data
        Parsed ``__NEXT_DATA__`` JSON for ``json_path`` resolution.
    json_ld
        List of JSON-LD dicts for ``json_path`` resolution.
    """
    fields: dict[str, dict] = extraction_spec.get("fields", {})
    if not fields:
        logger.warning("extraction_spec has no 'fields' key — returning empty dict")
        return {}

    result: dict[str, Any] = {}

    for field_name, spec in fields.items():
        selector = spec.get("selector", "")
        selector_type = spec.get("type", "css")
        multiple = spec.get("multiple", False)

        try:
            if selector_type == "json_path":
                source = spec.get("source", "next_data")
                if source == "next_data":
                    source_data = next_data
                elif source == "json_ld":
                    # For JSON-LD, use the first item (or merge list)
                    source_data = json_ld[0] if json_ld else None
                else:
                    source_data = next_data

                resolved = _resolve_json_path(source_data, selector)
                if multiple and not isinstance(resolved, list):
                    result[field_name] = [resolved] if resolved is not None else []
                elif not multiple and isinstance(resolved, list):
                    result[field_name] = resolved[0] if resolved else None
                else:
                    result[field_name] = resolved
            elif selector_type == "xpath":
                selected = response.xpath(selector)
                if multiple:
                    result[field_name] = selected.getall() if selected else []
                else:
                    result[field_name] = selected.get() if selected else None
            else:
                effective_selector = _normalise_css_selector(selector)
                selected = response.css(effective_selector)
                if multiple:
                    result[field_name] = selected.getall() if selected else []
                else:
                    result[field_name] = selected.get() if selected else None

        except Exception as exc:
            logger.error(
                "Extraction error for field '%s' (selector='%s'): %s",
                field_name,
                selector,
                exc,
            )
            result[field_name] = None

    return result


def extract_data_with_metadata(
    response: Any,
    extraction_spec: dict,
    sample_max_length: int = 200,
    next_data: dict | None = None,
    json_ld: list[dict] | None = None,
) -> list[FieldResult]:
    """Apply *extraction_spec* to a Scrapling *response*, returning
    per-field metadata alongside the raw values.

    This is the verification counterpart to ``extract_data()``:
    instead of a flat ``{name: value}`` dict, it returns a list of
    ``FieldResult`` objects that indicate whether each selector matched,
    how many elements it found, and a sample of the extracted text.

    Parameters
    ----------
    response
        Scrapling response object.
    extraction_spec
        The extraction specification dict.
    sample_max_length
        Max chars for sample values.
    next_data
        Parsed ``__NEXT_DATA__`` JSON for ``json_path`` resolution.
    json_ld
        List of JSON-LD dicts for ``json_path`` resolution.
    """
    fields: dict[str, dict] = extraction_spec.get("fields", {})
    if not fields:
        logger.warning("extraction_spec has no 'fields' key")
        return []

    results: list[FieldResult] = []

    for field_name, spec in fields.items():
        selector = spec.get("selector", "")
        selector_type = spec.get("type", "css")
        multiple = spec.get("multiple", False)

        try:
            if selector_type == "json_path":
                source = spec.get("source", "next_data")
                if source == "next_data":
                    source_data = next_data
                elif source == "json_ld":
                    source_data = json_ld[0] if json_ld else None
                else:
                    source_data = next_data

                resolved = _resolve_json_path(source_data, selector)

                if multiple:
                    if isinstance(resolved, list):
                        values = resolved
                    elif resolved is not None:
                        values = [resolved]
                    else:
                        values = []
                    match_count = len(values)
                    matched = match_count > 0
                    raw_value: Any = values
                    sample = str(values[0])[:sample_max_length] if values else None
                else:
                    if isinstance(resolved, list):
                        val = resolved[0] if resolved else None
                    else:
                        val = resolved
                    matched = val is not None
                    match_count = 1 if matched else 0
                    raw_value = val
                    sample = str(val)[:sample_max_length] if val is not None else None

            elif selector_type == "xpath":
                selected = response.xpath(selector)
                if multiple:
                    values = selected.getall() if selected else []
                    match_count = len(values)
                    matched = match_count > 0
                    raw_value = values
                    sample = str(values[0])[:sample_max_length] if values else None
                else:
                    val = selected.get() if selected else None
                    matched = val is not None
                    match_count = 1 if matched else 0
                    raw_value = val
                    sample = str(val)[:sample_max_length] if val is not None else None

            else:
                effective_selector = _normalise_css_selector(selector)
                selected = response.css(effective_selector)
                if multiple:
                    values = selected.getall() if selected else []
                    match_count = len(values)
                    matched = match_count > 0
                    raw_value = values
                    sample = str(values[0])[:sample_max_length] if values else None
                else:
                    val = selected.get() if selected else None
                    matched = val is not None
                    match_count = 1 if matched else 0
                    raw_value = val
                    sample = str(val)[:sample_max_length] if val is not None else None

        except Exception as exc:
            logger.error(
                "Extraction error for field '%s' (selector='%s'): %s",
                field_name,
                selector,
                exc,
            )
            matched = False
            match_count = 0
            raw_value = None if not multiple else []
            sample = None

        results.append(FieldResult(
            field_name=field_name,
            selector=selector,
            selector_type=selector_type,
            multiple=multiple,
            matched=matched,
            match_count=match_count,
            value=raw_value,
            sample=sample,
        ))

    return results
