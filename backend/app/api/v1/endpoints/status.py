"""Status endpoint — lightweight service identity check."""

from fastapi import APIRouter

from app.schemas.status import StatusResponse

router = APIRouter()

_STATUS_RESPONSE = StatusResponse(
    status="ok",
    version="1.0.0",
    service="pilgrim",
)


@router.get("/", response_model=StatusResponse)
async def get_status() -> StatusResponse:
    """Return service status, version and name."""
    return _STATUS_RESPONSE