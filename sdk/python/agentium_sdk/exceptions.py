"""
Custom exception hierarchy for the Agentium SDK.

All exceptions inherit from AgentiumError so callers can catch
a single base class or be more specific.
"""


class AgentiumError(Exception):
    """Base exception for all Agentium SDK errors."""

    def __init__(self, message: str, status_code: int | None = None, detail: dict | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail or {}


class AuthenticationError(AgentiumError):
    """Raised when authentication fails (401)."""

    def __init__(self, message: str = "Authentication failed", detail: dict | None = None):
        super().__init__(message, status_code=401, detail=detail)


class AuthorizationError(AgentiumError):
    """Raised when the user lacks permission (403)."""

    def __init__(self, message: str = "Insufficient permissions", detail: dict | None = None):
        super().__init__(message, status_code=403, detail=detail)


class ConstitutionalViolationError(AgentiumError):
    """Raised when an action violates the Agentium Constitution."""

    def __init__(self, message: str = "Constitutional violation", detail: dict | None = None):
        super().__init__(message, status_code=403, detail=detail)


class NotFoundError(AgentiumError):
    """Raised when a requested resource does not exist (404)."""

    def __init__(self, message: str = "Resource not found", detail: dict | None = None):
        super().__init__(message, status_code=404, detail=detail)


class RateLimitError(AgentiumError):
    """Raised when the API rate limit is exceeded (429)."""

    def __init__(self, message: str = "Rate limit exceeded", retry_after: float | None = None, detail: dict | None = None):
        super().__init__(message, status_code=429, detail=detail)
        self.retry_after = retry_after


class ValidationError(AgentiumError):
    """Raised when request validation fails (422)."""

    def __init__(self, message: str = "Validation error", detail: dict | None = None):
        super().__init__(message, status_code=422, detail=detail)


class ServerError(AgentiumError):
    """Raised when the Agentium server returns a 5xx error."""

    def __init__(self, message: str = "Server error", status_code: int = 500, detail: dict | None = None):
        super().__init__(message, status_code=status_code, detail=detail)
