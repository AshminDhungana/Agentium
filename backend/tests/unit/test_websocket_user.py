"""Unit tests for WebSocketUser (Phase 21.5.2)."""

import pytest
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

        def send(self, data):
            self.sent.append(data)

        def recv(self, timeout=None):
            return '{"type": "system", "content": "Welcome"}'

        def close(self):
            self.closed = True

    mock_ws = MockWS()
    monkeypatch.setattr("backend.tests.load.websocket_user.ws_connect", lambda *a, **k: mock_ws)

    user = WebSocketUser()
    user.on_start()
    assert user.connected is True
    assert len(mock_ws.sent) == 1
    assert "auth" in mock_ws.sent[0]

    # Test heartbeat
    mock_ws.recv = lambda timeout=None: '{"type": "pong", "timestamp": 123456}'
    user.heartbeat()
    assert len(mock_ws.sent) == 2
    assert "ping" in mock_ws.sent[1]

    # Test on_stop
    user.on_stop()
    assert mock_ws.closed is True
    assert user.connected is False

