"""HTML sanitizer for AI/LLM consumption.

Strips non-semantic tags (scripts, styles, nav, etc.) and bloat
attributes while preserving ``class``, ``id``, and ``data-*``
attributes that are essential for generating CSS selectors.

Uses only the stdlib ``html.parser`` — no additional dependencies
required in the API container.
"""

from __future__ import annotations

import html.parser
import re


class _HTMLStripper(html.parser.HTMLParser):
    """SAX-style HTML sanitizer.

    Tags in ``STRIP_TAGS`` (and their entire subtree) are removed.
    Attributes not in ``PRESERVE_ATTRS`` (and not ``data-*``) are
    stripped from surviving tags.
    """

    STRIP_TAGS: frozenset[str] = frozenset(
        {
            "script",
            "style",
            "nav",
            "footer",
            "header",
            "noscript",
            "iframe",
            "svg",
        }
    )

    PRESERVE_ATTRS: frozenset[str] = frozenset(
        {"class", "id", "href", "src", "alt", "type", "name", "role"}
    )

    def __init__(self) -> None:
        super().__init__()
        self._result: list[str] = []
        self._skip_depth: int = 0
        self._skip_tag: str | None = None

    # ── Tag events ──────────────────────────────────────────────

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:  # noqa: N802
        if self._skip_depth > 0:
            if tag == self._skip_tag:
                self._skip_depth += 1
            return

        if tag in self.STRIP_TAGS:
            self._skip_depth = 1
            self._skip_tag = tag
            return

        filtered: list[tuple[str, str]] = []
        for key, value in attrs:
            if value is None:
                continue
            if key in self.PRESERVE_ATTRS or key.startswith("data-"):
                filtered.append((key, value))

        attr_str = "".join(f' {k}="{value}"' for k, value in filtered)
        self._result.append(f"<{tag}{attr_str}>")

    def handle_endtag(self, tag: str) -> None:  # noqa: N802
        if self._skip_depth > 0:
            if tag == self._skip_tag:
                self._skip_depth -= 1
            return
        self._result.append(f"</{tag}>")

    def handle_data(self, data: str) -> None:  # noqa: N802
        if self._skip_depth > 0:
            return
        self._result.append(data)

    def handle_comment(self, data: str) -> None:  # noqa: N802, ARG002
        # Discard all HTML comments
        pass

    # ── Result ──────────────────────────────────────────────────

    def get_result(self) -> str:
        """Return the sanitized HTML string."""
        return "".join(self._result)


def sanitize_html(html: str) -> str:
    """Sanitize HTML for LLM consumption.

    * Strips ``<script>``, ``<style>``, ``<nav>``, ``<footer>``,
      ``<header>``, ``<noscript>``, ``<iframe>``, ``<svg>`` and
      their contents.
    * Preserves ``class``, ``id``, ``data-*`` and other
      selector-relevant attributes.
    * Removes HTML comments.
    * Collapses excessive whitespace.
    """
    stripper = _HTMLStripper()
    stripper.feed(html)
    result = stripper.get_result()

    # Collapse 3+ newlines into 2
    result = re.sub(r"\n{3,}", "\n\n", result)
    # Collapse 2+ spaces/tabs into 1
    result = re.sub(r"[ \t]{2,}", " ", result)

    return result.strip()