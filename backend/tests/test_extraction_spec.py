"""Tests for the config-recipe interpreter: ``app.crawlers.extraction``.

The ``extraction_spec`` JSONB on a CrawlConfiguration is the recipe that
defines *what* to extract from a fetched page.  These tests lock in the
recipe-parsing semantics with a tiny Scrapling-like page double (lxml
under the hood — no Scrapling, no network):

- CSS selectors with ``::text`` / ``::attr(...)`` pseudo-elements, and
  auto-normalisation of bare CSS selectors to ``::text``.
- XPath selectors (callers supply ``/text()`` explicitly).
- ``json_path`` fields resolved against ``__NEXT_DATA__`` / JSON-LD.
- ``multiple`` list semantics and error isolation per field.
"""

import re
from typing import Any

from lxml import html as lxml_html  # type: ignore[import-untyped]

from app.crawlers.extraction import (
    _normalise_css_selector,
    _resolve_json_path,
    assess_value_quality,
    extract_data,
    extract_data_with_metadata,
)

_PSEUDO_RE = re.compile(r"::(?:text|attr\(([^)]+)\))\s*$")


# ── Scrapling-like page double ───────────────────────────────────────


class _FakeSelection:
    """Mimics Scrapling's selection container (``.get()`` / ``.getall()``)."""

    def __init__(self, values: list[str]) -> None:
        self._values = values

    def get(self) -> str | None:
        return self._values[0] if self._values else None

    def getall(self) -> list[str]:
        return list(self._values)


class _FakePage:
    """Minimal page double: ``.css()``/``.xpath()`` over an lxml tree."""

    def __init__(self, html: str) -> None:
        self._tree = lxml_html.fromstring(html)

    def css(self, selector: str) -> _FakeSelection:
        match = _PSEUDO_RE.search(selector)
        values: list[str]
        if match is None:
            elements = self._tree.cssselect(selector)
            values = [
                lxml_html.tostring(el, encoding="unicode") for el in elements
            ]
        elif selector[match.start():].strip() == "::text":
            elements = self._tree.cssselect(selector[: match.start()])
            values = ["".join(el.itertext()) for el in elements]
        else:
            attr_name = match.group(1)
            elements = self._tree.cssselect(selector[: match.start()])
            values = [
                attr for el in elements
                if (attr := el.get(attr_name)) is not None
            ]
        return _FakeSelection(values)

    def xpath(self, selector: str) -> _FakeSelection:
        nodes = self._tree.xpath(selector)
        values = [
            node if isinstance(node, str) else "".join(node.itertext())
            for node in nodes
        ]
        return _FakeSelection(values)


_PAGE_HTML = """
<html>
  <body>
    <h1 class="title">Widget</h1>
    <span class="price">129.90</span>
    <img class="gallery" src="img1.png">
    <img class="gallery" src="img2.png">
    <a class="next" href="/page2">Next</a>
  </body>
</html>
"""


def _title_page() -> _FakePage:
    return _FakePage(_PAGE_HTML)


# ── JSON path resolver ───────────────────────────────────────────────


class TestResolveJsonPath:
    def test_resolves_nested_keys(self) -> None:
        data = {"props": {"pageProps": {"product": {"name": "Widget"}}}}
        assert (
            _resolve_json_path(data, "props.pageProps.product.name")
            == "Widget"
        )

    def test_resolves_array_indices(self) -> None:
        data = {"prices": [{"formattedPrice": "129.90"}, {"value": 1}]}
        assert (
            _resolve_json_path(data, "prices[0].formattedPrice") == "129.90"
        )
        assert (
            _resolve_json_path(data, "prices[1].value") == 1
        )

    def test_bare_index_token(self) -> None:
        assert _resolve_json_path({"props": [10, 20]}, "props") == [10, 20]
        assert _resolve_json_path([10, 20], "[0]") == 10

    def test_missing_keys_return_none(self) -> None:
        data: dict[str, Any] = {"props": {"pageProps": {}}}
        assert (
            _resolve_json_path(data, "props.pageProps.product.name") is None
        )
        assert _resolve_json_path(data, "nope.deeper") is None

    def test_out_of_range_and_non_list_indices(self) -> None:
        assert _resolve_json_path({"prices": []}, "prices[0].value") is None
        assert _resolve_json_path({"not_a_list": 3}, "not_a_list[0]") is None

    def test_traverse_through_non_dict_returns_none(self) -> None:
        assert _resolve_json_path({"a": 42}, "a.b") is None

    def test_none_input_and_root_none(self) -> None:
        assert _resolve_json_path(None, "anything") is None
        assert _resolve_json_path({"a": None}, "a") is None


# ── CSS selector normalisation ───────────────────────────────────────


class TestNormaliseCssSelector:
    def test_appends_text_to_bare_selector(self) -> None:
        assert _normalise_css_selector("h1.title") == "h1.title::text"

    def test_keeps_explicit_text(self) -> None:
        assert (
            _normalise_css_selector("h1.title::text") == "h1.title::text"
        )

    def test_keeps_explicit_attr(self) -> None:
        assert (
            _normalise_css_selector("a.next::attr(href)")
            == "a.next::attr(href)"
        )


# ── Value quality assessment ─────────────────────────────────────────


class TestAssessValueQuality:
    def test_good_values(self) -> None:
        assert assess_value_quality("Widget") == "good"
        assert assess_value_quality(["a", "b"]) == "good"

    def test_empty_and_none(self) -> None:
        assert assess_value_quality(None) == "none"
        assert assess_value_quality([]) == "none"
        assert assess_value_quality("") == "empty"
        assert assess_value_quality("   ") == "empty"
        assert assess_value_quality(["  "]) == "empty"

    def test_html_values_flagged(self) -> None:
        assert assess_value_quality("<h1>Widget</h1>") == "html"
        assert assess_value_quality(["<img src='x'>"]) == "html"


# ── extract_data (recipe interpreter) ────────────────────────────────


class TestExtractDataCss:
    def test_css_text_and_attr(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {
                "title": {"selector": "h1.title::text", "type": "css"},
                "link": {"selector": "a.next::attr(href)", "type": "css"},
            }},
        )
        assert result == {"title": "Widget", "link": "/page2"}

    def test_bare_css_selector_normalised_to_text(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {"title": {"selector": "h1.title"}}},
        )
        # Locks the documented auto-normalisation: no outer HTML leakage.
        assert result == {"title": "Widget"}

    def test_multiple_returns_list(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {
                "images": {
                    "selector": "img.gallery::attr(src)",
                    "type": "css",
                    "multiple": True,
                },
            }},
        )
        assert result == {"images": ["img1.png", "img2.png"]}

    def test_multiple_no_match_returns_empty_list(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {
                "ghost": {"selector": ".missing::text",
                          "type": "css", "multiple": True},
            }},
        )
        assert result == {"ghost": []}

    def test_single_no_match_returns_none(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {
                "ghost": {"selector": ".missing::text", "type": "css"},
            }},
        )
        assert result == {"ghost": None}


class TestExtractDataXPath:
    def test_xpath_explicit_text(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {
                "price": {
                    "selector": "//span[@class='price']/text()",
                    "type": "xpath",
                },
            }},
        )
        assert result == {"price": "129.90"}

    def test_xpath_multiple(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {
                "prices": {
                    "selector": "//span[@class='price']/text()",
                    "type": "xpath",
                    "multiple": True,
                },
            }},
        )
        assert result == {"prices": ["129.90"]}

    def test_unknown_source_type_falls_back_to_css(self) -> None:
        # "weird" is neither xpath nor json_path → treated as CSS.
        result = extract_data(
            _title_page(),
            {"fields": {
                "title": {
                    "selector": "h1.title::text", "type": "weird",
                },
            }},
        )
        assert result == {"title": "Widget"}


class TestExtractDataJsonPath:
    def _next_data(self) -> dict[str, Any]:
        return {"props": {"pageProps": {"product": {
            "name": "Widget",
            "prices": [{"formattedPrice": "129.90"}],
        }}}}

    def test_resolves_against_next_data(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "price": {
                    "selector": (
                        "props.pageProps.product.prices"
                        "[0].formattedPrice"
                    ),
                    "type": "json_path",
                    "source": "next_data",
                },
            }},
            next_data=self._next_data(),
        )
        assert result == {"price": "129.90"}

    def test_single_selects_first_of_list(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "name": {
                    "selector": "props.pageProps.product.name",
                    "type": "json_path",
                },
            }},
            next_data=self._next_data(),
        )
        assert result == {"name": "Widget"}

    def test_multiple_false_coerces_list_to_first(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "prices": {
                    "selector": "props.pageProps.product.prices",
                    "type": "json_path",
                },
            }},
            next_data=self._next_data(),
        )
        assert result == {"prices": {"formattedPrice": "129.90"}}

    def test_multiple_scalar_wrapped_in_list(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "name": {
                    "selector": "props.pageProps.product.name",
                    "type": "json_path",
                    "multiple": True,
                },
            }},
            next_data=self._next_data(),
        )
        assert result == {"name": ["Widget"]}

    def test_multiple_missing_returns_empty_list(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "name": {
                    "selector": "props.pageProps.missing.deeper",
                    "type": "json_path",
                    "multiple": True,
                },
            }},
            next_data=self._next_data(),
        )
        assert result == {"name": []}

    def test_json_ld_source_uses_first_item(self) -> None:
        json_ld = [{"name": "From LD"}, {"name": "Second"}]
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "name": {
                    "selector": "name",
                    "type": "json_path",
                    "source": "json_ld",
                },
            }},
            json_ld=json_ld,
        )
        assert result == {"name": "From LD"}

    def test_json_ld_absent_returns_none(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "name": {
                    "selector": "name",
                    "type": "json_path",
                    "source": "json_ld",
                },
            }},
            json_ld=None,
        )
        assert result == {"name": None}

    def test_missing_next_data_returns_none(self) -> None:
        result = extract_data(
            _FakePage("<html></html>"),
            {"fields": {
                "name": {
                    "selector": "props.pageProps.product.name",
                    "type": "json_path",
                },
            }},
            next_data=None,
        )
        assert result == {"name": None}


class TestExtractDataRobustness:
    def test_missing_fields_key_returns_empty_dict(self) -> None:
        assert extract_data(_title_page(), {}) == {}

    def test_broken_field_isolated_as_none(self) -> None:
        class _ExplodingPage(_FakePage):
            def css(self, selector: str) -> Any:
                raise ValueError("boom")

        result = extract_data(
            _ExplodingPage(_PAGE_HTML),
            {"fields": {
                "broken": {"selector": "h1.title::text"},
                "fine": {"selector": "//h1[@class='title']/text()",
                         "type": "xpath"},
            }},
        )
        assert result == {"broken": None, "fine": "Widget"}


# ── extract_data_with_metadata (verification view) ───────────────────


class TestExtractDataWithMetadata:
    def test_reports_matched_and_sample(self) -> None:
        results = extract_data_with_metadata(
            _title_page(),
            {"fields": {
                "title": {"selector": "h1.title", "type": "css"},
                "ghost": {"selector": ".missing::text", "type": "css"},
            }},
        )
        by_name = {r.field_name: r for r in results}
        assert by_name["title"].matched is True
        assert by_name["title"].match_count == 1
        assert by_name["title"].value == "Widget"
        assert by_name["title"].sample == "Widget"
        assert by_name["ghost"].matched is False
        assert by_name["ghost"].match_count == 0
        assert by_name["ghost"].value is None

    def test_multiple_match_count_and_sample(self) -> None:
        results = extract_data_with_metadata(
            _title_page(),
            {"fields": {
                "images": {
                    "selector": "img.gallery::attr(src)",
                    "type": "css",
                    "multiple": True,
                },
            }},
        )
        (field,) = results
        assert field.multiple is True
        assert field.match_count == 2
        assert field.value == ["img1.png", "img2.png"]
        assert field.sample == "img1.png"

    def test_sample_respects_max_length(self) -> None:
        results = extract_data_with_metadata(
            _title_page(),
            {"fields": {"title": {"selector": "h1.title", "type": "css"}}},
            sample_max_length=3,
        )
        assert results[0].sample == "Wid"

    def test_error_field_reports_unmatched(self) -> None:
        class _ExplodingPage(_FakePage):
            def css(self, selector: str) -> Any:
                raise ValueError("boom")

        results = extract_data_with_metadata(
            _ExplodingPage(_PAGE_HTML),
            {"fields": {"broken": {"selector": "h1.title::text"}}},
        )
        (field,) = results
        assert field.matched is False
        assert field.match_count == 0
        assert field.value is None
        assert field.sample is None

    def test_missing_fields_key_returns_empty_list(self) -> None:
        assert extract_data_with_metadata(_title_page(), {}) == []


class TestNoPseudoLeakage:
    """Guards the documented raw-HTML trap: bare selectors must never
    hand outer HTML to the caller."""

    def test_bare_selector_value_is_not_html(self) -> None:
        result = extract_data(
            _title_page(),
            {"fields": {"price": {"selector": "span.price"}}},
        )
        assert result["price"] == "129.90"
        assert "<span" not in result["price"]
