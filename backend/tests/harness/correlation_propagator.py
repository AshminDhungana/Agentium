"""Correlation propagator for request_id tracking across HTTP, Celery, and WebSocket."""

import contextvars
from dataclasses import dataclass
from typing import Dict, Any, Optional
import uuid


# Context variable for request_id propagation
_request_id_var: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar('request_id', default=None)


@dataclass
class CorrelationContext:
    """Context carrying correlation information."""
    request_id: str
    trace_id: Optional[str] = None
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    metadata: Dict[str, Any] = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class CorrelationPropagator:
    """Manages request_id propagation across service boundaries."""

    def __init__(self):
        self._context: Optional[CorrelationContext] = None

    def inject_http_request(self, request_id: Optional[str] = None) -> str:
        """Inject correlation ID into HTTP request context."""
        if request_id is None:
            request_id = str(uuid.uuid4())

        self._context = CorrelationContext(request_id=request_id)
        _request_id_var.set(request_id)
        return request_id

    def extract_http_request(self) -> Optional[str]:
        """Extract correlation ID from HTTP request context."""
        return _request_id_var.get()

    def inject_celery_task(self, request_id: str):
        """Inject correlation ID into Celery task context."""
        _request_id_var.set(request_id)
        if self._context:
            self._context.request_id = request_id

    def extract_celery_context(self) -> Dict[str, Any]:
        """Extract correlation context for Celery task."""
        request_id = _request_id_var.get()
        return {
            "request_id": request_id,
            "trace_id": self._context.trace_id if self._context else None,
            "span_id": self._context.span_id if self._context else None,
        }

    def create_ws_event(self, event_type: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """Create WebSocket event with correlation ID."""
        request_id = _request_id_var.get() or (self._context.request_id if self._context else None)
        return {
            "type": event_type,
            "request_id": request_id,
            "data": data,
            "timestamp": uuid.uuid4().time  # Approximate
        }

    def inject_message_bus(self, request_id: str):
        """Inject correlation ID for MessageBus publish."""
        _request_id_var.set(request_id)

    def extract_message_bus(self) -> Optional[str]:
        """Extract correlation ID from MessageBus context."""
        return _request_id_var.get()

    def get_current_context(self) -> Optional[CorrelationContext]:
        """Get current correlation context."""
        return self._context

    def clear(self):
        """Clear correlation context."""
        self._context = None
        _request_id_var.set(None)


def get_current_request_id() -> Optional[str]:
    """Get the current request ID from context."""
    return _request_id_var.get()


def set_current_request_id(request_id: str):
    """Set the current request ID in context."""
    _request_id_var.set(request_id)