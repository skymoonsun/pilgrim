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


def _extract(unit: dict[str, Any]) -> dict[str, Any]:
    next_data = {"props": {"pageProps": {"businessUnit": unit}}}
    return extract_data(None, TRUSTPILOT_EXTRACTION_SPEC, next_data=next_data)


class TestRecipe:
    def test_extracts_every_field_from_live_capture(self) -> None:
        unit = UNITS["kinguin.net"]
        got = _extract(unit)
        assert got == {
            "trust_score": unit["trustScore"],
            "review_count": unit["numberOfReviews"],
            "stars": unit["stars"],
            "display_name": unit["displayName"],
            "identifying_name": "kinguin.net",
        }

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
        assert all(
            f["type"] == "json_path" and f["source"] == "next_data"
            for f in cfg.extraction_spec["fields"].values()
        )

    def test_seed_0003_registers_the_recipe(self) -> None:
        path = ROOT.parent / "seeds" / "0003_trustpilot_trust_score.py"
        spec = importlib.util.spec_from_file_location("seed_0003", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

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
                "kinguin.net": _extract(UNITS["kinguin.net"]),
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
