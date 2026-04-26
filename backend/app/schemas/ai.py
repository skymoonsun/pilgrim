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

    selector: str = Field(..., description="CSS or XPath selector, or JSON path")
    type: Literal["css", "xpath", "json_path"] = Field(
        default="css", description="Selector type"
    )
    multiple: bool = Field(
        default=False,
        description="Whether to extract all matches or just the first",
    )
    source: Literal["next_data", "json_ld"] | None = Field(
        default=None,
        description="Source for json_path type: 'next_data' or 'json_ld'",
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


# ── Verification schemas ─────────────────────────────────────────


class VerifySpecRequest(BaseModel):
    """Request body for extraction spec verification."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Target URL to verify the spec against",
    )
    extraction_spec: dict = Field(
        ...,
        description="Extraction spec to verify (same format as CrawlConfiguration.extraction_spec)",
    )
    scraper_profile: str = Field(
        default="fetcher",
        description="Scraper profile to use for fetching (fetcher, http_session, stealth, dynamic)",
    )
    fetch_options: dict | None = Field(
        default=None,
        description="Optional fetch options passed to the Scrapling fetcher (e.g. timeout, impersonate)",
    )
    max_iterations: int = Field(
        default=2,
        ge=0,
        le=5,
        description="Max LLM refinement iterations (0 = verify only, no LLM repair)",
    )


class FieldVerificationResult(BaseModel):
    """Per-field verification result."""

    field_name: str = Field(..., description="Name of the extraction field")
    matched: bool = Field(..., description="Whether the selector found any matches")
    match_count: int = Field(
        default=0, description="Number of elements matched (0 if none)"
    )
    sample_value: str | None = Field(
        default=None,
        description="First extracted value (truncated), or None if no match",
    )
    selector: str = Field(
        ..., description="The CSS/XPath selector that was tested"
    )
    selector_type: Literal["css", "xpath", "json_path"] = Field(
        default="css", description="Selector type used"
    )
    value_quality: Literal["good", "html", "empty", "none"] = Field(
        default="none",
        description="Quality assessment of the extracted value: "
        "'good' = clean text/attribute, 'html' = contains HTML tags, "
        "'empty' = empty string, 'none' = no match",
    )


# ── Proxy source suggestion schemas ──────────────────────────────


class ProxySourceSuggestionRequest(BaseModel):
    """Request body for AI-powered proxy source analysis."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Proxy list source URL to analyze",
    )


class ProxySourceVerifyRequest(BaseModel):
    """Request body for verifying proxy source parsing configuration."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Proxy list source URL to test",
    )
    format_type: str = Field(
        ...,
        description="Format type: raw_text, json, csv, xml",
    )
    extraction_spec: dict | None = Field(
        None,
        description="Extraction spec for non-raw_text formats",
    )


class ProxySourceVerifyResult(BaseModel):
    """Result of verifying a proxy source configuration."""

    success: bool = Field(
        ..., description="Whether proxies were successfully parsed"
    )
    total_parsed: int = Field(
        ..., description="Total number of proxies parsed"
    )
    sample_proxies: list[dict] = Field(
        default_factory=list,
        description="Sample parsed proxies (up to 10)",
    )
    format_type: str = Field(
        ..., description="Format type used for parsing"
    )
    content_length: int = Field(
        ..., description="Fetched content length in characters"
    )
    suggested_max_proxies: int | None = Field(
        None, description="Suggested max_proxies value if total > 500"
    )
    error: str | None = Field(
        None, description="Error message if parsing failed"
    )


class ProxySourceSuggestionSchema(BaseModel):
    """LLM structured output schema for proxy source suggestions."""

    format_type: str = Field(
        ...,
        description="One of: raw_text, json, csv, xml",
    )
    extraction_spec: dict | None = Field(
        None,
        description="Extraction spec for non-raw_text formats",
    )
    suggested_name: str = Field(
        ...,
        description="Short descriptive name for this source",
    )
    description: str = Field(
        ...,
        description="Brief description of what this source provides",
    )


class ProxySourceSuggestionResponse(BaseModel):
    """Response from the AI proxy source suggestion endpoint."""

    format_type: str = Field(..., description="Detected format type")
    extraction_spec: dict | None = Field(
        None, description="Suggested extraction spec (null for raw_text)"
    )
    suggested_name: str = Field(..., description="Suggested source name")
    description: str = Field(..., description="Source description")
    sample_proxies: list[dict] = Field(
        default_factory=list,
        description="Sample proxies parsed from the content",
    )
    total_detected: int = Field(
        default=0, description="Total number of proxies detected in full content"
    )
    suggested_max_proxies: int | None = Field(
        None, description="Suggested max_proxies value if total > 500"
    )
    model_used: str = Field(..., description="LLM model used (or 'heuristic' for raw_text)")
    content_length: int = Field(..., description="Fetched content length in characters")


class SpecVerificationResponse(BaseModel):
    """Response from the spec verification endpoint."""

    valid: bool = Field(
        ..., description="True if every field matched at least one element"
    )
    total_fields: int = Field(..., description="Total number of fields in the spec")
    passed_fields: int = Field(
        ..., description="Fields that matched at least one element"
    )
    failed_fields: list[str] = Field(
        default_factory=list,
        description="Field names whose selectors returned no results",
    )
    field_results: list[FieldVerificationResult] = Field(
        default_factory=list, description="Per-field verification details"
    )
    extracted_data: dict = Field(
        default_factory=dict,
        description="Actual extraction output: field_name -> extracted value(s)",
    )
    refined_spec: dict | None = Field(
        default=None,
        description="Updated extraction_spec with LLM-suggested alternatives "
        "for failed fields, or None if no refinement was needed/performed",
    )
    iterations_performed: int = Field(
        default=0, description="Number of LLM refinement iterations performed"
    )
    model_used: str | None = Field(
        default=None, description="LLM model used for refinement, if any"
    )
    page_warning: str | None = Field(
        default=None,
        description="Warning about page fetching issues (e.g. empty page, JS-rendered content)",
    )


# ── Sanitizer suggestion schemas ─────────────────────────────────


class SanitizerSuggestionRequest(BaseModel):
    """Request body for AI-powered sanitizer rule generation."""

    url: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Target URL to extract sample data from",
    )
    extraction_spec: dict = Field(
        ...,
        description="Extraction spec to use for extracting sample data",
    )
    description: str | None = Field(
        None,
        max_length=2000,
        description="What kind of sanitization is needed (e.g. 'clean up prices, remove currency symbols')",
    )
    scraper_profile: str = Field(
        default="fetcher",
        description="Scraper profile to use for fetching",
    )


class SanitizerSuggestionSchema(BaseModel):
    """LLM structured output schema for sanitizer suggestions."""

    rules: list[dict] = Field(
        ...,
        description="List of sanitizer rules, each with 'field' and 'transforms' keys",
    )


class SanitizerSuggestionResponse(BaseModel):
    """Response from the AI sanitizer suggestion endpoint."""

    rules: list[dict] = Field(
        ..., description="Suggested sanitizer rules"
    )
    sample_before: dict | None = Field(
        default=None,
        description="Extracted data before sanitization",
    )
    sample_after: dict | None = Field(
        default=None,
        description="Extracted data after applying suggested rules",
    )
    model_used: str = Field(
        ..., description="LLM model that produced the suggestion"
    )