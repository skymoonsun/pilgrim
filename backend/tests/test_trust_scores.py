"""Trustpilot trust-score recipe: domain → score JSON.

Static tests run the real extraction engine over ``businessUnit`` blocks
captured live from trustpilot.com (``tests/fixtures/trustpilot_samples.json``).
The one network test is double-gated: ``integration`` marker
(``PILGRIM_RUN_INTEGRATION=1``) *and* ``PILGRIM_TRUSTPILOT_LIVE=1`` —
Trustpilot is behind an AWS WAF challenge, so it needs a browser engine
(optionally ``PILGRIM_TRUSTPILOT_CHROME=/path/to/chrome``).
"""

import importlib.util
import json
import os
from pathlib import Path
from typing import Any

import pytest

from app.crawlers.extraction import extract_data
from app.models.enums import ScraperProfile
from app.schemas.crawl_config import CrawlConfigCreate
from app.services.trust_scores import (
    TRUSTPILOT_EXTRACTION_SPEC,
    TRUSTPILOT_FETCH_OPTIONS,
    build_trust_record,
    build_trust_scores,
    domain_from_review_url,
    normalize_domain,
    trustpilot_review_url,
)

ROOT = Path(__file__).resolve().parent
FIXTURE: dict[str, Any] = json.loads(
    (ROOT / "fixtures" / "trustpilot_samples.json").read_text()
)
UNITS: dict[str, dict[str, Any]] = FIXTURE["units"]
EXAMPLE_PATH = ROOT.parent.parent / "docs" / "examples" / "trustpilot-trust-scores.json"
EXAMPLE = json.loads(EXAMPLE_PATH.read_text())

KINGUIN = UNITS["kinguin.net"]


def _json_ld(unit: dict[str, Any]) -> list[dict[str, Any]]:
    """@graph container as a real review page embeds it (fixture-derived).

    Mirrors the live kinguin.net page (2026-11-23): one ld+json document
    whose ``@graph`` wraps non-rating nodes (Organization/WebPage) plus
    the ``LocalBusiness`` node carrying ``aggregateRating``.  The walk in
    ``_select_json_ld_block`` must flatten the graph and ``ld_match`` pick
    the LocalBusiness node — not the container, not block 0.
    """
    return [
        {
            "@context": "https://schema.org",
            "@graph": [
                {"@type": "BreadcrumbList", "itemListElement": []},
                {"@type": "WebPage", "name": unit.get("displayName", "")},
                {
                    "@type": "LocalBusiness",
                    "name": unit.get("displayName", ""),
                    "aggregateRating": {
                        "@type": "AggregateRating",
                        "ratingValue": unit["trustScore"],
                        "reviewCount": unit["numberOfReviews"],
                        "bestRating": 5,
                    },
                },
            ],
        },
    ]


def _extract(unit: dict[str, Any]) -> dict[str, Any]:
    """Full-pipeline extraction: JSON-LD primary + NextData fallback."""
    next_data = {"props": {"pageProps": {"businessUnit": unit}}}
    return extract_data(
        None,
        TRUSTPILOT_EXTRACTION_SPEC,
        next_data=next_data,
        json_ld=_json_ld(unit),
    )


def _nd(unit: dict[str, Any]) -> dict[str, Any]:
    """NextData-only extraction (blocked JSON-LD, e.g. WAF page)."""
    next_data = {"props": {"pageProps": {"businessUnit": unit}}}
    return extract_data(None, TRUSTPILOT_EXTRACTION_SPEC, next_data=next_data)


class TestRecipe:
    def test_extracts_every_field_from_live_capture(self) -> None:
        got = _extract(KINGUIN)
        assert got == {
            "trust_score": KINGUIN["trustScore"],
            "review_count": KINGUIN["numberOfReviews"],
            "trust_score_nd": KINGUIN["trustScore"],
            "review_count_nd": KINGUIN["numberOfReviews"],
            "stars": KINGUIN["stars"],
            "display_name": "Kinguin.net",
            "identifying_name": "kinguin.net",
            "trust_score_css": None,
            "review_count_css": None,
        }

    def test_nextdata_only_capture_still_yields_the_score(self) -> None:
        got = _nd(KINGUIN)
        assert got["trust_score"] is None  # no JSON-LD → primary absent
        assert got["trust_score_nd"] == KINGUIN["trustScore"]

    def test_all_captured_sellers_yield_a_score(self) -> None:
        assert len(UNITS) >= 5
        for unit in UNITS.values():
            assert isinstance(_extract(unit)["trust_score"], float)

    def test_missing_business_unit_extracts_none(self) -> None:
        got = extract_data(None, TRUSTPILOT_EXTRACTION_SPEC, next_data={"props": {}})
        assert got["trust_score"] is None

    def test_config_payload_is_a_valid_stealth_recipe(self) -> None:
        # The WAF challenge makes a plain-HTTP profile useless here.
        cfg = CrawlConfigCreate(
            name="trustpilot-trust-score",
            scraper_profile=ScraperProfile.STEALTH,
            extraction_spec=TRUSTPILOT_EXTRACTION_SPEC,
            fetch_options=TRUSTPILOT_FETCH_OPTIONS,
        )
        assert cfg.scraper_profile is ScraperProfile.STEALTH
        fields = cfg.extraction_spec["fields"]
        # Primary json-ld, NextData fallback, CSS last resort.
        assert fields["trust_score"] == {
            "selector": "aggregateRating.ratingValue",
            "type": "json_path",
            "source": "json_ld",
            "ld_match": {"key": "@type", "value": "LocalBusiness"},
        }
        assert fields["trust_score_nd"]["source"] == "next_data"
        assert fields["trust_score_css"]["type"] == "css"
        assert all(
            f["type"] in ("json_path", "css") for f in fields.values()
        )

    def test_seed_0003_registers_the_recipe(self) -> None:
        path = ROOT.parent / "seeds" / "0003_trustpilot_trust_score.py"
        module = _load_module(path, "seed_0003")

        added: list[Any] = []

        class _Session:
            def add(self, obj: Any) -> None:
                added.append(obj)

            async def flush(self) -> None:
                return None

        import asyncio

        asyncio.run(module.run(_Session()))
        assert len(added) == 1
        assert added[0].name == "trustpilot-trust-score"
        assert added[0].scraper_profile is ScraperProfile.STEALTH
        assert added[0].extraction_spec == TRUSTPILOT_EXTRACTION_SPEC


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestUrlAndDomain:
    @pytest.mark.parametrize(
        ("raw", "host"),
        [
            ("kinguin.net", "kinguin.net"),
            ("WWW.GOG.com", "gog.com"),
            ("https://www.instant-gaming.com/en/games", "instant-gaming.com"),
        ],
    )
    def test_normalize_domain(self, raw: str, host: str) -> None:
        assert normalize_domain(raw) == host
        assert trustpilot_review_url(raw) == f"https://www.trustpilot.com/review/{host}"

    @pytest.mark.parametrize("bad", ["", "localhost", "https://"])
    def test_non_domain_rejected(self, bad: str) -> None:
        with pytest.raises(ValueError):
            trustpilot_review_url(bad)


class TestDomainFromReviewUrl:
    @pytest.mark.parametrize(
        ("url", "domain"),
        [
            ("https://www.trustpilot.com/review/kinguin.net", "kinguin.net"),
            ("https://trustpilot.com/review/kinguin.net", "kinguin.net"),
            ("http://www.trustpilot.com/review/Www.Gog.Com", "gog.com"),
            ("www.trustpilot.com/review/www.gog.com", "gog.com"),
            ("https://www.trustpilot.com/review/kinguin.net/", "kinguin.net"),
            ("https://www.trustpilot.com/review/kinguin.net/?src=rss", "kinguin.net"),
            ("HTTPS://WWW.TRUSTPILOT.COM/review/kinguin.net#reviews", "kinguin.net"),
        ],
    )
    def test_review_urls_resolve_the_domain(self, url: str, domain: str) -> None:
        assert domain_from_review_url(url) == domain

    @pytest.mark.parametrize(
        "url",
        [
            "",
            "https://www.trustpilot.com/",
            "https://www.trustpilot.com/review/",
            "https://www.trustpilot.com/r/kinguin.net",
            "kinguin.net",
            "https://example.com/review/kinguin.net",
        ],
    )
    def test_other_urls_resolve_to_none(self, url: str) -> None:
        assert domain_from_review_url(url) is None

    def test_roundtrip_with_review_url(self) -> None:
        for raw in ("kinguin.net", "www.gog.com"):
            url = trustpilot_review_url(raw)
            domain = domain_from_review_url(url)
            assert domain == normalize_domain(raw)
            assert domain is not None
            assert trustpilot_review_url(domain) == url


class TestRecordPrecedence:
    def _record(self, extracted: dict[str, Any]) -> dict[str, Any]:
        return build_trust_record(
            "kinguin.net",
            {"stars": 4.5, "display_name": "Kinguin.net", **extracted},
        )

    def test_json_ld_beats_next_data_beats_css(self) -> None:
        assert self._record({
            "trust_score": 4.6, "review_count": 125805,
            "trust_score_nd": 3.9, "review_count_nd": 11,
            "trust_score_css": "2.2", "review_count_css": "5",
        })["score"] == 4.6
        assert self._record({
            "trust_score_nd": 3.9, "review_count_nd": 11,
            "trust_score_css": "2.2", "review_count_css": "5",
        })["score"] == 3.9
        record = self._record({
            "trust_score_css": "2.2", "review_count_css": "5",
        })
        assert record["score"] == 2.2
        assert record["reviews"] == 5  # ::attr text is coerced

    def test_reviews_follow_the_same_precedence(self) -> None:
        record = self._record({
            "trust_score": 4.6, "review_count": 125805,
            "trust_score_nd": 3.9, "review_count_nd": 11,
            "trust_score_css": "2.2", "review_count_css": "5",
        })
        assert record["reviews"] == 125805

    def test_strict_tiers_reject_strings_but_css_rescues(self) -> None:
        # NextData carries JSON numbers — a string there stays unusable
        # and the CSS tier (attr text) supplies the score.
        record = self._record({
            "trust_score_nd": "4.5", "review_count_nd": "1200",
            "trust_score_css": "3.3", "review_count_css": "77",
        })
        assert record["score"] == 3.3
        assert record["reviews"] == 77

    def test_name_and_stars_from_either_tier(self) -> None:
        extracted = {
            "stars": 4.5, "stars_nd": 2.0,
            "display_name": "Kinguin.net", "display_name_nd": "ND name",
            "trust_score": 4.6,
        }
        record = build_trust_record("kinguin.net", extracted)
        assert record["stars"] == 4.5 and record["name"] == "Kinguin.net"

        fell_back = build_trust_record(
            "kinguin.net",
            {
                "stars_nd": 2.0, "display_name_nd": "ND name",
                "trust_score_nd": 4.6, "review_count_nd": 10,
            },
        )
        assert fell_back["stars"] == 2.0 and fell_back["name"] == "ND name"

    def test_identifying_name_is_the_last_name_fallback(self) -> None:
        record = build_trust_record(
            "kinguin.net",
            {"trust_score": 4.6, "review_count": 10, "identifying_name": "kinguin.net"},
        )
        assert record["name"] == "kinguin.net"

    @pytest.mark.parametrize(
        "extracted",
        [
            {},  # nothing at all
            {"trust_score": None, "trust_score_nd": None, "trust_score_css": None},
            {"trust_score": "4.6"},  # primary tier rejects strings
            {"trust_score_nd": "4.5", "trust_score_css": "garbage"},
            {"trust_score": True},  # bool is never usable
            {"trust_score": -0.5, "trust_score_nd": 4.0},  # out of range fails hard
            {"trust_score_nd": 5.5},  # same on the fallback tier
            {"trust_score_css": "6.1"},
        ],
    )
    def test_unusable_score_raises(self, extracted: dict[str, Any]) -> None:
        with pytest.raises(ValueError):
            build_trust_record("x.com", extracted)

    def test_fixture_extraction_builds_the_reference_record(self) -> None:
        assert build_trust_record("kinguin.net", _extract(KINGUIN)) == {
            "score": KINGUIN["trustScore"],
            "reviews": KINGUIN["numberOfReviews"],
            "stars": KINGUIN["stars"],
            "name": "Kinguin.net",
            "url": "https://www.trustpilot.com/review/kinguin.net",
        }


class TestScoreDocument:
    def test_record_shape(self) -> None:
        rec = build_trust_record("gog.com", _extract(UNITS["www.gog.com"]))
        assert rec == {
            "score": UNITS["www.gog.com"]["trustScore"],
            "reviews": UNITS["www.gog.com"]["numberOfReviews"],
            "stars": UNITS["www.gog.com"]["stars"],
            "name": "GOG.COM",
            "url": "https://www.trustpilot.com/review/gog.com",
        }

    @pytest.mark.parametrize("score", [None, "4.5", True, -1, 5.5])
    def test_unusable_score_raises(self, score: Any) -> None:
        with pytest.raises(ValueError):
            build_trust_record("x.com", {"trust_score": score})

    def test_document_reports_failures_instead_of_inventing(self) -> None:
        doc = build_trust_scores(
            {
                "kinguin.net": _extract(KINGUIN),
                "blocked.example": None,
                "empty.example": {"trust_score": None},
            }
        )
        assert set(doc["scores"]) == {"kinguin.net"}
        assert doc["failed"] == ["blocked.example", "empty.example"]
        assert doc["source"] == "trustpilot" and doc["scale"] == 5

    def test_static_example_equals_builder_output_for_captures(self) -> None:
        doc = build_trust_scores({dom: _extract(unit) for dom, unit in UNITS.items()})
        assert doc == EXAMPLE


@pytest.mark.integration
@pytest.mark.skipif(
    os.environ.get("PILGRIM_TRUSTPILOT_LIVE") != "1",
    reason="real trustpilot.com request; set PILGRIM_TRUSTPILOT_LIVE=1",
)
def test_live_trustpilot_review_page() -> None:
    """Fetch a real review page through the stealth profile and extract."""
    from app.crawlers.factory import create_fetcher
    from app.crawlers.html_sanitizer import sanitize_html

    options: dict[str, Any] = dict(TRUSTPILOT_FETCH_OPTIONS)
    chrome = os.environ.get("PILGRIM_TRUSTPILOT_CHROME")
    if chrome:
        options["executable_path"] = chrome
    domain = os.environ.get("PILGRIM_TRUSTPILOT_DOMAIN", "kinguin.net")

    response = create_fetcher(ScraperProfile.STEALTH, options).get(
        trustpilot_review_url(domain)
    )
    assert response.status == 200
    html = response.body.decode() if isinstance(response.body, bytes) else response.body
    extracted = extract_data(
        response, TRUSTPILOT_EXTRACTION_SPEC, next_data=sanitize_html(html).next_data
    )
    record = build_trust_record(domain, extracted)
    assert 0 < record["score"] <= 5
    assert record["reviews"] and record["reviews"] > 0


# ── @graph JSON-LD (real Trustpilot page shape, 2026-11-23) ────────────
# Live capture: the review page's ld+json is a ``@graph`` document whose
# ``LocalBusiness`` node carries the aggregateRating; ``Review`` nodes
# carry per-review ratings that must never win.  next_data is seeded with
# a DIFFERENT score (4.9) so the test proves the JSON-LD tier precedence.

_REAL_GRAPH_DOC = {
    "@context": "https://schema.org",
    "@graph": [
        {
            "@type": "Organization",
            "@id": "https://www.trustpilot.com/#/schema/Organization/1",
            "name": "Trustpilot",
        },
        {
            "@type": "WebPage",
            "@id": "https://www.trustpilot.com/review/kinguin.net",
            "name": "Kinguin.net Reviews",
        },
        {
            "@type": "LocalBusiness",
            "@id": "https://www.trustpilot.com/#/schema/Organization/kinguin.net",
            "name": "Kinguin.net",
            "aggregateRating": {
                "@type": "AggregateRating",
                "bestRating": "5",
                "worstRating": "1",
                "ratingValue": "4.6",
                "reviewCount": "126143",
            },
        },
        {"@type": "Review", "reviewRating": {"@type": "Rating", "ratingValue": "5"}},
        {"@type": "Review", "reviewRating": {"@type": "Rating", "ratingValue": "3"}},
    ],
}

_REAL_PAGE_HTML = (
    "<html><head><title>Kinguin.net Reviews</title>"
    '<script type="application/ld+json" data-business-unit-json-ld="true">'
    + json.dumps(_REAL_GRAPH_DOC)
    + "</script>"
    '<script id="__NEXT_DATA__" type="application/json">'
    + json.dumps(
        {
            "props": {
                "pageProps": {
                    "businessUnit": {
                        "trustScore": 4.9,  # stale/sibling copy — must NOT win
                        "numberOfReviews": 99999,
                        "stars": 5.0,
                        "displayName": "Kinguin.net",
                        "identifyingName": "kinguin.net",
                    }
                }
            }
        }
    )
    + "</script></head><body><main></main></body></html>"
)


class _CssStubResponse:
    """Response stand-in for extract_data's css/xpath surface."""

    def css(self, selector: str, **kwargs: Any) -> "list[Any]":  # noqa: D102
        return []

    def xpath(self, selector: str, **kwargs: Any) -> "list[Any]":  # noqa: D102
        return []


@pytest.mark.integration
def test_real_page_graph_json_ld_primary_over_next_data() -> None:
    """@graph LocalBusiness aggregateRating wins over next_data + Reviews."""
    from app.crawlers.html_sanitizer import sanitize_html

    sanitized = sanitize_html(_REAL_PAGE_HTML)
    data = extract_data(
        _CssStubResponse(),
        TRUSTPILOT_EXTRACTION_SPEC,
        next_data=sanitized.next_data,
        json_ld=sanitized.json_ld,
    )
    # Provenance: the *primary* (JSON-LD) tier won — 4.6/126143 — with the
    # next_data stale copy (4.9/99999) untouched and the Reviews' 5.0/3.0
    # never picked up.
    assert data["trust_score"] == pytest.approx(4.6)
    assert data["review_count"] == 126143
    record = build_trust_record("kinguin.net", data)
    assert record["score"] == pytest.approx(4.6)
    assert record["reviews"] == 126143
    assert record["name"] == "Kinguin.net"


def test_graph_container_flattened_by_sanitizer() -> None:
    """The @graph LocalBusiness node survives _extract_json_ld type filtering."""
    from app.crawlers.html_sanitizer import sanitize_html

    sanitized = sanitize_html(_REAL_PAGE_HTML)
    types = [block.get("@type") for block in (sanitized.json_ld or [])]
    assert "LocalBusiness" in types
    # And the review nodes did not flood the result.
    assert types.count("Review") == 0
