"""Status endpoint response schemas."""

from pydantic import BaseModel


class StatusResponse(BaseModel):
    """Response model for the service status endpoint."""

    status: str
    version: str
    service: str