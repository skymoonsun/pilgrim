"""Centralised LLM prompt templates for AI-powered features.

All prompts used by ``AIService`` live here so they can be reviewed,
tuned, and extended in a single place.

Each constant is a plain string.  ``{{…}}`` double-braces are used for
literal braces in JSON examples (Python ``str.format`` escapes).  Single
braces ``{name}`` are ``str.format`` placeholders filled at call time.

Available placeholders
----------------------
* ``description`` — natural-language description of what to extract
* ``html`` — sanitised / truncated HTML of the target page
* ``json_ld_context`` — JSON-LD structured data extracted from the page
  (empty string if none found)
* ``fields_description`` — human-readable list of all fields + their
  current extraction results
* ``failed_fields`` — human-readable list of fields that need fixing
  (with reasons and current values)
"""

from __future__ import annotations

# ── System prompt (shared across all AI calls) ───────────────────

SYSTEM_PROMPT = (
    "You are a web scraping expert. You MUST respond with ONLY valid JSON — "
    "no explanation, no markdown, no code fences, no conversational text. "
    "Your entire response must be a single JSON object that conforms to the "
    "schema provided. Never include any text before or after the JSON."
)

# ── Extraction spec generation ───────────────────────────────────

GENERATE_SPEC_PROMPT = """\
Given the following HTML from a web page, generate an extraction specification.
{json_ld_context}
The extraction spec must be a JSON object with this exact structure:
{{
  "fields": {{
    "<field_name>": {{
      "selector": "<CSS selector, XPath expression, or JSON path>",
      "type": "css" or "xpath" or "json_path",
      "multiple": true or false,
      "source": "next_data" or "json_ld"  (only for type: "json_path")
    }}
  }}
}}

Selector types:
- "css" (default): CSS selector with ::text or ::attr() pseudo-element
- "xpath": XPath 1.0 expression with /text() or /@attr
- "json_path": Dot-notation path into embedded JSON data (e.g. "productState.product.prices[0].formattedPrice")
  - Use "source": "next_data" for React/Redux embedded data
  - Use "source": "json_ld" for JSON-LD structured data

Rules:
- Use CSS selectors by default (type: "css"). Use XPath only when CSS cannot express the selection.
- Use "json_path" ONLY when the structured data section above contains the values you need and there are no matching visible DOM elements.
- If using XPath, only XPath 1.0 is supported. Do NOT use XPath 2.0+ functions like substring-before, substring-after, or tokenize.
- CRITICAL: CSS selectors MUST end with a pseudo-element to specify what to extract:
  - Append ::text to extract the text content of an element (e.g. "h1.title::text", ".price::text")
  - Append ::attr(name) to extract an attribute (e.g. "a.link::attr(href)", "img::attr(src)")
  - NEVER return a bare element selector like ".price" — always add ::text or ::attr(...)
  - For XPath, include /text() for text or /@attr for attributes as appropriate.
- Do NOT target <script> tags with CSS/XPath to extract data — their JSON content cannot be parsed by CSS/XPath selectors.
- Set "multiple": true when the field should capture all matching elements (e.g. list of prices, images).
- Keep selectors concise and robust — prefer semantic classes and IDs over deep DOM paths.
- Every field name must be a snake_case identifier.
- You MUST respond with ONLY the JSON object. No other text.

What to extract:
{description}

HTML:
{html}

JSON response:"""

# ── Extraction spec refinement (verification) ────────────────────

REFINE_SPEC_PROMPT = """\
Given the following HTML from a web page, fix the CSS/XPath selectors for the fields that need correction.
{json_ld_context}
The extraction spec has these fields (with their current extraction results):
{fields_description}

The following fields NEED FIXING:
{failed_fields}

Provide a complete extraction spec JSON with the "fields" key containing ONLY the fields
that need fixing with their corrected selectors. Do NOT include fields that already work correctly.

The response must be a JSON object with this exact structure:
{{
  "fields": {{
    "<field_name>": {{
      "selector": "<CSS selector, XPath expression, or JSON path>",
      "type": "css" or "xpath" or "json_path",
      "multiple": true or false,
      "source": "next_data" or "json_ld"  (only for type: "json_path")
    }}
  }}
}}

Selector types:
- "css" (default): CSS selector with ::text or ::attr() pseudo-element
- "xpath": XPath 1.0 expression with /text() or /@attr
- "json_path": Dot-notation path into embedded JSON data (e.g. "productState.product.prices[0].formattedPrice")
  - Use "source": "next_data" for React/Redux embedded data
  - Use "source": "json_ld" for JSON-LD structured data

Rules:
- Include ONLY the fields that need fixing in your response, with corrected selectors.
- Use CSS selectors by default (type: "css"). Use XPath only when CSS cannot express the selection.
- Use "json_path" ONLY when the structured data section above contains the values you need and there are no matching visible DOM elements.
- If using XPath, only XPath 1.0 is supported. Do NOT use XPath 2.0+ functions like substring-before, substring-after, or tokenize.
- CRITICAL: CSS selectors MUST end with a pseudo-element to specify what to extract:
  - Append ::text to extract the text content of an element (e.g. "h1.title::text", ".price::text")
  - Append ::attr(name) to extract an attribute (e.g. "a.link::attr(href)", "img::attr(src)")
  - NEVER return a bare element selector like ".price" — always add ::text or ::attr(...)
  - For XPath, include /text() for text or /@attr for attributes as appropriate.
- Do NOT target <script> tags with CSS/XPath to extract data — their JSON content cannot be parsed by CSS/XPath selectors.
- If a field currently extracts HTML instead of clean text, add ::text to the selector.
- If a field currently extracts nothing, try a different selector approach — especially check if the data is available via "json_path" in the embedded structured data.
- Keep selectors concise and robust — prefer semantic classes and IDs over deep DOM paths.
- If a field cannot be reliably extracted, set the selector to "" to indicate a deliberate skip.
- You MUST respond with ONLY the JSON object. No other text.

HTML:
{html}

JSON response:"""