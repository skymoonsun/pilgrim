"""AI endpoint — extraction spec generation, verification, and status checks."""

from fastapi import APIRouter

from app.models.enums import ScraperProfile
from app.schemas.ai import (
    AIStatusResponse,
    ExtractionSpecAIRequest,
    ExtractionSpecAIResponse,
    ProxySourceSuggestionRequest,
    ProxySourceSuggestionResponse,
    ProxySourceVerifyRequest,
    ProxySourceVerifyResult,
    RefineSpecChatRequest,
    RefineSpecChatResponse,
    SanitizerSuggestionRequest,
    SanitizerSuggestionResponse,
    SpecVerificationResponse,
    VerifySpecRequest,
)
from app.services.ai_service import AIService

router = APIRouter()


@router.post(
    "/generate-spec",
    response_model=ExtractionSpecAIResponse,
)
async def generate_extraction_spec(
    body: ExtractionSpecAIRequest,
) -> ExtractionSpecAIResponse:
    """Generate an extraction_spec from a URL and natural language description.

    Fetches the page via Scrapling, sanitizes the HTML, and sends it to
    the configured LLM provider (Ollama by default) to produce
    CSS/XPath selectors.
    """
    try:
        profile = ScraperProfile(body.scraper_profile)
    except ValueError:
        profile = ScraperProfile.FETCHER

    service = AIService()
    return await service.generate_extraction_spec(
        url=body.url,
        description=body.description,
        scraper_profile=profile,
        headers=body.headers,
        cookies=body.cookies,
    )


@router.post(
    "/verify-spec",
    response_model=SpecVerificationResponse,
)
async def verify_extraction_spec(
    body: VerifySpecRequest,
) -> SpecVerificationResponse:
    """Verify an extraction spec against a target URL.

    Fetches the page, runs the spec's selectors, and reports which
    fields matched and which failed.  If some fields fail and
    ``max_iterations > 0``, the LLM will suggest alternative selectors
    and the verification loop re-runs until all fields pass or the
    iteration budget is exhausted.
    """
    try:
        profile = ScraperProfile(body.scraper_profile)
    except ValueError:
        profile = ScraperProfile.FETCHER

    service = AIService()
    return await service.verify_extraction_spec(
        url=body.url,
        extraction_spec=body.extraction_spec,
        scraper_profile=profile,
        fetch_options=body.fetch_options,
        max_iterations=body.max_iterations,
        headers=body.headers,
        cookies=body.cookies,
    )


@router.post(
    "/refine-spec",
    response_model=RefineSpecChatResponse,
)
async def refine_spec_chat(
    body: RefineSpecChatRequest,
) -> RefineSpecChatResponse:
    """Chat-based extraction spec refinement with conversation history and multiple URLs.

    Accepts a conversation history, one or more URLs, and the current
    extraction_spec. Fetches each URL, builds context from all pages,
    and asks the LLM to generate or refine the spec based on accumulated
    conversation context.
    """
    try:
        profile = ScraperProfile(body.scraper_profile)
    except ValueError:
        profile = ScraperProfile.FETCHER

    service = AIService()
    return await service.refine_spec_chat(
        messages=body.messages,
        urls=body.urls,
        current_spec=body.current_spec,
        scraper_profile=profile,
        headers=body.headers,
        cookies=body.cookies,
    )


@router.get("/status", response_model=AIStatusResponse)
async def ai_status() -> AIStatusResponse:
    """Check whether AI features are enabled and the provider is reachable."""
    service = AIService()
    return await service.check_status()


@router.post(
    "/suggest-proxy-source",
    response_model=ProxySourceSuggestionResponse,
)
async def suggest_proxy_source(
    body: ProxySourceSuggestionRequest,
) -> ProxySourceSuggestionResponse:
    """Analyze a proxy source URL and suggest configuration.

    Fetches the source content, detects format (raw_text, json, csv, xml),
    and suggests extraction_spec, name, and description.  For raw_text
    format, skips the LLM call and returns heuristic results.
    """
    service = AIService()
    return await service.suggest_proxy_source(url=body.url)


@router.post(
    "/verify-proxy-source",
    response_model=ProxySourceVerifyResult,
)
async def verify_proxy_source(
    body: ProxySourceVerifyRequest,
) -> ProxySourceVerifyResult:
    """Verify a proxy source configuration by fetching and parsing it.

    Fetches the source content, parses it using the given format_type
    and extraction_spec, and returns sample proxies.
    Does not require AI — this is a pure parsing verification.
    """
    service = AIService()
    return await service.verify_proxy_source(
        url=body.url,
        format_type=body.format_type,
        extraction_spec=body.extraction_spec,
    )


@router.post(
    "/suggest-sanitizer",
    response_model=SanitizerSuggestionResponse,
)
async def suggest_sanitizer(
    body: SanitizerSuggestionRequest,
) -> SanitizerSuggestionResponse:
    """Suggest sanitizer rules based on extracted data from a URL.

    Fetches the page, applies the given extraction_spec to get raw data,
    then asks the LLM to suggest appropriate sanitization transforms.
    Returns suggested rules along with before/after sample data.
    """
    try:
        profile = ScraperProfile(body.scraper_profile)
    except ValueError:
        profile = ScraperProfile.FETCHER

    service = AIService()
    return await service.suggest_sanitizer(
        url=body.url,
        extraction_spec=body.extraction_spec,
        description=body.description,
        scraper_profile=profile,
        headers=body.headers,
        cookies=body.cookies,
    )