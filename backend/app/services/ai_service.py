"""AI-powered extraction spec generation service.

Orchestrates the full pipeline:
1. Fetch the target page HTML via Scrapling (same fetcher as crawl jobs).
2. Sanitize the HTML for LLM consumption.
3. Build a structured prompt.
4. Call the configured LLM provider (Ollama by default).
5. Validate the returned extraction spec.
6. Return the result.
"""

from __future__ import annotations

import logging

import httpx

from app.core.config import get_settings
from app.core.exceptions import (
    AIDisabledError,
    AIEmptySpecError,
    AIInvalidPageError,
)
from app.crawlers.html_sanitizer import sanitize_html
from app.integrations.llm_base import LLMProvider, create_llm_provider
from app.models.enums import ScraperProfile
from app.schemas.ai import (
    AIStatusResponse,
    ExtractionSpecAIResponse,
    ExtractionSpecSchema,
)

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = (
    "You are a web scraping expert. You MUST respond with ONLY valid JSON — "
    "no explanation, no markdown, no code fences, no conversational text. "
    "Your entire response must be a single JSON object that conforms to the "
    "schema provided. Never include any text before or after the JSON."
)

_PROMPT_TEMPLATE = """\
Given the following HTML from a web page, generate an extraction specification.

The extraction spec must be a JSON object with this exact structure:
{{
  "fields": {{
    "<field_name>": {{
      "selector": "<CSS or XPath selector>",
      "type": "css" or "xpath",
      "multiple": true or false
    }}
  }}
}}

Rules:
- Use CSS selectors by default (type: "css"). Use XPath only when CSS cannot express the selection.
- Set "multiple": true when the field should capture all matching elements (e.g. list of prices, images).
- Keep selectors concise and robust — prefer semantic classes and IDs over deep DOM paths.
- Every field name must be a snake_case identifier.
- You MUST respond with ONLY the JSON object. No other text.

What to extract:
{description}

HTML:
{html}

JSON response:"""


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

        # 2. Sanitize
        sanitized = sanitize_html(html)

        # 3. Truncate to max size
        max_chars = settings.ai_max_html_chars
        if len(sanitized) > max_chars:
            logger.info(
                "Sanitized HTML truncated: %d → %d chars",
                len(sanitized),
                max_chars,
            )
            sanitized = sanitized[:max_chars]

        # 4. Build prompt
        prompt = _PROMPT_TEMPLATE.format(
            description=description, html=sanitized
        )

        # 5. Call LLM with structured output
        provider = await self._get_provider()
        result: ExtractionSpecSchema = await provider.generate(  # type: ignore[assignment]
            prompt=prompt,
            schema=ExtractionSpecSchema,
            system=_SYSTEM_PROMPT,
        )

        # 6. Validate
        self._validate_spec(result)

        return ExtractionSpecAIResponse(
            extraction_spec=result.model_dump(),
            model_used=getattr(provider, "_model", "unknown"),
            html_length=len(html),
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

        # Scrapling Adaptor exposes the page HTML via the ``html`` attr
        html: str = getattr(response, "html", "")
        if not html:
            # Fallback: some Scrapling versions use different attr names
            html = str(response)

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