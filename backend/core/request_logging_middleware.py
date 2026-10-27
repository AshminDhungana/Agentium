"""
Request Logging Middleware for Agentium - Observability (Phase 21.4).

Logs incoming HTTP requests with correlation IDs for structured observability.
"""

import logging
import time
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.services.structured_logging import get_structured_logger, request_id_var

logger = get_structured_logger("request_logging")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log incoming requests with correlation IDs and timing."""

    # Paths to skip logging (health checks, metrics, static files)
    SKIP_PATHS = {
        "/health",
        "/healthz",
        "/ready",
        "/readyz",
        "/api/health",
        "/api/v1/metrics",
        "/ws",
        "/static",
        "/docs",
        "/openapi.json",
        "/favicon",
        "/metrics",
        "/.well-known",
    }

    def _should_skip(self, path: str) -> bool:
        """Check if path should be skipped."""
        for skip_path in self.SKIP_PATHS:
            if path.startswith(skip_path):
                return True
        return False

    async def dispatch(self, request: Request, call_next):
        # Skip logging for certain paths
        if self._should_skip(request.url.path):
            return await call_next(request)

        # Get correlation ID from contextvar (set by CorrelationIdMiddleware)
        request_id = request_id_var.get()

        start_time = time.perf_counter()

        # Log request start
        logger.info(
            f"Request started: {request.method} {request.url.path}",
            step="request_start",
            method=request.method,
            path=request.url.path,
            status="started",
        )

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request completion
            logger.info(
                f"Request completed: {request.method} {request.url.path} - {response.status_code}",
                step="request_end",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
                status="completed",
            )

            return response
        except Exception as e:
            duration_ms = (time.perf_counter() - start_time) * 1000

            # Log request error
            logger.error(
                f"Request failed: {request.method} {request.url.path} - {type(e).__name__}: {e}",
                step="request_error",
                method=request.method,
                path=request.url.path,
                error_type=type(e).__name__,
                error_message=str(e),
                duration_ms=duration_ms,
                status="failed",
            )
            raise