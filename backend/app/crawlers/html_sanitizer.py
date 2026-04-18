"""Smart HTML sanitizer for AI/LLM consumption.

Strips bloat (scripts, styles, nav, forms, ads, cross-sell, cookie banners,
etc.) and extracts JSON-LD structured data before sanitization. Uses
``lxml.html`` for tree-based processing — no new dependencies required.

The main entry point is :func:`sanitize_html` which returns a
:dataclass:`SanitizeResult` containing both the cleaned HTML and any
JSON-LD structured data found on the page.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

from lxml import html as lxml_html

logger = logging.getLogger(__name__)

# ── Tags whose entire subtree is removed ──────────────────────────

STRIP_TAGS: frozenset[str] = frozenset(
    {
        # Existing
        "script",
        "style",
        "nav",
        "footer",
        "header",
        "noscript",
        "iframe",
        "svg",
        # New — low extraction value for LLM spec generation
        "aside",
        "form",
        "button",
        "input",
        "select",
        "textarea",
        "label",
        "fieldset",
        "dialog",
        "canvas",
        "audio",
        "video",
        "embed",
        "object",
        "applet",
        "map",
        "area",
        "details",
        "summary",
    }
)

# ── Block-level tags for smart truncation ────────────────────────

BLOCK_TAGS: frozenset[str] = frozenset(
    {
        "div",
        "p",
        "section",
        "article",
        "main",
        "aside",
        "header",
        "footer",
        "nav",
        "table",
        "tr",
        "td",
        "th",
        "ul",
        "ol",
        "li",
        "dl",
        "dt",
        "dd",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
        "blockquote",
        "pre",
        "figure",
        "figcaption",
        "hr",
        "br",
    }
)

# ── Attributes preserved on surviving tags ───────────────────────

PRESERVE_ATTRS: frozenset[str] = frozenset(
    {"class", "id", "href", "src", "alt", "type", "name", "role", "itemprop"}
)

# ── Negative class/ID patterns — entire subtree removed ─────────
# Elements whose class or id matches any of these regexes are
# stripped along with their entire subtree.

NEGATIVE_PATTERNS: list[re.Pattern[str]] = [
    # Cookie / consent / GDPR
    re.compile(r"cookie", re.I),
    re.compile(r"consent", re.I),
    re.compile(r"gdpr", re.I),
    re.compile(r"privacy.?banner", re.I),
    re.compile(r"privacy.?policy", re.I),
    # Ads / promos / sponsors
    re.compile(r"-ad-", re.I),
    re.compile(r"\bad[s_]?\b", re.I),
    re.compile(r"advert", re.I),
    re.compile(r"promo", re.I),
    re.compile(r"sponsor", re.I),
    re.compile(r"outbrain", re.I),
    # Cross-sell / recommendations
    re.compile(r"recommend", re.I),
    re.compile(r"related.?product", re.I),
    re.compile(r"cross.?sell", re.I),
    re.compile(r"upsell", re.I),
    re.compile(r"you.?may.?also", re.I),
    re.compile(r"similar.?product", re.I),
    re.compile(r"also.?viewed", re.I),
    re.compile(r"also.?bought", re.I),
    re.compile(r"frequently.?bought", re.I),
    re.compile(r"customer.?also", re.I),
    # Social / share
    re.compile(r"\bshare[s]?\b", re.I),
    re.compile(r"\bsocial\b", re.I),
    re.compile(r"shoutbox", re.I),
    # Navigation / sidebar
    re.compile(r"\bsidebar\b", re.I),
    re.compile(r"skyscraper", re.I),
    re.compile(r"\bmenu\b", re.I),
    # Comments
    re.compile(r"\bcomment", re.I),
    re.compile(r"disqus", re.I),
    re.compile(r"yorum", re.I),  # Turkish: "comments"
    # Turkish e-commerce bloat
    re.compile(r"\bbenzer\b", re.I),  # "similar"
    re.compile(r"\boneri\b", re.I),  # "recommendation"
    re.compile(r"\bilgili\b", re.I),  # "related"
    re.compile(r"cok.?satan", re.I),  # "bestseller"
    re.compile(r"birlikte.?alin", re.I),  # "bought together"
    re.compile(r"\bkampanya\b", re.I),  # "campaign"
    # Misc bloat
    re.compile(r"\bbanner\b", re.I),
    re.compile(r"\bpopup\b", re.I),
    re.compile(r"newsletter", re.I),
    re.compile(r"subscribe", re.I),
    re.compile(r"mailing.?list", re.I),
    re.compile(r"recently.?viewed", re.I),
    re.compile(r"recently.?view", re.I),
    re.compile(r"wish.?list", re.I),
    re.compile(r"live.?chat", re.I),
    re.compile(r"chat.?widget", re.I),
    re.compile(r"\bsticky\b", re.I),
    re.compile(r"\bfloating\b", re.I),
    re.compile(r"breadcrumb", re.I),
    re.compile(r"pagination", re.I),
    re.compile(r"\bpager\b", re.I),
]

# ── ARIA roles that signal non-content ──────────────────────────

UNLIKELY_ROLES: frozenset[str] = frozenset(
    {
        "menu",
        "menubar",
        "complementary",
        "navigation",
        "alert",
        "alertdialog",
        "dialog",
    }
)

# ── Result dataclass ─────────────────────────────────────────────


@dataclass
class SanitizeResult:
    """Result of HTML sanitization for LLM consumption."""

    html: str
    json_ld: list[dict] = field(default_factory=list)
    next_data: dict | None = None
    original_length: int = 0
    sanitized_length: int = 0


# ── JSON-LD extraction ───────────────────────────────────────────


# JSON-LD types worth keeping for selector generation — drop the rest
_USEFUL_JSON_LD_TYPES: frozenset[str] = frozenset(
    {
        "Product",
        "Offer",
        "AggregateOffer",
        "ItemPage",
        "WebPage",
        "BreadcrumbList",
        "ItemList",
    }
)


def _extract_json_ld(tree: lxml_html.HtmlElement) -> list[dict]:
    """Extract useful JSON-LD structured data from ``<script type="application/ld+json">`` tags.

    Only keeps types in ``_USEFUL_JSON_LD_TYPES`` (Product, Offer, etc.)
    to avoid flooding the LLM context with Review data.
    """
    results: list[dict] = []
    for script in tree.iter("script"):
        script_type = script.get("type", "")
        if script_type.lower() != "application/ld+json":
            continue
        text = script.text_content()
        if not text or not text.strip():
            continue
        try:
            data = json.loads(text)
            if isinstance(data, list):
                for item in data:
                    if _is_useful_json_ld(item):
                        results.append(item)
            else:
                if _is_useful_json_ld(data):
                    results.append(data)
        except (json.JSONDecodeError, TypeError):
            continue
    return results


def _is_useful_json_ld(data: dict) -> bool:
    """Check if a JSON-LD item is useful for extraction spec generation."""
    ld_type = data.get("@type", "")
    if isinstance(ld_type, list):
        return any(t in _USEFUL_JSON_LD_TYPES for t in ld_type)
    return ld_type in _USEFUL_JSON_LD_TYPES


# ── Next.js __NEXT_DATA__ / Redux Store extraction ────────────────────

# Script tag IDs that contain embedded product data (JSON)
_EMBEDDED_DATA_IDS: frozenset[str] = frozenset(
    {
        "__NEXT_DATA__",  # Next.js
        "reduxStore",  # Hepsiburada / React-Redux
        "__APP_DATA__",  # Some Next.js variants
    }
)

# Key names that signal product-relevant data inside embedded JSON
_PRODUCT_DATA_KEYS: frozenset[str] = frozenset(
    {
        "formattedPrice",
        "price",
        "value",
        "currency",
        "name",
        "productName",
        "title",
        "availability",
        "stock",
        "inStock",
        "sku",
        "brand",
        "imageUrl",
        "variantName",
        "discountRate",
        "originalPrice",
        "sellingPrice",
    }
)


def _extract_next_data(tree: lxml_html.HtmlElement) -> dict | None:
    """Extract embedded JSON data from known script tag IDs.

    Checks for ``__NEXT_DATA__``, ``reduxStore``, and other known IDs
    that e-commerce sites use to embed product data. Returns the first
    valid JSON found, or None.
    """
    for script in tree.iter("script"):
        script_id = script.get("id", "")
        if script_id not in _EMBEDDED_DATA_IDS:
            continue
        text = script.text_content()
        if not text or not text.strip():
            continue
        try:
            data = json.loads(text)
            return data
        except (json.JSONDecodeError, TypeError):
            continue
    return None


def _extract_product_data_from_next(next_data: dict, max_chars: int = 5000) -> str:
    """Extract product-relevant data from an embedded JSON payload.

    Walks the JSON looking for keys like ``formattedPrice``, ``price``,
    ``name``, ``availability``, etc.  Returns a compact summary string
    suitable for LLM context.  Works with ``__NEXT_DATA__``, ``reduxStore``,
    and other embedded JSON sources.
    """
    if not next_data:
        return ""

    target_keys = _PRODUCT_DATA_KEYS

    results: list[str] = []

    def _walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k in target_keys:
                    results.append(f"{path}.{k}: {v!r}")
                _walk(v, f"{path}.{k}")
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                _walk(item, f"{path}[{i}]")

    _walk(next_data)
    output = "\n".join(results)
    if len(output) > max_chars:
        output = output[:max_chars] + "...(truncated)"
    return output


# ── Negative pattern matching ───────────────────────────────────


def _matches_negative_pattern(class_attr: str | None, id_attr: str | None) -> bool:
    """Check if an element's class or id matches any negative pattern."""
    combined = ""
    if class_attr:
        combined += " " + class_attr
    if id_attr:
        combined += " " + id_attr
    if not combined.strip():
        return False
    for pattern in NEGATIVE_PATTERNS:
        if pattern.search(combined):
            return True
    return False


def _matches_unlikely_role(element: lxml_html.HtmlElement) -> bool:
    """Check if an element has an unlikely ARIA role."""
    role = element.get("role", "")
    return role in UNLIKELY_ROLES


# ── Core sanitization ────────────────────────────────────────────


def _remove_bloat(tree: lxml_html.HtmlElement) -> None:
    """Remove strip-tags, negative-pattern elements, and unlikely-role elements."""
    # Collect elements to remove (can't modify tree while iterating)
    to_remove: list[lxml_html.HtmlElement] = []

    for element in tree.iter():
        if not isinstance(element, lxml_html.HtmlElement):
            continue

        # 1. Strip by tag name
        if element.tag in STRIP_TAGS:
            to_remove.append(element)
            continue

        # 2. Strip by class/id negative patterns
        class_attr = element.get("class", "")
        id_attr = element.get("id", "")
        if _matches_negative_pattern(class_attr, id_attr):
            to_remove.append(element)
            continue

        # 3. Strip by unlikely ARIA role
        if _matches_unlikely_role(element):
            to_remove.append(element)
            continue

    for element in to_remove:
        parent = element.getparent()
        if parent is not None:
            # Preserve tail text (text after the closing tag)
            if element.tail:
                prev = element.getprevious()
                if prev is not None:
                    prev.tail = (prev.tail or "") + element.tail
                else:
                    parent.text = (parent.text or "") + element.tail
            parent.remove(element)


# Tags that act as wrappers with no semantic value — safe to prune
# if they contain only other wrappers and very little text.
_WRAPPER_TAGS: frozenset[str] = frozenset({"div", "span", "section"})


def _prune_wrapper_divs(tree: lxml_html.HtmlElement, max_text_ratio: float = 0.15) -> None:
    """Remove deep wrapper ``<div>``/``<span>``/``<section>`` trees that
    carry almost no text content.

    Walks the tree bottom-up.  A wrapper element whose text-to-tag
    ratio is below *max_text_ratio* (text chars / total serialized
    length < 0.15) is a candidate for pruning.

    Elements with ``class`` or ``id`` are kept because they may carry
    selector-relevant names.  However, if the class matches a known
    decorative pattern (layout, container, wrapper), the element is
    pruned regardless.
    """
    # Class patterns that signal decorative wrappers (not selector targets)
    _DECORATIVE_CLASS_PATTERNS = [
        re.compile(r"\bwrapper\b", re.I),
        re.compile(r"\bcontainer\b", re.I),
        re.compile(r"\blayout\b", re.I),
        re.compile(r"\brow\b", re.I),
        re.compile(r"\bcol(?:umn)?s?\b", re.I),
        re.compile(r"\bflex\b", re.I),
        re.compile(r"\bgrid\b", re.I),
        re.compile(r"\bwrap(?:per)?\b", re.I),
        re.compile(r"\binner\b", re.I),
        re.compile(r"\bouter\b", re.I),
        re.compile(r"\bholder\b", re.I),
        re.compile(r"\bparent\b", re.I),
    ]

    def _is_decorative_class(class_attr: str) -> bool:
        return any(p.search(class_attr) for p in _DECORATIVE_CLASS_PATTERNS)

    # Bottom-up: process children before parents
    for element in reversed(list(tree.iter())):
        if not isinstance(element, lxml_html.HtmlElement):
            continue
        if element.tag not in _WRAPPER_TAGS:
            continue
        if element.getparent() is None:
            continue

        class_attr = element.get("class", "")
        has_id = bool(element.get("id"))
        has_data = any(k.startswith("data-") for k in element.attrib)

        # Keep elements with data-* attributes (likely product-specific)
        if has_data:
            continue

        # Keep elements with itemprop (schema.org microdata)
        if element.get("itemprop"):
            continue

        # Elements with NO class and NO id: prune if low text ratio
        if not class_attr and not has_id:
            text = element.text_content() or ""
            text_len = len(text.strip())
            total_len = len(lxml_html.tostring(element, encoding="unicode"))
            if total_len > 0 and text_len / total_len < max_text_ratio:
                _unwrap_element(element)
            continue

        # Elements with decorative class names: prune if low text ratio
        if class_attr and _is_decorative_class(class_attr):
            text = element.text_content() or ""
            text_len = len(text.strip())
            total_len = len(lxml_html.tostring(element, encoding="unicode"))
            if total_len > 0 and text_len / total_len < max_text_ratio:
                _unwrap_element(element)
            continue


def _unwrap_element(element: lxml_html.HtmlElement) -> None:
    """Replace an element with its children (unwrap), preserving tail text."""
    parent = element.getparent()
    if parent is None:
        return
    # Preserve tail text
    if element.tail:
        prev = element.getprevious()
        if prev is not None:
            prev.tail = (prev.tail or "") + element.tail
        else:
            parent.text = (parent.text or "") + element.tail
    # Move children up
    index = list(parent).index(element)
    for i, child in enumerate(list(element)):
        parent.insert(index + i, child)
    parent.remove(element)


def _remove_empty_elements(tree: lxml_html.HtmlElement) -> None:
    """Remove leaf elements that have no text content and no attributes.

    This cleans up leftover ``<div></div>``, ``<span></span>``, etc.
    after bloat removal.  Elements with attributes are kept because
    they may be selector targets.
    """
    # Multiple passes: removing one empty element may expose another
    for _ in range(3):
        to_remove: list[lxml_html.HtmlElement] = []
        for element in tree.iter():
            if not isinstance(element, lxml_html.HtmlElement):
                continue
            if element.tag not in _WRAPPER_TAGS:
                continue
            if element.getparent() is None:
                continue
            # Skip elements with any attributes
            if element.attrib:
                continue
            # Skip elements with children
            children = list(element)
            if children:
                continue
            # Skip elements with text content
            text = (element.text or "").strip()
            tail = (element.tail or "").strip()
            if text or tail:
                continue
            to_remove.append(element)

        if not to_remove:
            break
        for element in to_remove:
            parent = element.getparent()
            if parent is not None:
                # Preserve tail
                if element.tail:
                    prev = element.getprevious()
                    if prev is not None:
                        prev.tail = (prev.tail or "") + element.tail
                    else:
                        parent.text = (parent.text or "") + element.tail
                parent.remove(element)


def _strip_attributes(tree: lxml_html.HtmlElement) -> None:
    """Remove all attributes except the preserved set and data-*."""
    for element in tree.iter():
        if not isinstance(element, lxml_html.HtmlElement):
            continue
        attrs_to_remove = [
            attr
            for attr in element.attrib
            if attr not in PRESERVE_ATTRS and not attr.startswith("data-")
        ]
        for attr in attrs_to_remove:
            del element.attrib[attr]


def _collapse_whitespace(text: str) -> str:
    """Collapse excessive whitespace in sanitized HTML."""
    # Collapse 3+ newlines into 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Collapse 2+ spaces/tabs into 1
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ── Smart truncation ─────────────────────────────────────────────


def _truncate_html_smart(html: str, max_chars: int) -> str:
    """Truncate HTML at a safe block-level boundary within *max_chars*.

    Instead of slicing mid-tag, find the last complete closing block tag
    that fits within the budget.  This produces well-formed HTML snippets
    that the LLM can actually parse.
    """
    if len(html) <= max_chars:
        return html

    # Find the last closing block tag position within the budget
    last_safe_pos = max_chars
    best_cut = -1

    # Search backwards from max_chars for a closing block tag
    for i in range(min(max_chars, len(html)) - 1, max(max_chars - 500, 0), -1):
        if html[i] == ">" and i > 0:
            # Look back for </tagname>
            close_match = re.match(r"</(\w+)\s*>$", html[max(0, i - 50) : i + 1])
            if close_match:
                tag_name = close_match.group(1).lower()
                # Accept any closing tag as a safe cut point, but prefer blocks
                if tag_name in BLOCK_TAGS or tag_name in {"div", "section", "article", "main"}:
                    best_cut = i + 1
                    break

    # If no block tag found, fall back to any closing tag
    if best_cut == -1:
        for i in range(min(max_chars, len(html)) - 1, max(max_chars - 500, 0), -1):
            if html[i] == ">":
                best_cut = i + 1
                break

    if best_cut == -1:
        best_cut = max_chars

    return html[:best_cut]


# ── Public API ───────────────────────────────────────────────────


def sanitize_html(html: str) -> SanitizeResult:
    """Sanitize HTML for LLM consumption.

    * Extracts JSON-LD structured data from ``<script type="application/ld+json">``
      tags *before* stripping.
    * Strips bloat tags (scripts, styles, forms, nav, etc.) and their subtrees.
    * Removes elements whose class/id match negative patterns (ads, cross-sell,
      cookie banners, etc.).
    * Removes elements with unlikely ARIA roles (navigation, complementary, etc.).
    * Strips all attributes except class, id, href, src, alt, data-*, itemprop.
    * Collapses excessive whitespace.

    Returns a :class:`SanitizeResult` with the sanitized HTML, extracted JSON-LD,
    and size statistics.
    """
    original_length = len(html)

    # Parse with lxml
    tree = lxml_html.fromstring(html)

    # 1. Extract JSON-LD BEFORE removing script tags
    json_ld = _extract_json_ld(tree)

    # 1b. Extract __NEXT_DATA__ BEFORE removing script tags
    next_data = _extract_next_data(tree)

    # 2. Remove bloat elements
    _remove_bloat(tree)

    # 3. Prune deep wrapper div trees (div soup from React/Next.js)
    _prune_wrapper_divs(tree)

    # 4. Remove empty wrapper elements
    _remove_empty_elements(tree)

    # 5. Strip non-essential attributes
    _strip_attributes(tree)

    # 6. Serialize back to HTML
    sanitized = lxml_html.tostring(tree, encoding="unicode", method="html")

    # 7. Collapse whitespace
    sanitized = _collapse_whitespace(sanitized)

    return SanitizeResult(
        html=sanitized,
        json_ld=json_ld,
        next_data=next_data,
        original_length=original_length,
        sanitized_length=len(sanitized),
    )


def truncate_html(html: str, max_chars: int) -> str:
    """Truncate HTML at a safe block-level boundary.

    Delegates to :func:`_truncate_html_smart` which finds the last
    complete closing tag within *max_chars*.
    """
    return _truncate_html_smart(html, max_chars)