"""AI-powered extraction spec generation and verification service.

Orchestrates the full pipeline:
1. Fetch the target page HTML via Scrapling (same fetcher as crawl jobs).
2. Sanitize the HTML for LLM consumption.
3. Build a structured prompt.
4. Call the configured LLM provider (Ollama by default).
5. Validate the returned extraction spec.
6. Return the result.

For verification:
1. Fetch the target page via Scrapling.
2. Run extraction spec against the page.
3. Report per-field results (matched, sample values).
4. Optionally iterate: ask LLM to fix failed selectors.
"""

from __future__ import annotations

import copy
import logging
import re

import httpx

from app.core.config import get_settings
from app.core.exceptions import (
    AIDisabledError,
    AIEmptySpecError,
    AIInvalidPageError,
)
from app.crawlers.extraction import assess_value_quality, extract_data_with_metadata
from app.crawlers.html_sanitizer import sanitize_html, truncate_html
from app.integrations.llm_base import LLMProvider, create_llm_provider
from app.models.enums import ScraperProfile
from app.schemas.ai import (
    AIStatusResponse,
    ExtractionSpecAIResponse,
    ExtractionSpecSchema,
    FieldVerificationResult,
    SpecVerificationResponse,
)
from app.services.ai_prompts import (
    GENERATE_SPEC_PROMPT,
    REFINE_SPEC_PROMPT,
    SYSTEM_PROMPT,
)

logger = logging.getLogger(__name__)


class AIService:
    """Stateless service for AI-powered extraction spec generation."""

    def __init__(self) -> None:
        self._provider: LLMProvider | None = None

    async def _get_provider(self) -> LLMProvider:
        if self._provider is None:
            self._provider = create_llm_provider()
        return self._provider

    # ── Public API ──────────────────────────────────────────────

    async def generate_extraction_spec(
        self,
        url: str,
        description: str,
        scraper_profile: ScraperProfile = ScraperProfile.FETCHER,
    ) -> ExtractionSpecAIResponse:
        """Full pipeline: fetch → sanitize → LLM → validate."""
        settings = get_settings()
        if not settings.ai_enabled:
            raise AIDisabledError()

        # 1. Fetch page HTML via Scrapling
        html = self._fetch_page_html(url, scraper_profile)

        # 2. Sanitize (extracts JSON-LD before stripping scripts)
        sanitize_result = sanitize_html(html)

        # 3. Truncate to max size
        max_chars = settings.ai_max_html_chars
        sanitized = truncate_html(sanitize_result.html, max_chars)
        if len(sanitize_result.html) > max_chars:
            logger.info(
                "Sanitized HTML truncated: %d → %d chars",
                len(sanitize_result.html),
                max_chars,
            )

        # 4. Build JSON-LD context section
        json_ld_context = self._build_json_ld_section(sanitize_result.json_ld)

        # 4b. Build __NEXT_DATA__ context section
        next_data_context = self._build_next_data_section(sanitize_result.next_data)

        # 4c. Search raw HTML for value snippets from the description
        value_context = self._find_value_contexts(html, description)

        # 5. Build prompt
        prompt = GENERATE_SPEC_PROMPT.format(
            description=description,
            html=sanitized,
            json_ld_context=json_ld_context + next_data_context + value_context,
        )

        # 6. Call LLM with structured output
        provider = await self._get_provider()
        llm_result: ExtractionSpecSchema = await provider.generate(  # type: ignore[assignment]
            prompt=prompt,
            schema=ExtractionSpecSchema,
            system=SYSTEM_PROMPT,
        )

        # 7. Validate
        self._validate_spec(llm_result)

        return ExtractionSpecAIResponse(
            extraction_spec=llm_result.model_dump(),
            model_used=getattr(provider, "_model", "unknown"),
            html_length=sanitize_result.original_length,
            sanitized_length=len(sanitized),
        )

    async def check_status(self) -> AIStatusResponse:
        """Check whether AI features are enabled and provider is reachable."""
        settings = get_settings()
        if not settings.ai_enabled:
            return AIStatusResponse(
                enabled=False, provider=None, reachable=False
            )

        reachable = await self._check_provider_reachable()
        return AIStatusResponse(
            enabled=True,
            provider=settings.llm_provider,
            reachable=reachable,
        )

    # ── Verification API ────────────────────────────────────────────

    async def verify_extraction_spec(
        self,
        url: str,
        extraction_spec: dict,
        scraper_profile: ScraperProfile = ScraperProfile.FETCHER,
        fetch_options: dict | None = None,
        max_iterations: int | None = None,
    ) -> SpecVerificationResponse:
        """Full verification pipeline: fetch → extract → evaluate → optionally refine.

        Parameters
        ----------
        url
            Target URL to verify against.
        extraction_spec
            The extraction spec dict (same format as
            ``CrawlConfiguration.extraction_spec``).
        scraper_profile
            Scrapling fetcher profile.
        fetch_options
            Optional fetch options passed to the Scrapling fetcher
            (e.g. ``{"timeout": 30, "impersonate": "chrome_131"}``).
        max_iterations
            Maximum LLM refinement rounds.  ``None`` uses the config default.
            ``0`` means verify only, no LLM refinement at all.
        """
        settings = get_settings()
        if not settings.ai_enabled:
            raise AIDisabledError()

        # Cap iterations to the server-configured maximum
        if max_iterations is None:
            max_iterations = settings.ai_max_verification_iterations
        max_iterations = min(max_iterations, settings.ai_max_verification_iterations)

        # 1. Fetch page via Scrapling (single fetch, reuse HTML from response)
        page_warning: str | None = None
        try:
            from app.crawlers.factory import create_fetcher  # noqa: F811

            fetcher = create_fetcher(scraper_profile, fetch_options=fetch_options or {})
            response = fetcher.get(url)
        except ImportError as exc:
            raise AIInvalidPageError(
                url,
                f"Scraper profile '{scraper_profile.value}' requires "
                f"browser binaries that are not available in this "
                f"environment. Use 'fetcher' or 'http_session' instead.",
            ) from exc
        except Exception as exc:
            raise AIInvalidPageError(url, str(exc)) from exc

        # Extract raw HTML from the Scrapling response for LLM prompts.
        # Scrapling responses expose HTML via different attributes depending
        # on the version and profile used.  Try the most reliable first.
        html: str = (
            getattr(response, "html", "")
            or getattr(response, "html_content", "")
            or getattr(response, "body", "")
            or str(response)
        )
        if not html.strip():
            raise AIInvalidPageError(url, "Page returned empty content")

        # Warn if page content is suspiciously small — likely JS-rendered
        # or blocked by anti-bot protection
        if len(html) < 500:
            page_warning = (
                "Page content is very short. The site may require JavaScript "
                "rendering or anti-bot bypass. Try using 'stealth' or "
                "'dynamic' scraper profile (requires worker environment) "
                "or add fetch_options like impersonate."
            )
            logger.warning(
                "Page content for %s is only %d chars — "
                "likely JS-rendered or anti-bot protected",
                url,
                len(html),
            )

        # 2. Sanitize HTML for structured data extraction (json_path support)
        sanitize_result = sanitize_html(html)

        # 3. Run extraction with metadata
        current_spec = copy.deepcopy(extraction_spec)
        iterations = 0
        model_used: str | None = None

        while True:
            field_results = extract_data_with_metadata(
                response, current_spec,
                next_data=sanitize_result.next_data,
                json_ld=sanitize_result.json_ld,
            )

            # Build extraction data dict and assess value quality
            extracted_data: dict[str, Any] = {}
            pydantic_results = []
            for r in field_results:
                val = r.value
                extracted_data[r.field_name] = val
                quality = assess_value_quality(val)
                pydantic_results.append(
                    FieldVerificationResult(
                        field_name=r.field_name,
                        matched=r.matched,
                        match_count=r.match_count,
                        sample_value=r.sample,
                        selector=r.selector,
                        selector_type=r.selector_type,  # type: ignore[arg-type]
                        value_quality=quality,  # type: ignore[arg-type]
                    )
                )

            # Determine which fields need fixing:
            # - failed (no match) OR bad quality (HTML in value, empty)
            failed_names = [r.field_name for r in field_results if not r.matched]
            bad_quality_names = [
                r.field_name
                for r in field_results
                if r.matched and assess_value_quality(r.value) in ("html", "empty")
            ]
            needs_fix = list(set(failed_names + bad_quality_names))
            all_good = len(needs_fix) == 0

            # If everything is good, or we have no iterations left, we're done
            if all_good or iterations >= max_iterations:
                break

            # 3. Ask LLM to refine selectors (include extraction results
            # so the AI can see what each field actually produces)
            refine_result = sanitize_html(html)
            max_chars = settings.ai_max_html_chars
            sanitized = truncate_html(refine_result.html, max_chars)
            if len(refine_result.html) > max_chars:
                logger.info(
                    "Sanitized HTML truncated for refinement: %d → %d chars",
                    len(refine_result.html),
                    max_chars,
                )

            json_ld_context = self._build_json_ld_section(refine_result.json_ld)
            next_data_context = self._build_next_data_section(refine_result.next_data)

            refine_prompt = self._build_refine_prompt(
                current_spec, needs_fix, extracted_data, sanitized,
                json_ld_context=json_ld_context + next_data_context,
            )

            provider = await self._get_provider()
            refined_fields: ExtractionSpecSchema = await provider.generate(  # type: ignore[assignment]
                prompt=refine_prompt,
                schema=ExtractionSpecSchema,
                system=SYSTEM_PROMPT,
            )
            model_used = getattr(provider, "_model", "unknown")

            # 4. Merge refined fields into the current spec
            current_spec = self._merge_refined_fields(
                current_spec, needs_fix, refined_fields.model_dump()
            )

            iterations += 1

        # 5. Determine if a refined spec was produced
        refined_spec = current_spec if iterations > 0 else None

        return SpecVerificationResponse(
            valid=len(needs_fix) == 0,
            total_fields=len(field_results),
            passed_fields=sum(
                1 for r in field_results
                if r.matched and assess_value_quality(r.value) == "good"
            ),
            failed_fields=needs_fix,
            field_results=pydantic_results,
            extracted_data=extracted_data,
            refined_spec=refined_spec,
            iterations_performed=iterations,
            model_used=model_used,
            page_warning=page_warning,
        )

    # ── Internal helpers ────────────────────────────────────────

    @staticmethod
    def _fetch_page_html(
        url: str,
        scraper_profile: ScraperProfile = ScraperProfile.FETCHER,
    ) -> str:
        """Fetch raw HTML from *url* using Scrapling fetchers.

        Uses the same ``create_fetcher`` factory as the crawl pipeline
        so TLS fingerprinting, anti-bot bypass and session handling
        work consistently.

        The basic ``Fetcher`` and ``FetcherSession`` profiles work in
        the API container (no browser required).  ``StealthyFetcher``
        and ``DynamicFetcher`` require browser binaries that live only
        in the worker image — calling them here will raise an
        ``ImportError`` that is surfaced as ``AIInvalidPageError``.
        """
        try:
            from app.crawlers.factory import create_fetcher  # noqa: F811

            fetcher = create_fetcher(scraper_profile)
            response = fetcher.get(url)
        except ImportError as exc:
            raise AIInvalidPageError(
                url,
                f"Scraper profile '{scraper_profile.value}' requires "
                f"browser binaries that are not available in this "
                f"environment. Use 'fetcher' or 'http_session' instead.",
            ) from exc
        except Exception as exc:
            raise AIInvalidPageError(url, str(exc)) from exc

        # Scrapling responses expose HTML via different attributes depending
        # on the version and profile.  Try the most reliable first.
        html: str = (
            getattr(response, "html", "")
            or getattr(response, "html_content", "")
            or getattr(response, "body", "")
            or str(response)
        )

        if not html.strip():
            raise AIInvalidPageError(
                url, "Page returned empty content"
            )

        return html

    @staticmethod
    def _validate_spec(spec: ExtractionSpecSchema) -> None:
        """Validate the LLM-returned spec is usable."""
        if not spec.fields:
            raise AIEmptySpecError()
        for name, field_spec in spec.fields.items():
            if not field_spec.selector:
                raise AIEmptySpecError()

    @staticmethod
    def _build_json_ld_section(json_ld: list[dict]) -> str:
        """Format JSON-LD data as a context section for the LLM prompt.

        Returns an empty string if no JSON-LD data was found.
        """
        if not json_ld:
            return ""
        import json as _json

        parts = ["\nStructured data (JSON-LD) found on the page — use this as a reference:"]
        for item in json_ld:
            # Compact JSON, limit size
            dumped = _json.dumps(item, ensure_ascii=False)
            if len(dumped) > 3000:
                dumped = dumped[:3000] + "...(truncated)"
            parts.append(dumped)
        parts.append("\n")
        return "\n".join(parts)

    @staticmethod
    def _build_next_data_section(next_data: dict | None) -> str:
        """Format ``__NEXT_DATA__`` product data as a context section.

        Many React/Next.js e-commerce sites embed product data (prices,
        availability, variants) in a ``<script id="__NEXT_DATA__">`` tag
        as JSON rather than as visible DOM elements.  This section gives
        the LLM direct access to that data so it can generate selectors
        that actually match, or recommend extracting from the embedded
        JSON instead.
        """
        if not next_data:
            return ""
        from app.crawlers.html_sanitizer import _extract_product_data_from_next

        summary = _extract_product_data_from_next(next_data)
        if not summary:
            return ""
        return (
            "\nEmbedded product data found on the page. "
            "The site uses React and stores product data in a "
            "<script> tag as JSON. Key product fields:\n"
            + summary
            + "\n\n"
            "IMPORTANT: If the data you need is present in the embedded JSON above "
            "but NOT visible in the HTML section below (e.g. the price is loaded "
            "client-side by JavaScript), use type: \"json_path\" with "
            "source: \"next_data\" and a dot-notation path to extract it directly. "
            "The paths shown above (e.g. productState.product.prices[0].formattedPrice) "
            "are the actual JSON paths — use them as the selector value. "
            "Example: {\"selector\": \"productState.product.prices[0].formattedPrice\", "
            "\"type\": \"json_path\", \"source\": \"next_data\"}\n"
        )

    @staticmethod
    def _find_value_contexts(
        html: str, description: str, max_snippets: int = 5, context_chars: int = 300,
    ) -> str:
        """Search raw HTML for specific values mentioned in the description.

        When a user says "the price is 20.999,00 TL" or "extract the title
        'Product Name'", this function finds where those values appear in the
        raw HTML and extracts surrounding context.  This gives the LLM highly
        relevant DOM snippets to generate accurate selectors.
        """
        # Extract potential values from the description — numbers with
        # decimal separators, quoted strings, and standalone tokens
        value_patterns: list[str] = []

        # Numbers with decimal separators (e.g. "20.999,00", "1,299.99", "5.490")
        for match in re.finditer(
            r"\b\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})\b", description
        ):
            value_patterns.append(match.group())

        # Quoted strings
        for match in re.finditer(r'["\']([^"\']{3,50})["\']', description):
            value_patterns.append(match.group(1))

        # Standalone capitalized/numeric tokens (likely product names/values)
        for match in re.finditer(r"\b[A-ZÇĞİÖŞÜ][a-zçğüışöü]{2,}\b", description):
            value_patterns.append(match.group())

        if not value_patterns:
            return ""

        # Deduplicate and search
        seen_positions: set[int] = set()
        snippets: list[str] = []

        for value in value_patterns:
            start = 0
            while len(snippets) < max_snippets:
                pos = html.find(value, start)
                if pos == -1:
                    break
                # Avoid overlapping snippets
                if any(abs(pos - sp) < context_chars for sp in seen_positions):
                    start = pos + len(value)
                    continue

                seen_positions.add(pos)
                # Extract context around the match
                ctx_start = max(0, pos - context_chars)
                ctx_end = min(len(html), pos + len(value) + context_chars)
                snippet = html[ctx_start:ctx_end]

                # Clean up the snippet (remove excessive whitespace)
                snippet = re.sub(r"\s+", " ", snippet).strip()
                if len(snippet) > 600:
                    snippet = snippet[:600] + "..."

                snippets.append(f"  ...{snippet}...")
                start = pos + len(value)

        if not snippets:
            return ""

        return (
            "\nRelevant HTML snippets — the target values appear in these "
            "locations in the raw HTML. Use these to identify the correct "
            "CSS selectors:\n"
            + "\n".join(snippets)
            + "\n"
        )

    @staticmethod
    def _build_refine_prompt(
        spec: dict,
        failed_field_names: list[str],
        extracted_data: dict,
        sanitized_html: str,
        json_ld_context: str = "",
    ) -> str:
        """Build the LLM prompt for selector refinement.

        Includes actual extraction results so the AI can see what each
        field currently produces and identify quality issues (HTML blobs,
        empty values, etc.).
        """

        # Describe all fields with their extraction results
        fields_desc_lines = []
        for name, field_spec in spec.get("fields", {}).items():
            marker = ""
            value_preview = ""
            if name in failed_field_names:
                marker = " <-- NEEDS FIX"
            # Show what the field currently extracts (truncated)
            val = extracted_data.get(name)
            if val is not None:
                val_str = str(val)
                if len(val_str) > 150:
                    val_str = val_str[:150] + "..."
                value_preview = f", extracted='{val_str}'"
            else:
                value_preview = ", extracted=None"
            fields_desc_lines.append(
                f"  - {name}: selector='{field_spec.get('selector', '')}', "
                f"type='{field_spec.get('type', 'css')}', "
                f"multiple={field_spec.get('multiple', False)}{value_preview}{marker}"
            )
        fields_description = "\n".join(fields_desc_lines)

        # Describe only the fields that need fixing
        failed_lines = []
        for name in failed_field_names:
            field_spec = spec.get("fields", {}).get(name, {})
            val = extracted_data.get(name)
            val_str = ""
            if val is not None:
                val_str = str(val)
                if len(val_str) > 200:
                    val_str = val_str[:200] + "..."
                val_str = f", current_value='{val_str}'"
            else:
                val_str = ", current_value=None"
            # Explain why it needs fixing
            reason = "no match found"
            if val is not None:
                val_s = str(val)
                if not val_s.strip():
                    reason = "extracted empty value"
                elif re.search(r"<[a-zA-Z/]", val_s):
                    reason = (
                        "extracted HTML element instead of text — "
                        "use ::text pseudo-element or ::attr() to extract "
                        "text content or attributes"
                    )
                else:
                    reason = "value may be incorrect"
            failed_lines.append(
                f"  - {name}: selector='{field_spec.get('selector', '')}', "
                f"reason: {reason}{val_str}"
            )
        failed_fields_str = "\n".join(failed_lines)

        return REFINE_SPEC_PROMPT.format(
            fields_description=fields_description,
            failed_fields=failed_fields_str,
            html=sanitized_html,
            json_ld_context=json_ld_context,
        )

    @staticmethod
    def _merge_refined_fields(
        original_spec: dict,
        failed_field_names: list[str],
        refined_spec_dict: dict,
    ) -> dict:
        """Merge LLM-suggested alternatives for failed fields into the original spec.

        Only replaces fields that were in the failed list.  All other fields
        (including any new fields the LLM might have added) are left unchanged
        from the original.  The LLM may add entirely new fields -- those are
        also merged in.
        """
        merged = copy.deepcopy(original_spec)
        original_fields = merged.setdefault("fields", {})
        refined_fields = refined_spec_dict.get("fields", {})

        for name, field_spec in refined_fields.items():
            # Replace failed fields with LLM suggestions
            if name in failed_field_names:
                if field_spec.get("selector"):  # Don't merge empty-skip markers
                    original_fields[name] = field_spec
            # Also merge in any genuinely new fields the LLM added
            elif name not in original_fields:
                if field_spec.get("selector"):
                    original_fields[name] = field_spec

        return merged

    async def _check_provider_reachable(self) -> bool:
        """Lightweight reachability check for the configured provider.

        For Ollama, hits ``GET /api/tags`` which is cheap and does
        not load a model.
        """
        settings = get_settings()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                headers: dict[str, str] = {}
                if settings.ollama_token:
                    headers["Authorization"] = (
                        f"Bearer {settings.ollama_token}"
                    )
                resp = await client.get(
                    f"{settings.ollama_base_url.rstrip('/')}/api/tags",
                    headers=headers,
                )
                return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False