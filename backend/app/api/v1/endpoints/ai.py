"""AI endpoint — extraction spec generation and status checks."""

from fastapi import APIRouter

from app.models.enums import ScraperProfile
from app.schemas.ai import (
    AIStatusResponse,
    ExtractionSpecAIRequest,
    ExtractionSpecAIResponse,
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


@router.get("/status", response_model=AIStatusResponse)
async def ai_status() -> AIStatusResponse:
    """Check whether AI features are enabled and the provider is reachable."""
    service = AIService()
    return await service.check_status()