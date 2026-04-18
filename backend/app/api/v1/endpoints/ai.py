"""AI endpoint — extraction spec generation, verification, and status checks."""

from fastapi import APIRouter

from app.models.enums import ScraperProfile
from app.schemas.ai import (
    AIStatusResponse,
    ExtractionSpecAIRequest,
    ExtractionSpecAIResponse,
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
    )


@router.get("/status", response_model=AIStatusResponse)
async def ai_status() -> AIStatusResponse:
    """Check whether AI features are enabled and the provider is reachable."""
    service = AIService()
    return await service.check_status()