"""
Correlation ID Middleware for Agentium - Section 14.6
Generates and propagates request_id across HTTP → Celery → WebSocket for distributed tracing.
"""

import uuid
import logging
from contextlib import contextmanager
from typing import Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from backend.services.structured_logging import (
    request_id_var,
    set_request_id,
    get_request_id,
    clear_context,
)

logger = logging.getLogger(__name__)

# Header name for correlation ID
CORRELATION_HEADER = "X-Request-ID"
CORRELATION_HEADER_ALT = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware that generates or extracts a correlation ID (request_id) for each request
    and makes it available via contextvars for structured logging.

    The request_id is:
    1. Extracted from incoming headers (X-Request-ID or X-Correlation-ID)
    2. Generated if not present
    3. Added to response headers for client-side tracing
    4. Available in contextvars for structured logging throughout the request lifecycle
    """

    def __init__(
        self,
        app: ASGIApp,
        header_name: str = CORRELATION_HEADER,
        generator: callable = None,
    ):
        super().__init__(app)
        self.header_name = header_name
        self.generator = generator or (lambda: str(uuid.uuid4())[:12])

    async def dispatch(self, request: Request, call_next):
        # Extract or generate request_id
        request_id = request.headers.get(self.header_name) or request.headers.get(CORRELATION_HEADER_ALT)

        if not request_id:
            request_id = self.generator()

        # Set in contextvar for this request's lifecycle
        token = request_id_var.set(request_id)

        try:
            # Process request
            response = await call_next(request)

            # Add correlation ID to response headers
            response.headers[self.header_name] = request_id

            return response
        finally:
            # Clean up contextvar
            request_id_var.reset(token)


def get_correlation_id() -> str:
    """Get the current correlation ID, generating one if needed."""
    return get_request_id()


def set_correlation_id(correlation_id: str) -> None:
    """Set the correlation ID for the current context."""
    set_request_id(correlation_id)


class WebSocketCorrelationManager:
    """
    Manages correlation IDs for WebSocket connections.
    WebSocket connections can be long-lived, so we need to track
    correlation IDs per connection and per message.
    """

    def __init__(self):
        self._connection_contexts: dict = {}  # websocket -> request_id

    def set_connection_context(self, websocket, request_id: str):
        """Set the correlation context for a WebSocket connection."""
        self._connection_contexts[id(websocket)] = request_id

    def get_connection_context(self, websocket) -> Optional[str]:
        """Get the correlation ID for a WebSocket connection."""
        return self._connection_contexts.get(id(websocket))

    def clear_connection_context(self, websocket):
        """Clear the correlation context for a WebSocket connection."""
        self._connection_contexts.pop(id(websocket), None)

    @contextmanager
    def message_context(self, websocket, message_request_id: Optional[str] = None):
        """
        Context manager for handling a WebSocket message with correlation.
        Uses the message's request_id if provided, otherwise falls back to connection's.
        """
        connection_request_id = self.get_connection_context(websocket)
        request_id = message_request_id or connection_request_id or get_correlation_id()

        token = request_id_var.set(request_id)
        try:
            yield request_id
        finally:
            request_id_var.reset(token)


# Global instance for WebSocket correlation management
ws_correlation_manager = WebSocketCorrelationManager()


# Celery task correlation helpers
def extract_correlation_from_task_kwargs(kwargs: dict) -> tuple:
    """
    Extract correlation IDs from Celery task kwargs.
    Returns (request_id, task_id, agent_id)
    """
    request_id = kwargs.pop("_request_id", None)
    task_id = kwargs.pop("_task_id", None)
    agent_id = kwargs.pop("_agent_id", None)
    return request_id, task_id, agent_id


def inject_correlation_into_task_kwargs(
    kwargs: dict,
    request_id: Optional[str] = None,
    task_id: Optional[str] = None,
    agent_id: Optional[str] = None,
) -> dict:
    """
    Inject correlation IDs into Celery task kwargs for propagation.
    """
    if request_id:
        kwargs["_request_id"] = request_id
    if task_id:
        kwargs["_task_id"] = task_id
    if agent_id:
        kwargs["_agent_id"] = agent_id
    return kwargs