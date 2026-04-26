"""Sanitizer config schemas (create / update / response)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import TransformType


class TransformRule(BaseModel):
    """A single transform operation applied to a field value."""

    type: TransformType = Field(..., description="Transform type")
    pattern: str | None = Field(
        None, description="Regex pattern (regex_replace) or separator (split_take)"
    )
    replacement: str | None = Field(
        None, description="Replacement string (regex_replace)"
    )
    value: str | None = Field(
        None, description="Default value (default) or string to trim (trim_prefix/trim_suffix)"
    )
    index: int | None = Field(
        None, description="Index to take after split (split_take)"
    )


class FieldSanitizer(BaseModel):
    """Rules for sanitizing a single extracted field."""

    field: str = Field(..., min_length=1, description="Extraction spec field name")
    transforms: list[TransformRule] = Field(
        default_factory=list, description="Ordered list of transforms"
    )


class SanitizerConfigCreate(BaseModel):
    """Payload for creating a new sanitizer config."""

    name: str = Field(..., min_length=1, max_length=100, description="Unique name")
    description: str | None = Field(None, max_length=2000)
    is_active: bool = True
    rules: list[FieldSanitizer] = Field(default_factory=list)


class SanitizerConfigUpdate(BaseModel):
    """Payload for partially updating a sanitizer config."""

    name: str | None = Field(None, min_length=1, max_length=100)
    description: str | None = None
    is_active: bool | None = None
    rules: list[FieldSanitizer] | None = None


class SanitizerConfigResponse(BaseModel):
    """Single sanitizer config response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    description: str | None
    is_active: bool
    rules: list[FieldSanitizer]
    created_at: datetime
    updated_at: datetime


class SanitizerConfigListResponse(BaseModel):
    """Paginated list of sanitizer configs."""

    items: list[SanitizerConfigResponse]
    total: int