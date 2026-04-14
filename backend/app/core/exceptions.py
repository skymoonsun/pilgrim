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
