"""Failure injection utilities for integration tests."""
import contextlib
from typing import Any, Callable, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import httpx


class FailureSimulator:
    """Context managers to inject failures at key seams."""

    @contextlib.contextmanager
    def patch_http(
        self,
        *,
        return_value: Optional[httpx.Response] = None,
        side_effect: Optional[Exception] = None,
        status_code: Optional[int] = None,
    ):
        """Patch httpx.AsyncClient.request to return a canned response or raise."""
        if return_value is None and side_effect is None and status_code is not None:
            return_value = httpx.Response(status_code, request=httpx.Request("GET", "http://test"))
        if return_value is None and side_effect is None:
            return_value = httpx.Response(500, request=httpx.Request("GET", "http://test"))

        mock = AsyncMock(return_value=return_value)
        if side_effect:
            mock.side_effect = side_effect

        with patch("httpx.AsyncClient.request", mock):
            yield mock

    @contextlib.contextmanager
    def patch_db(self, *, side_effect: Optional[Exception] = None):
        """Patch sqlalchemy.Engine.connect to raise or return a mock connection."""
        mock = MagicMock()
        if side_effect:
            mock.side_effect = side_effect

        with patch("sqlalchemy.engine.Engine.connect", mock):
            yield mock

    @contextlib.contextmanager
    def patch_chroma(self, *, side_effect: Optional[Exception] = None, return_value: Any = None):
        """Patch chromadb.HttpClient to simulate connection failure."""
        mock_client = MagicMock()
        if side_effect:
            mock_client.side_effect = side_effect
        elif return_value is not None:
            mock_client.return_value = return_value
        else:
            # Default: return a mock client instance
            mock_client.return_value = MagicMock()

        # Patch the class constructor, not __init__
        with patch("chromadb.HttpClient", mock_client):
            yield mock_client

    @contextlib.contextmanager
    def patch_s3(self, *, side_effect: Optional[Exception] = None, return_value: Any = None):
        """Patch boto3.client('s3') to simulate S3 failures."""
        mock_client = MagicMock()
        if side_effect:
            mock_client.side_effect = side_effect
        elif return_value is not None:
            mock_client.return_value = return_value

        def client_factory(service_name, **kwargs):
            if service_name == "s3":
                return mock_client
            import boto3
            return boto3.client(service_name, **kwargs)

        with patch("boto3.client", side_effect=client_factory):
            yield mock_client


class CircuitBreakerInspector:
    """Read-only access to ProviderCircuitBreaker internal state for test assertions."""

    def __init__(self):
        self._breakers = {}

    def register(self, provider_name: str, breaker: Any):
        self._breakers[provider_name] = breaker

    def get_state(self, provider_name: str) -> str:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return breaker.state

    def get_failure_count(self, provider_name: str) -> int:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return breaker.failure_count

    def get_last_failure(self, provider_name: str) -> Optional[float]:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return getattr(breaker, "last_failure_time", None)

    def get_half_open_successes(self, provider_name: str) -> int:
        breaker = self._breakers.get(provider_name)
        if not breaker:
            raise KeyError(f"No circuit breaker registered for {provider_name}")
        return getattr(breaker, "success_count_in_half_open", 0)


class WebSocketEventCapture:
    """Captures ConnectionManager.broadcast calls for assertion."""

    def __init__(self):
        self.captured_events = []
        self._original_broadcast = None

    def start(self):
        from backend.api.routes.websocket import manager
        self._original_broadcast = manager.broadcast
        manager.broadcast = self._capture_broadcast

    def stop(self):
        if self._original_broadcast:
            from backend.api.routes.websocket import manager
            manager.broadcast = self._original_broadcast

    async def _capture_broadcast(self, payload: dict):
        self.captured_events.append(payload)
        if self._original_broadcast:
            await self._original_broadcast(payload)

    def wait_for_event(self, event_type: str, timeout: float = 5.0) -> dict:
        import asyncio
        async def _wait():
            import time
            start = time.time()
            while time.time() - start < timeout:
                for event in self.captured_events:
                    if event.get("type") == event_type:
                        return event
                await asyncio.sleep(0.05)
            raise TimeoutError(f"Event {event_type} not captured within {timeout}s")
        return asyncio.run(_wait())

    def clear(self):
        self.captured_events.clear()


class HealthEndpointClient:
    """Test helper to call the degradation health endpoint."""

    def __init__(self, base_url: str = "http://testserver"):
        self.base_url = base_url
        self._client = None

    async def __aenter__(self):
        import httpx
        self._client = httpx.AsyncClient(base_url=self.base_url)
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def get_degradation(self) -> dict:
        resp = await self._client.get("/api/v1/health/degradation")
        resp.raise_for_status()
        return resp.json()