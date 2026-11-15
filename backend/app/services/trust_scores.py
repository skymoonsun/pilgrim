"""Seller trust scores collected from Trustpilot review pages.

Trustpilot renders ``https://www.trustpilot.com/review/<domain>`` as a
Next.js page whose ``__NEXT_DATA__`` carries the rating under
``props.pageProps.businessUnit`` (``trustScore`` 0-5, ``numberOfReviews``,
``stars`` = rounded half-star value). The page sits behind an AWS WAF
bot challenge: plain HTTP (``fetcher`` profile) gets a 403 interstitial,
a real browser engine (``stealth`` profile) gets the page.

This module is the recipe + the glue:

* :data:`TRUSTPILOT_EXTRACTION_SPEC` — the ``extraction_spec`` of the
  ``trustpilot-trust-score`` crawl config (seed ``0003``);
* :func:`trustpilot_review_url` — domain → review URL (scrape target);
* :func:`build_trust_record` / :func:`build_trust_scores` — extracted
  fields → the domain → score JSON document consumed by c4game-core
  (``feed_url`` adapter or admin API)::

      {"source": "trustpilot", "scale": 5, "scores": {
          "kinguin.net": {"score": 4.6, "reviews": 125805, "stars": 4.5,
                          "name": "Kinguin.net",
                          "url": "https://www.trustpilot.com/review/kinguin.net"}}}
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TRUSTPILOT_REVIEW_URL = "https://www.trustpilot.com/review/{domain}"
TRUST_SCALE = 5

#: ``extraction_spec`` of the ``trustpilot-trust-score`` crawl config.
TRUSTPILOT_EXTRACTION_SPEC: dict[str, Any] = {
    "fields": {
        "trust_score": {
            "selector": "props.pageProps.businessUnit.trustScore",
            "type": "json_path",
            "source": "next_data",
        },
        "review_count": {
            "selector": "props.pageProps.businessUnit.numberOfReviews",
            "type": "json_path",
            "source": "next_data",
        },
        "stars": {
            "selector": "props.pageProps.businessUnit.stars",
            "type": "json_path",
            "source": "next_data",
        },
        "display_name": {
            "selector": "props.pageProps.businessUnit.displayName",
            "type": "json_path",
            "source": "next_data",
        },
        "identifying_name": {
            "selector": "props.pageProps.businessUnit.identifyingName",
            "type": "json_path",
            "source": "next_data",
        },
    }
}

#: Trustpilot sits behind an AWS WAF challenge — needs a browser engine.
TRUSTPILOT_FETCH_OPTIONS: dict[str, Any] = {"timeout": 60, "network_idle": True}


def normalize_domain(domain: str) -> str:
    """Lower-case bare host: strips scheme, path and a leading ``www.``."""
    host = domain.strip().lower()
    for prefix in ("https://", "http://"):
        if host.startswith(prefix):
            host = host[len(prefix) :]
    host = host.split("/", 1)[0]
    return host.removeprefix("www.")


def trustpilot_review_url(domain: str) -> str:
    """Review-page URL for a seller domain (the scrape target)."""
    host = normalize_domain(domain)
    if not host or "." not in host:
        raise ValueError(f"not a domain: {domain!r}")
    return TRUSTPILOT_REVIEW_URL.format(domain=host)


def build_trust_record(domain: str, extracted: Mapping[str, Any]) -> dict[str, Any]:
    """One domain's extracted fields → a score record.

    Raises ``ValueError`` when the page carried no usable score (blocked
    interstitial, unknown business) — callers skip the domain instead of
    inventing a number.
    """
    raw = extracted.get("trust_score")
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValueError(f"no trust score extracted for {domain!r}")
    score = float(raw)
    if not 0 <= score <= TRUST_SCALE:
        raise ValueError(f"trust score {score} out of range for {domain!r}")
    reviews = extracted.get("review_count")
    stars = extracted.get("stars")
    name = extracted.get("display_name")
    return {
        "score": score,
        "reviews": int(reviews)
        if isinstance(reviews, (int, float)) and not isinstance(reviews, bool)
        else None,
        "stars": float(stars)
        if isinstance(stars, (int, float)) and not isinstance(stars, bool)
        else None,
        "name": name if isinstance(name, str) else None,
        "url": trustpilot_review_url(domain),
    }


def build_trust_scores(
    extracted_by_domain: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, Any]:
    """``{domain: extracted-fields | None}`` → the domain → score document.

    ``None`` / unusable entries are listed under ``failed`` rather than
    dropped silently, so a partial crawl is visible downstream.
    """
    scores: dict[str, Any] = {}
    failed: list[str] = []
    for domain, extracted in extracted_by_domain.items():
        key = normalize_domain(domain)
        try:
            scores[key] = build_trust_record(domain, extracted or {})
        except ValueError:
            failed.append(key)
    return {
        "source": "trustpilot",
        "scale": TRUST_SCALE,
        "scores": scores,
        "failed": sorted(failed),
    }
