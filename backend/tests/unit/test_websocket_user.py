"""Unit tests for WebSocketUser (Phase 21.5.2)."""

import pytest
import json
from backend.tests.load.websocket_user import WebSocketUser


def test_websocket_user_token_generation():
    """Verify WebSocketUser generates valid auth JWT token."""
    user = WebSocketUser()
    token = user._get_auth_token()
    assert token is not None
    assert len(token) > 20


def test_websocket_user_lifecycle_mocked(monkeypatch):
    """Verify WebSocketUser handles connection and heartbeat lifecycle with mock ws."""
    class MockWS:
        def __init__(self):
            self.sent = []
            self.closed = False
            self._call_count = 0
            self._last_request_id = None

        def send(self, data):
            self.sent.append(data)
            # Track the request_id from ping messages
            try:
                parsed = json.loads(data)
                if parsed.get("type") == "ping":
                    self._last_request_id = parsed.get("request_id")
            except Exception:
                pass

        def recv(self, timeout=None):
            self._call_count += 1
            if self._call_count == 1:
                # First recv (after auth) - return welcome
                return '{"type": "system", "content": "Welcome"}'
            elif self._call_count == 2:
                # Second recv (after first ping) - return pong with matching request_id
                return json.dumps({"type": "pong", "timestamp": 123456, "request_id": self._last_request_id})
            elif self._call_count == 3:
                # Third recv (after second ping) - return pong with matching request_id
                return json.dumps({"type": "pong", "timestamp": 123456, "request_id": self._last_request_id})
            else:
                # Default fallback
                return json.dumps({"type": "pong", "timestamp": 123456, "request_id": self._last_request_id})

        def close(self):
            self.closed = True

    mock_ws = MockWS()
    monkeypatch.setattr("backend.tests.load.websocket_user.ws_connect", lambda *a, **k: mock_ws)

    user = WebSocketUser()
    user.on_start()
    assert user.connected is True
    assert len(mock_ws.sent) == 1
    assert "auth" in mock_ws.sent[0]

    # Test heartbeat - first call sends ping and receives matching pong
    user.heartbeat()
    assert len(mock_ws.sent) == 2
    assert "ping" in mock_ws.sent[1]

    # Test heartbeat again - second call
    user.heartbeat()
    assert len(mock_ws.sent) == 3

    # Test on_stop
    user.on_stop()
    assert mock_ws.closed is True
    assert user.connected is False