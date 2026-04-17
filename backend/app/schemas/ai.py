"""AI feature schemas (request / response / LLM structured output)."""

from typing import Literal

from pydantic import BaseModel, Field


# ── Request ─────────────────────────────────────────────────────


class ExtractionSpecAIRequest(BaseModel):
    """Request body for AI-generated extraction spec."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Target URL to analyze",
    )
    description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Natural language description of what data to extract",
    )
    scraper_profile: str = Field(
        default="fetcher",
        description="Scraper profile to use for fetching (fetcher, http_session, stealth, dynamic)",
    )


# ── LLM structured output schema ────────────────────────────────


class ExtractionFieldSpec(BaseModel):
    """A single field extraction rule produced by the LLM."""

    selector: str = Field(..., description="CSS or XPath selector")
    type: Literal["css", "xpath"] = Field(
        default="css", description="Selector type"
    )
    multiple: bool = Field(
        default=False,
        description="Whether to extract all matches or just the first",
    )


class ExtractionSpecSchema(BaseModel):
    """Structured output schema the LLM must conform to.

    This shape is intentionally identical to the ``extraction_spec``
    JSONB format consumed by ``extract_data()`` in
    ``app.crawlers.extraction``.
    """

    fields: dict[str, ExtractionFieldSpec] = Field(
        ...,
        description="Mapping of field names to extraction rules",
    )


# ── Response ────────────────────────────────────────────────────


class ExtractionSpecAIResponse(BaseModel):
    """Response from the AI spec generation endpoint."""

    extraction_spec: dict = Field(
        ...,
        description="Generated extraction_spec compatible with CrawlConfiguration",
    )
    model_used: str = Field(
        ..., description="LLM model that produced the spec"
    )
    html_length: int = Field(
        ..., description="Original HTML size in characters"
    )
    sanitized_length: int = Field(
        ..., description="Sanitized HTML size in characters"
    )


class AIStatusResponse(BaseModel):
    """AI feature availability check."""

    enabled: bool
    provider: str | None
    reachable: bool