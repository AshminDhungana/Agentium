"""WebSocketUser - Locust user class for WebSocket load testing (Phase 21.5.2).

Simulates high-concurrency WebSocket connections to /ws/chat with:
- JWT authentication handshake
- Periodic heartbeat (ping/pong) monitoring
- Chat message streaming interaction
- Connection persistence and drop rate tracking
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Optional

try:
    from locust import User, task, between, events
    _HAS_LOCUST = True
except Exception:  # pragma: no cover
    _HAS_LOCUST = False
    User = object
    def task(weight=1):
        return lambda fn: fn
    def between(a, b):
        return lambda: a
    class _MockEvents:
        class _Req:
            def fire(self, **kwargs):
                pass
        request = _Req()
    events = _MockEvents()

try:
    from websockets.sync.client import connect as ws_connect
    _HAS_WEBSOCKETS = True
except Exception:  # pragma: no cover
    _HAS_WEBSOCKETS = False

logger = logging.getLogger(__name__)

_TEST_USER = "admin"
_TEST_PASS = "admin"

# Use the same SECRET_KEY as the TESTING mode backend
_TEST_SECRET_KEY = "test-secret-key-for-ci"


class WebSocketUser(User):
    """
    Locust user that connects to /ws/chat and maintains persistent WebSocket connection.
    Target: 500 concurrent connections, <1% disconnect rate, <100ms ping latency.
    """
    weight = 25
    wait_time = between(1.0, 3.0) if _HAS_LOCUST else None

    def __init__(self, *args, **kwargs):
        if _HAS_LOCUST:
            super().__init__(*args, **kwargs)
        self.ws = None
        self.token: Optional[str] = None
        self.connected = False
        self._host = getattr(self.environment, "host", "http://localhost:8000") if getattr(self, "environment", None) else "http://localhost:8000"

    def _get_auth_token(self) -> str:
        """Obtain JWT token from auth endpoint or generate valid HMAC token."""
        try:
            from jose import jwt
            # Use the same SECRET_KEY as the TESTING mode backend
            secret_key = _TEST_SECRET_KEY
            payload = {
                "sub": _TEST_USER,
                "role": "sovereign",
                "exp": time.time() + 3600,
            }
            return jwt.encode(payload, secret_key, algorithm="HS256")
        except Exception:
            return "mock-token"

    def on_start(self):
        """Establish WebSocket connection and complete authentication handshake."""
        if not _HAS_WEBSOCKETS:
            return

        self.token = self._get_auth_token()
        base = (self._host or "http://localhost:8000").rstrip("/")
        ws_url = base.replace("http://", "ws://").replace("https://", "wss://") + "/ws/chat"

        start_time = time.perf_counter()
        try:
            self.ws = ws_connect(ws_url, open_timeout=5.0, close_timeout=2.0)
            # 1. Send auth message
            auth_payload = json.dumps({"type": "auth", "token": self.token})
            self.ws.send(auth_payload)

            # 2. Await system welcome response
            welcome_raw = self.ws.recv(timeout=5.0)
            welcome_data = json.loads(welcome_raw)
            if welcome_data.get("type") in ("system", "welcome"):
                self.connected = True
                duration_ms = (time.perf_counter() - start_time) * 1000.0
                if _HAS_LOCUST:
                    events.request.fire(
                        request_type="WebSocket",
                        name="ws:connect_and_auth",
                        response_time=duration_ms,
                        response_length=len(welcome_raw),
                        exception=None,
                    )
            else:
                raise ValueError(f"Unexpected auth reply: {welcome_data}")
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            self.connected = False
            if _HAS_LOCUST:
                events.request.fire(
                    request_type="WebSocket",
                    name="ws:connect_and_auth",
                    response_time=duration_ms,
                    response_length=0,
                    exception=exc,
                )

    def on_stop(self):
        """Gracefully close WebSocket connection."""
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None
            self.connected = False

    @task(3)
    def heartbeat(self):
        """Send ping message and verify pong response."""
        if not self.ws or not self.connected:
            return

        start_time = time.perf_counter()
        try:
            ping_payload = json.dumps({"type": "ping", "timestamp": time.time()})
            self.ws.send(ping_payload)

            reply = self.ws.recv(timeout=2.0)
            data = json.loads(reply)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            if data.get("type") == "pong":
                if _HAS_LOCUST:
                    events.request.fire(
                        request_type="WebSocket",
                        name="ws:heartbeat_ping",
                        response_time=duration_ms,
                        response_length=len(reply),
                        exception=None,
                    )
            else:
                raise ValueError(f"Expected pong, received {data.get('type')}")
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            if _HAS_LOCUST:
                events.request.fire(
                    request_type="WebSocket",
                    name="ws:heartbeat_ping",
                    response_time=duration_ms,
                    response_length=0,
                    exception=exc,
                )

    @task(1)
    def chat_message(self):
        """Send chat message and receive response chunk."""
        if not self.ws or not self.connected:
            return

        start_time = time.perf_counter()
        try:
            msg_payload = json.dumps({
                "type": "chat_message",
                "content": "Load test ping message",
            })
            self.ws.send(msg_payload)

            reply = self.ws.recv(timeout=5.0)
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            if _HAS_LOCUST:
                events.request.fire(
                    request_type="WebSocket",
                    name="ws:chat_exchange",
                    response_time=duration_ms,
                    response_length=len(reply),
                    exception=None,
                )
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            if _HAS_LOCUST:
                events.request.fire(
                    request_type="WebSocket",
                    name="ws:chat_exchange",
                    response_time=duration_ms,
                    response_length=0,
                    exception=exc,
                )
