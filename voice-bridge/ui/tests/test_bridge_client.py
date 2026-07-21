import json
import sys
import os
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import QUrl

sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..", "..")
    ),
)
sys.path.insert(
    0,
    os.path.normpath(
        os.path.join(os.path.dirname(__file__), "..")
    ),
)

import ui.bridge_client as bridge_client  # noqa: E402
from ui.bridge_client import BridgeClient  # noqa: E402


@pytest.fixture
def mock_ws():
    with patch("ui.bridge_client.QWebSocket") as cls:
        yield cls


@pytest.fixture
def mock_timer():
    with patch("ui.bridge_client.QTimer") as cls:
        yield cls


@pytest.fixture
def client(mock_ws, mock_timer):
    ws = MagicMock()
    mock_ws.return_value = ws
    timer = MagicMock()
    mock_timer.return_value = timer
    c = BridgeClient()
    c._ws = ws
    c._reconnect_timer = timer
    return c, ws, timer


@pytest.fixture
def client_with_signals(client):
    c, ws, timer = client
    connected_spy = MagicMock()
    disconnected_spy = MagicMock()
    voice_state_spy = MagicMock()
    c.connected.connect(connected_spy)
    c.disconnected.connect(disconnected_spy)
    c.voice_state_changed.connect(voice_state_spy)
    return c, ws, timer, connected_spy, disconnected_spy, voice_state_spy


class TestInit:
    def test_default_state(self, mock_ws, mock_timer):
        mock_ws.return_value = MagicMock()
        mock_timer.return_value = MagicMock()
        c = BridgeClient()
        assert c._url == ""
        assert c._reconnect_delay == 1000
        assert c._max_backoff == 15000

    def test_reconnect_timer_is_single_shot(self, mock_ws, mock_timer):
        timer = MagicMock()
        mock_timer.return_value = timer
        mock_ws.return_value = MagicMock()
        c = BridgeClient()
        timer.setSingleShot.assert_called_once_with(True)

    def test_websocket_signals_connected(self, client):
        c, ws, timer = client
        ws.connected.connect.assert_called_once_with(c._on_connected)
        ws.disconnected.connect.assert_called_once_with(c._on_disconnected)
        ws.textMessageReceived.connect.assert_called_once_with(c._on_message)
        ws.errorOccurred.connect.assert_called_once_with(c._on_error)

    def test_reconnect_timer_connected(self, client):
        c, ws, timer = client
        timer.timeout.connect.assert_called_once_with(c._do_reconnect)


class TestConnect:
    def test_opens_websocket(self, client):
        c, ws, timer = client
        c.connect_to_server("ws://localhost:9999")
        ws.open.assert_called_once_with(QUrl("ws://localhost:9999"))

    def test_stores_url(self, client):
        c, ws, timer = client
        c.connect_to_server("ws://localhost:9999")
        assert c._url == "ws://localhost:9999"

    def test_resets_reconnect_delay(self, client):
        c, ws, timer = client
        c._reconnect_delay = 8000
        c.connect_to_server("ws://localhost:9999")
        assert c._reconnect_delay == 1000


class TestDisconnect:
    def test_stops_reconnect_timer(self, client):
        c, ws, timer = client
        c._url = "ws://localhost:9999"
        c.disconnect_from_server()
        timer.stop.assert_called_once()

    def test_closes_websocket(self, client):
        c, ws, timer = client
        c.disconnect_from_server()
        ws.close.assert_called_once()


class TestOnConnected:
    def test_resets_reconnect_delay(self, client):
        c, ws, timer = client
        c._reconnect_delay = 8000
        c._on_connected()
        assert c._reconnect_delay == 1000

    def test_emits_connected(self, client):
        c, ws, timer = client
        spy = MagicMock()
        c.connected.connect(spy)
        c._on_connected()
        spy.assert_called_once()


class TestOnDisconnected:
    def test_emits_disconnected(self, client):
        c, ws, timer = client
        spy = MagicMock()
        c.disconnected.connect(spy)
        c._on_disconnected()
        spy.assert_called_once()

    def test_schedules_reconnect_when_url_set(self, client):
        c, ws, timer = client
        c._url = "ws://localhost:9999"
        c._on_disconnected()
        timer.start.assert_called_once_with(1000)

    def test_does_not_schedule_reconnect_when_no_url(self, client):
        c, ws, timer = client
        c._url = ""
        c._on_disconnected()
        timer.start.assert_not_called()


class TestOnMessage:
    @pytest.mark.parametrize(
        "state",
        ["listening", "speaking", "interrupted", "idle"],
    )
    def test_voice_state(self, client, state):
        c, ws, timer = client
        spy = MagicMock()
        c.voice_state_changed.connect(spy)
        c._on_message(json.dumps({"type": "voice_state", "state": state}))
        spy.assert_called_once_with(state)

    def test_invalid_json_is_ignored(self, client):
        c, ws, timer = client
        spy = MagicMock()
        c.voice_state_changed.connect(spy)
        c._on_message("not json")
        spy.assert_not_called()

    def test_non_voice_state_message_ignored(self, client):
        c, ws, timer = client
        spy = MagicMock()
        c.voice_state_changed.connect(spy)
        c._on_message(json.dumps({"type": "ping", "data": "hello"}))
        spy.assert_not_called()

    def test_defaults_to_idle_when_state_missing(self, client):
        c, ws, timer = client
        spy = MagicMock()
        c.voice_state_changed.connect(spy)
        c._on_message(json.dumps({"type": "voice_state"}))
        spy.assert_called_once_with("idle")


class TestReconnect:
    def test_exponential_backoff(self, client):
        c, ws, timer = client
        c._url = "ws://localhost:9999"
        delays = []
        for _ in range(5):
            delays.append(c._reconnect_delay)
            c._schedule_reconnect()
        expected_delays = [1000, 2000, 4000, 8000, 15000]
        assert delays == expected_delays

    def test_does_not_reconnect_without_url(self, client):
        c, ws, timer = client
        c._url = ""
        c._schedule_reconnect()
        timer.start.assert_not_called()

    def test_do_reconnect_opens_websocket(self, client):
        c, ws, timer = client
        c._url = "ws://localhost:9999"
        c._do_reconnect()
        ws.open.assert_called_once_with(QUrl("ws://localhost:9999"))

    def test_do_reconnect_does_nothing_without_url(self, client):
        c, ws, timer = client
        c._url = ""
        c._do_reconnect()
        ws.open.assert_not_called()


class TestOnError:
    def test_error_did_not_crash(self, client):
        c, ws, timer = client
        c._on_error("some error")


class TestIntegration:
    def test_full_connect_message_disconnect_cycle(
        self, client_with_signals
    ):
        c, ws, timer, connected_spy, disconnected_spy, voice_state_spy = (
            client_with_signals
        )

        c.connect_to_server("ws://127.0.0.1:9999")
        ws.open.assert_called_once()

        c._on_connected()
        connected_spy.assert_called_once()

        c._on_message(
            json.dumps({"type": "voice_state", "state": "speaking"})
        )
        voice_state_spy.assert_called_once_with("speaking")

        c._on_disconnected()
        disconnected_spy.assert_called_once()

    def test_message_after_disconnect_emits_state(
        self, client_with_signals
    ):
        c, ws, timer, connected_spy, disconnected_spy, voice_state_spy = (
            client_with_signals
        )

        c._on_disconnected()
        c._on_message(
            json.dumps({"type": "voice_state", "state": "idle"})
        )
        voice_state_spy.assert_called_once_with("idle")
