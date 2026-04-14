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
    "images": {"selector": "img.gallery::attr(src)", "type": "css", "multiple": true}
  }
}
```

* ``selector`` — CSS or XPath expression
* ``type`` — ``"css"`` (default) or ``"xpath"``
* ``multiple`` — if ``true`` return a list; otherwise first match only
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def extract_data(
    response: Any,
    extraction_spec: dict,
) -> dict[str, Any]:
    """Apply *extraction_spec* to a Scrapling *response*.

    Returns a flat dict mapping field names to extracted values.
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
            if selector_type == "xpath":
                selected = response.xpath(selector)
            else:
                selected = response.css(selector)

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
