# backend/core/correlation_middleware.py
import uuid
import contextvars
from contextlib import contextmanager
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.websockets import WebSocket

from backend.services.structured_logging import set_request_id, get_request_id, request_id_var


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Extract or generate request_id, propagate via contextvar and response header."""

    HEADER_NAME = "X-Request-ID"
    FALLBACK_HEADER = "X-Correlation-ID"

    async def dispatch(self, request: Request, call_next):
        # Extract or generate: X-Request-ID first, then X-Correlation-ID, then generate
        request_id = (
            request.headers.get(self.HEADER_NAME)
            or request.headers.get(self.FALLBACK_HEADER)
            or str(uuid.uuid4())[:12]
        )

        # Set contextvar for structured logging
        set_request_id(request_id)

        # Process request
        response = await call_next(request)

        # Echo back in response
        response.headers[self.HEADER_NAME] = request_id
        return response


# WebSocket correlation ID manager for propagating request_id across WebSocket messages
class WSCorrelationManager:
    """Manage correlation IDs for WebSocket connections."""

    # Store request_id per WebSocket connection
    _connection_context: dict = {}

    def set_connection_context(self, websocket: WebSocket, request_id: str | None):
        """Set the correlation ID for a WebSocket connection."""
        if request_id:
            self._connection_context[id(websocket)] = request_id
            set_request_id(request_id)

    def clear_connection_context(self, websocket: WebSocket):
        """Clear the correlation ID for a WebSocket connection."""
        ws_id = id(websocket)
        if ws_id in self._connection_context:
            del self._connection_context[ws_id]

    def get_connection_context(self, websocket: WebSocket) -> str | None:
        """Get the correlation ID for a WebSocket connection."""
        return self._connection_context.get(id(websocket))

    @contextmanager
    def message_context(self, websocket: WebSocket, message_request_id: str | None = None):
        """Context manager for handling a single WebSocket message with correlation ID."""
        # Use message-provided request_id, fallback to connection context, fallback to new
        request_id = message_request_id or self.get_connection_context(websocket)
        if not request_id:
            request_id = str(uuid.uuid4())[:12]

        # Save old context
        old_request_id = request_id_var.get()

        try:
            # Set new context
            set_request_id(request_id)
            # Update connection context so subsequent messages in this connection use it
            self._connection_context[id(websocket)] = request_id
            yield request_id
        finally:
            # Restore old context
            set_request_id(old_request_id) if old_request_id else request_id_var.set(None)


# Global instance for WebSocket correlation management
ws_correlation_manager = WSCorrelationManager()


# Celery task correlation helpers
def inject_correlation_into_task_kwargs(
    kwargs: dict,
    request_id: str | None = None,
    task_id: str | None = None,
    agent_id: str | None = None,
) -> None:
    """Inject correlation IDs into Celery task kwargs for propagation.

    Args:
        kwargs: The task kwargs dict to modify (in-place).
        request_id: Request correlation ID to propagate.
        task_id: Task ID for tracking.
        agent_id: Agent ID for tracking.
    """
    if request_id:
        kwargs["_request_id"] = request_id
    if task_id:
        kwargs["_task_id"] = task_id
    if agent_id:
        kwargs["_agent_id"] = agent_id


def extract_correlation_from_task_kwargs(kwargs: dict) -> tuple[str | None, str | None, str | None]:
    """Extract correlation IDs from Celery task kwargs.

    Args:
        kwargs: The task kwargs dict (can be a copy to avoid mutation).

    Returns:
        Tuple of (request_id, task_id, agent_id).
    """
    request_id = kwargs.get("_request_id")
    task_id = kwargs.get("_task_id")
    agent_id = kwargs.get("_agent_id")
    return request_id, task_id, agent_id