"""Seller trust scores collected from Trustpilot review pages.

Trustpilot renders ``https://www.trustpilot.com/review/<domain>`` as a
Next.js page.  The rating is embedded twice: a JSON-LD ``@graph``
document whose ``LocalBusiness`` node carries ``aggregateRating``
(the *primary* read — first-party schema.org data), and the
``__NEXT_DATA__`` payload under ``props.pageProps.businessUnit``
(``trustScore`` 0-5, ``numberOfReviews``, ``stars`` = rounded half-star
value) as the fallback.  Both were verified on the live kinguin.net
page (2026-11-23: ratingValue 4.6 / reviewCount 126143 on both tiers).
The page sits behind an AWS WAF bot challenge: plain HTTP (``fetcher``
profile) gets a 403 interstitial, a real browser engine (``stealth``
profile) gets the page.

This module is the recipe + the glue:

* :data:`TRUSTPILOT_EXTRACTION_SPEC` — the ``extraction_spec`` of the
  ``trustpilot-trust-score`` crawl config (seed ``0003``): JSON-LD
  primary fields, ``__NEXT_DATA__`` fallbacks (``*_nd``) and
  last-resort DOM-attribute fallbacks (``*_css``);
* :func:`trustpilot_review_url` — domain → review URL (scrape target);
* :func:`domain_from_review_url` — the inverse: review URL → domain
  (key used by the callback trust-document transform);
* :func:`build_trust_record` / :func:`build_trust_scores` — extracted
  fields → the domain → score JSON document consumed by c4game-core
  (``feed_url`` adapter or admin API)::

      {"source": "trustpilot", "scale": 5, "scores": {
          "kinguin.net": {"score": 4.6, "reviews": 125805, "stars": 4.5,
                          "name": "Kinguin.net",
                          "url": "https://www.trustpilot.com/review/kinguin.net"}}}

The document shape is a cross-repo contract (keytickr-core's
``parse_trust_document``): top-level ``source`` / ``scale`` / ``scores``
/ ``failed``; callers may add ``crawled_at``.  Do not rename keys.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TRUSTPILOT_REVIEW_URL = "https://www.trustpilot.com/review/{domain}"
TRUST_SCALE = 5

#: ``extraction_spec`` of the ``trustpilot-trust-score`` crawl config.
#:
#: JSON-LD primary (extractor picks the ``LocalBusiness`` node of the
#: ``@graph`` document via ``ld_match``), ``__NEXT_DATA__`` fallback
#: fields (``*_nd``), and CSS-attribute last resorts (``*_css`` — exact
#: Trustpilot attributes may need adjusting as the page evolves; kept
#: tolerant on purpose).  :func:`build_trust_record` consumes all three
#: tiers via precedence.
TRUSTPILOT_EXTRACTION_SPEC: dict[str, Any] = {
    "fields": {
        # ── Primary: JSON-LD aggregateRating (@graph LocalBusiness) ──
        "trust_score": {
            "selector": "aggregateRating.ratingValue",
            "type": "json_path",
            "source": "json_ld",
            "ld_match": {"key": "@type", "value": "LocalBusiness"},
        },
        "review_count": {
            "selector": "aggregateRating.reviewCount",
            "type": "json_path",
            "source": "json_ld",
            "ld_match": {"key": "@type", "value": "LocalBusiness"},
        },
        # ── Fallback: __NEXT_DATA__ businessUnit ──────────────────
        "trust_score_nd": {
            "selector": "props.pageProps.businessUnit.trustScore",
            "type": "json_path",
            "source": "next_data",
        },
        "review_count_nd": {
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
        # ── Last resort: DOM attributes (unstable — tolerant) ─────
        "trust_score_css": {
            "selector": "span[data-rating-score]::attr(data-rating-score)",
            "type": "css",
        },
        "review_count_css": {
            "selector": "[data-review-count]::attr(data-review-count)",
            "type": "css",
        },
    }
}

#: Trustpilot sits behind an AWS WAF challenge — needs a browser engine.
TRUSTPILOT_FETCH_OPTIONS: dict[str, Any] = {"timeout": 60, "network_idle": True}

#: Where a record field may live in an extraction row, in precedence
#: order: JSON-LD primary → ``__NEXT_DATA__`` fallback (strict numbers)
#: → CSS fallback (``::attr`` text, coerced).  The first tier that
#: yields a usable value wins.
_STRICT_SCORE_FIELDS = ("trust_score", "trust_score_nd")
_STRICT_REVIEW_FIELDS = ("review_count", "review_count_nd")
_CSS_SCORE_FIELDS = ("trust_score_css",)
_CSS_REVIEW_FIELDS = ("review_count_css",)
_STARS_FIELDS = ("stars", "stars_nd")
_NAME_FIELDS = (
    "display_name",
    "display_name_nd",
    "identifying_name",
    "identifying_name_nd",
)


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


def domain_from_review_url(url: str) -> str | None:
    """Normalized seller domain from a ``trustpilot.com/review/PATH`` URL.

    Accepts http(s) and scheme-less forms on the ``trustpilot.com`` /
    ``www.trustpilot.com`` hosts and returns the first ``review/`` path
    segment normalized exactly like every other document key.  Anything
    else — other hosts, missing or empty path segment, unrelated URLs —
    is ``None``.
    """
    rest = (url or "").strip().lower()
    for prefix in ("https://", "http://"):
        if rest.startswith(prefix):
            rest = rest[len(prefix) :]
    host, _, path = rest.partition("/")
    if host not in ("trustpilot.com", "www.trustpilot.com"):
        return None
    if not path.startswith("review/"):
        return None
    domain = (
        path[len("review/") :]
        .split("/", 1)[0]
        .split("?", 1)[0]
        .split("#", 1)[0]
        .strip()
    )
    if not domain:
        return None
    return normalize_domain(domain) or None


def _strict_number(raw: Any) -> float | None:
    """Usable only when *raw* is already a JSON number (bools excluded)."""
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


def _coerced_number(raw: Any) -> float | None:
    """Like :func:`_strict_number` but also accepts clean numeric strings.

    The ``*_css`` fields extract from DOM ``::attr(...)`` — they arrive
    as text even when the attribute holds a number.
    """
    number = _strict_number(raw)
    if number is not None:
        return number
    if isinstance(raw, str):
        try:
            return float(raw.strip())
        except ValueError:
            return None
    return None


def _pick_number(
    extracted: Mapping[str, Any],
    fields: tuple[str, ...],
    *,
    tolerant: bool,
) -> float | None:
    """First field in *fields* that yields a usable number."""
    for field in fields:
        raw = extracted.get(field)
        value = _coerced_number(raw) if tolerant else _strict_number(raw)
        if value is not None:
            return value
    return None


def _pick_score(extracted: Mapping[str, Any]) -> float | None:
    """Score from JSON-LD/NextData (strict numbers) then CSS (coerced)."""
    strict = _pick_number(extracted, _STRICT_SCORE_FIELDS, tolerant=False)
    if strict is not None:
        return strict
    return _pick_number(extracted, _CSS_SCORE_FIELDS, tolerant=True)


def _pick_reviews(extracted: Mapping[str, Any]) -> int | None:
    strict = _pick_number(extracted, _STRICT_REVIEW_FIELDS, tolerant=False)
    if strict is None:
        strict = _pick_number(extracted, _CSS_REVIEW_FIELDS, tolerant=True)
    return int(strict) if strict is not None else None


def _pick_stars(extracted: Mapping[str, Any]) -> float | None:
    """Stars from either the NextData or JSON-LD tier — never invented."""
    return _pick_number(extracted, _STARS_FIELDS, tolerant=False)


def _pick_name(extracted: Mapping[str, Any]) -> str | None:
    """Display name from either tier (falls back to identifying name)."""
    for field in _NAME_FIELDS:
        raw = extracted.get(field)
        if isinstance(raw, str):
            return raw
    return None


def build_trust_record(domain: str, extracted: Mapping[str, Any]) -> dict[str, Any]:
    """One domain's extracted fields → a score record.

    Score and reviews follow the field precedence (JSON-LD primary →
    ``__NEXT_DATA__`` fallback → CSS-attribute fallback); stars and name
    may come from either the JSON-LD or the NextData tier.  Raises
    ``ValueError`` when the page carried no usable score (blocked
    interstitial, unknown business) — callers skip the domain instead of
    inventing a number.
    """
    row = extracted or {}
    score = _pick_score(row)
    if score is None:
        raise ValueError(f"no trust score extracted for {domain!r}")
    if not 0 <= score <= TRUST_SCALE:
        raise ValueError(f"trust score {score} out of range for {domain!r}")
    return {
        "score": score,
        "reviews": _pick_reviews(row),
        "stars": _pick_stars(row),
        "name": _pick_name(row),
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
