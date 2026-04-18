"""Custom application exceptions.

Each exception carries a machine-readable ``code`` used by the global
error handler to select an HTTP status.
"""


class AppException(Exception):
    """Base application exception."""

    def __init__(self, message: str, code: str | None = None) -> None:
        self.message = message
        self.code = code
        super().__init__(self.message)


class ConfigNotFoundError(AppException):
    """Raised when a crawl configuration is not found."""

    def __init__(self, config_id: str) -> None:
        super().__init__(
            f"CrawlConfiguration with ID {config_id} not found",
            "CONFIG_NOT_FOUND",
        )


class JobNotFoundError(AppException):
    """Raised when a crawl job is not found."""

    def __init__(self, job_id: str) -> None:
        super().__init__(
            f"CrawlJob with ID {job_id} not found",
            "JOB_NOT_FOUND",
        )


class CrawlingError(AppException):
    """Raised when a crawling operation fails."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"Failed to crawl {url}: {reason}",
            "CRAWLING_ERROR",
        )


class RateLimitExceededError(AppException):
    """Raised when rate limits are exceeded."""

    def __init__(self, domain: str, retry_after: int) -> None:
        super().__init__(
            f"Rate limit exceeded for {domain}. Retry after {retry_after}s",
            "RATE_LIMIT_EXCEEDED",
        )
        self.retry_after = retry_after


class ExtractionError(AppException):
    """Raised when data extraction from a page fails."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"Extraction failed for {url}: {reason}",
            "EXTRACTION_ERROR",
        )


class ScheduleNotFoundError(AppException):
    """Raised when a crawl schedule is not found."""

    def __init__(self, schedule_id: str) -> None:
        super().__init__(
            f"CrawlSchedule with ID {schedule_id} not found",
            "SCHEDULE_NOT_FOUND",
        )


# ── AI / LLM exceptions ────────────────────────────────────────


class AIDisabledError(AppException):
    """Raised when AI features are requested but not enabled."""

    def __init__(self) -> None:
        super().__init__(
            "AI features are disabled. Set PILGRIM_AI_ENABLED=true to enable.",
            "AI_DISABLED",
        )


class AILLMError(AppException):
    """Raised when the LLM provider returns an error."""

    def __init__(self, provider: str, reason: str) -> None:
        super().__init__(
            f"LLM provider '{provider}' error: {reason}",
            "AI_LLM_ERROR",
        )


class AIConnectionError(AppException):
    """Raised when the LLM provider is unreachable."""

    def __init__(self, provider: str, url: str) -> None:
        super().__init__(
            f"Cannot reach LLM provider '{provider}' at {url}",
            "AI_CONNECTION_ERROR",
        )


class AIInvalidPageError(AppException):
    """Raised when the target URL does not return HTML."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(
            f"Invalid page at {url}: {reason}",
            "AI_INVALID_PAGE",
        )


class AIEmptySpecError(AppException):
    """Raised when the LLM returns an empty extraction spec."""

    def __init__(self) -> None:
        super().__init__(
            "LLM returned an empty extraction spec",
            "AI_EMPTY_SPEC",
        )


class AIVerificationError(AppException):
    """Raised when spec verification fails due to a non-recoverable error."""

    def __init__(self, reason: str) -> None:
        super().__init__(
            f"Spec verification failed: {reason}",
            "AI_VERIFICATION_ERROR",
        )
