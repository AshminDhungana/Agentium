"""Typed HTTP exceptions for Agentium.

All service / route layer code raises one of the classes below instead of a bare :class:`fastapi.HTTPException`.
The global exception handler (registered in :mod:`backend.main` by calling :func:`register_error_handlers`)
serialises them into the uniform ``{error, code, detail}`` envelope.
"""

from fastapi import HTTPException, status


class AgentiumError(HTTPException):
    """Base typed exception.

    Args:
        error: Human-readable description of what went wrong.
        code:  Machine-readable error code (e.g. ``NOT_FOUND``, ``RATE_LIMITED``).
        detail: Optional structured data (validation errors, retry-after, etc.).
        headers: Optional HTTP headers to attach to the response.
    """

    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR

    def __init__(self, error: str, code: str, detail: dict | None = None, headers: dict | None = None):
        self._error = error
        self._code = code
        self._detail = detail
        # Build the wrapped dict that FastAPI's default handler will render as the response body.
        super().__init__(status_code=self.status_code, detail=error, headers=headers)

    @property
    def error(self) -> str:
        return self._error

    @property
    def code(self) -> str:
        return self._code


class BadRequestError(AgentiumError):
    status_code = status.HTTP_400_BAD_REQUEST


class UnauthorizedError(AgentiumError):
    status_code = status.HTTP_401_UNAUTHORIZED


class ForbiddenError(AgentiumError):
    status_code = status.HTTP_403_FORBIDDEN


class NotFoundError(AgentiumError):
    status_code = status.HTTP_404_NOT_FOUND


class ConflictError(AgentiumError):
    status_code = status.HTTP_409_CONFLICT


class TooLargeError(AgentiumError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE


class RateLimitError(AgentiumError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS


class InternalServerError(AgentiumError):
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR


class ServiceUnavailableError(AgentiumError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE


class LocalSTTError(Exception):
    """Local whisper.cpp STT failed (binary/model missing, crash, timeout).

    Internal — not an HTTP error. The caller's fallback chain converts it
    into a user-facing signal.
    """


class ServerSTTUnavailable(ServiceUnavailableError):
    """No server-side STT engine (whisper.cpp nor OpenAI) is available.

    The frontend should fall back to the browser-native Web Speech API.
    Rendered by the global handler as HTTP 503 with code STT_UNAVAILABLE.
    """


class ProviderUnavailableError(ServiceUnavailableError):
    """A specific provider (TTS, STT, etc.) is unavailable.
    
    Used for multi-provider fallback logic. The caller should try the next
    available provider in the chain.
    
    Rendered by the global handler as HTTP 503 with the specific provider error code.
    """
