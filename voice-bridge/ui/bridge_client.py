import json
from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtWebSockets import QWebSocket


class BridgeClient(QObject):
    voice_state_changed = Signal(str)
    transcript_received = Signal(str, str)
    audio_level_received = Signal(float)
    connected = Signal()
    disconnected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._ws = QWebSocket()
        self._ws.connected.connect(self._on_connected)
        self._ws.disconnected.connect(self._on_disconnected)
        self._ws.textMessageReceived.connect(self._on_message)
        self._ws.errorOccurred.connect(self._on_error)
        self._url = ""
        self._reconnect_timer = QTimer(self)
        self._reconnect_timer.setSingleShot(True)
        self._reconnect_timer.timeout.connect(self._do_reconnect)
        self._reconnect_delay = 1000
        self._max_backoff = 15000

    def connect_to_server(self, url: str):
        self._url = url
        self._reconnect_delay = 1000
        self._ws.open(QUrl(url))

    def disconnect_from_server(self):
        self._reconnect_timer.stop()
        self._ws.close()

    def _on_connected(self):
        self._reconnect_delay = 1000
        self.connected.emit()

    def _on_disconnected(self):
        self.disconnected.emit()
        self._schedule_reconnect()

    def _on_message(self, text: str):
        try:
            data = json.loads(text)
            if not isinstance(data, dict):
                return
            msg_type = data.get("type")
            if msg_type == "voice_state":
                self.voice_state_changed.emit(data.get("state", "idle"))
            elif msg_type == "transcript":
                transcript_text = data.get("text", "")
                role = data.get("role", "agent")
                if transcript_text:
                    self.transcript_received.emit(transcript_text, role)
            elif msg_type == "audio_level":
                level = float(data.get("level", 0.0))
                self.audio_level_received.emit(level)
        except (json.JSONDecodeError, ValueError):
            pass

    def _on_error(self, error):
        pass

    def _schedule_reconnect(self):
        if self._url:
            self._reconnect_timer.start(self._reconnect_delay)
            self._reconnect_delay = min(self._reconnect_delay * 2, self._max_backoff)

    def _do_reconnect(self):
        if self._url:
            self._ws.open(QUrl(self._url))
