import json
from PySide6.QtCore import QObject, Signal, QUrl, QTimer
from PySide6.QtWebSockets import QWebSocket


class BridgeClient(QObject):
    voice_state_changed = Signal(str)
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
            if data.get("type") == "voice_state":
                self.voice_state_changed.emit(data.get("state", "idle"))
        except json.JSONDecodeError:
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
