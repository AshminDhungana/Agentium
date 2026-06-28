"""
Timing Middleware for Agentium — Performance Regression Gate (Phase 18.2).

Captures per-endpoint request latency with fixed-size ring buffers, then
computes avg / p95 / p99.  Pure-Python (no numpy) so it remains a zero-cost
dependency for production deployments.

The middleware is **opt-in**; if the singleton is never registered the app
behaves identically except for the missing ``GET /api/v1/metrics`` endpoint.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Dict

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Internal ring-buffer storage (thread-safe, no external deps)
# ──────────────────────────────────────────────────────────────────────────────

# Sentinel that marks "skip this request"
_SKIP_TIMING = object()

# Skip patterns — static files, health, websocket, favicon, etc.
# These are path prefixes; any request whose path starts with one of them
# is excluded from timing collection (keeps the buffer focused on useful traffic).
_SKIP_PREFIXES = (
    "/health",
    "/api/health",
    "/api/v1/metrics",
    "/ws",
    "/static",
    "/docs",
    "/openapi.json",
    "/favicon",
    "/metrics",
    "/.well-known",
)


class _TimingStore:
    """Thread-safe per-endpoint latency ring buffer with percentile helpers."""

    def __init__(self, *, max_samples: int = 10_000) -> None:
        self._lock = threading.Lock()
        self._max_samples = max_samples
        # Lock-protected shared state:
        self._buffers: Dict[str, deque[float]] = {}
        self._total_counts: Dict[str, int] = {}

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------
    def record(self, endpoint: str, latency_ms: float) -> None:
        """Append a single sample. Thread-safe."""
        with self._lock:
            if endpoint not in self._buffers:
                self._buffers[endpoint] = deque(maxlen=self._max_samples)
                self._total_counts[endpoint] = 0
            self._buffers[endpoint].append(latency_ms)
            self._total_counts[endpoint] += 1

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------
    def stats(self) -> Dict[str, Any]:
        """Return computed stats for every endpoint seen so far."""
        with self._lock:
            # Copy the data to avoid holding the lock during sort/arith
            buffers = {k: list(v) for k, v in self._buffers.items()}
            counts = dict(self._total_counts)

        result: Dict[str, Any] = {}
        for endpoint, samples in buffers.items():
            n = len(samples)
            total = counts[endpoint]
            if n == 0:
                continue
            sorted_samples = sorted(samples)
            avg = sum(sorted_samples) / n
            p95 = _percentile(sorted_samples, 0.95)
            p99 = _percentile(sorted_samples, 0.99)
            min_val = sorted_samples[0]
            max_val = sorted_samples[-1]
            result[endpoint] = {
                "count": total,
                "buffered": n,
                "avg_ms": round(avg, 3),
                "p95_ms": round(p95, 3),
                "p99_ms": round(p99, 3),
                "min_ms": round(min_val, 3),
                "max_ms": round(max_val, 3),
            }
        return result

    # ------------------------------------------------------------------
    # Helpers / lifecycle
    # ------------------------------------------------------------------
    def clear(self) -> None:
        """Reset all stored data. Mostly useful for test isolation."""
        with self._lock:
            self._buffers.clear()
            self._total_counts.clear()


def _percentile(sorted_data: list[float], q: float) -> float:
    """
    Return the percentile ``q`` of *sorted_data* (0 ≤ q ≤ 1).
    Uses the standard nearest-rank method for simplicity.  Pure Python.
    """
    n = len(sorted_data)
    if n == 0:  # pragma: no cover
        return 0.0
    if n == 1:
        return sorted_data[0]
    rank = (n - 1) * q
    lower = int(rank)
    frac = rank - lower
    if lower + 1 < n:
        return sorted_data[lower] + frac * (sorted_data[lower + 1] - sorted_data[lower])
    return sorted_data[lower]


def _should_skip(path: str) -> bool:
    """Return True if this request should not be timed."""
    for prefix in _SKIP_PREFIXES:
        if path.startswith(prefix):
            return True
    return False


# ──────────────────────────────────────────────────────────────────────────────
# Singleton store — shared between middleware and the API route via this module
# ──────────────────────────────────────────────────────────────────────────────

_timing_store = _TimingStore()


def get_timing_stats() -> Dict[str, Any]:
    """Return the current timing statistics snapshot."""
    return _timing_store.stats()


def clear_timing_stats() -> None:
    """Reset all timing data."""
    _timing_store.clear()


# ──────────────────────────────────────────────────────────────────────────────
# Middleware
# ──────────────────────────────────────────────────────────────────────────────

class TimingMiddleware(BaseHTTPMiddleware):
    """
    Starlette middleware that measures total request latency per endpoint.

    Execution order note (Starlette applies ``add_middleware`` in REVERSE):
    Register this middleware **last** so it wraps everything and its
    ``await call_next()`` covers the full request lifecycle including all
    security, rate-limiting, routing, and exception handling.
    """

    def __init__(self, app, *, max_samples: int = 10_000) -> None:  # noqa: D401
        super().__init__(app)
        self._store = _timing_store
        self._max_samples = max_samples

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        if _should_skip(request.url.path):
            return await call_next(request)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000
            endpoint_key = f"{request.method} {request.url.path}"
            self._store.record(endpoint_key, elapsed_ms)

        # Add per-request timing header for client-side observability
        # (only when the caller asks for it; no body read here)
        if hasattr(response, "headers"):
            response.headers["X-Response-Time-Ms"] = f"{elapsed_ms:.3f}"
        return response
