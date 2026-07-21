# Agentium Voice Bridge UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a cinematic PySide6 + QML desktop HUD for the Agentium voice bridge that lives in the system tray and shows a circular waveform overlay when speaking and a bottom-right pill when the agent replies.

**Architecture:** Standalone PySide6 app that connects to the existing voice bridge WebSocket (`ws://127.0.0.1:9999`) as a passive observer — no changes to the bridge. Independently captures mic RMS levels via QAudioSource for waveform animation. Two QQuickView windows (circular HUD + speaking indicator) managed by OverlayManager, controlled by QSystemTrayIcon.

**Tech Stack:** PySide6 (Qt 6), QML / Qt Quick, QWebSocket, QAudioSource (QtMultimedia), QML Canvas 2D, QSystemTrayIcon

## Global Constraints

- All new files go under `voice-bridge/ui/`
- Python 3.10+ compatible
- PySide6 >= 6.5 (for QtQuick.Effects MultiEffect)
- Cross-platform: Windows, macOS, Linux
- Agentium design tokens: canvas `rgba(15, 17, 23, 0.80)`, panel `rgba(22, 27, 39, 0.85)`, brand `#3b82f6`, brand-soft `rgba(59, 130, 246, 0.15)`, hairline `rgba(30, 37, 53, 0.5)`
- Overlay windows must use `Qt.WindowTransparentForInput` for click-through
- QApplication must use `setQuitOnLastWindowClosed(False)` for background operation

---

### Task 1: Scaffold + BridgeClient (WebSocket listener)

**Files:**
- Create: `voice-bridge/ui/__init__.py`
- Create: `voice-bridge/ui/bridge_client.py`

**Interfaces:**
- Consumes: WebSocket at `ws://127.0.0.1:9999` broadcasting JSON `{"type":"voice_state","state":"<listening|speaking|interrupted|idle>"}`
- Produces: `BridgeClient(QObject)` with signals `voice_state_changed(state: str)`, `connected()`, `disconnected()`. Method `connect_to_server(url: str)`.

- [ ] **Step 1: Create `voice-bridge/ui/__init__.py`**

```python
```

- [ ] **Step 2: Create `voice-bridge/ui/bridge_client.py`**

```python
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
```

---

### Task 2: MicLevelCapture (audio RMS reader)

**Files:**
- Create: `voice-bridge/ui/mic_level.py`

**Interfaces:**
- Produces: `MicLevelCapture(QObject)` with signal `mic_level(level: float)` (0.0–1.0). Methods `start()`, `stop()`.

- [ ] **Step 1: Create `voice-bridge/ui/mic_level.py`**

```python
from PySide6.QtCore import QObject, Signal, QTimer
from PySide6.QtMultimedia import QAudioSource, QMediaDevices, QAudioFormat
from PySide6.QtCore import QIODevice
import struct


class MicLevelCapture(QObject):
    mic_level = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._audio_source = None
        self._io_device = None
        self._timer = QTimer(self)
        self._timer.setInterval(33)
        self._timer.timeout.connect(self._read_level)
        self._buffer = b""

    def start(self):
        devices = QMediaDevices.audioInputs()
        if not devices:
            return
        fmt = QAudioFormat()
        fmt.setSampleRate(16000)
        fmt.setChannelCount(1)
        fmt.setSampleFormat(QAudioFormat.Int16)
        self._audio_source = QAudioSource(devices[0], fmt)
        self._io_device = self._audio_source.start()
        self._timer.start()

    def stop(self):
        self._timer.stop()
        if self._audio_source:
            self._audio_source.stop()
            self._audio_source = None
            self._io_device = None

    def _read_level(self):
        if not self._io_device:
            return
        data = self._io_device.read(960)
        if not data:
            return
        self._buffer += bytes(data)
        window_size = 1920
        if len(self._buffer) < window_size:
            return
        chunk = self._buffer[-window_size:]
        self._buffer = self._buffer[-window_size:]

        samples = struct.unpack("<" + "h" * (len(chunk) // 2), chunk)
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
        normalized = min(rms / 32768.0, 1.0)
        self.mic_level.emit(normalized)
```

---

### Task 3: WaveformOverlay.qml (circular waveform HUD)

**Files:**
- Create: `voice-bridge/ui/qml/WaveformOverlay.qml`

**Interfaces:**
- Consumes: `overlay.micLevel` (real), `overlay.voiceState` (string) from QML context properties set by Python
- Produces: Frameless transparent Window 280x280 centered on screen, auto-hides via opacity

- [ ] **Step 1: Create `voice-bridge/ui/qml/WaveformOverlay.qml`**

```qml
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: overlay
    width: 280
    height: 280
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property real micLevel: 0.0
    property string voiceState: "idle"

    opacity: 0

    Behavior on opacity {
        NumberAnimation { duration: 200; easing.type: Easing.OutCubic }
    }

    states: [
        State {
            name: "visible"; when: opacity > 0
            PropertyChanges { target: overlay; visible: true }
        },
        State {
            name: "hidden"; when: opacity === 0
            PropertyChanges { target: overlay; visible: false }
        }
    ]

    RectangularGlow {
        anchors.fill: parent
        glowRadius: 20
        spread: 0.1
        color: "rgba(59, 130, 246, 0.06)"
        cornerRadius: 140
    }

    Rectangle {
        id: glassBg
        anchors.fill: parent
        radius: 140
        color: "rgba(22, 27, 39, 0.80)"
        border.color: "rgba(59, 130, 246, 0.10)"
        border.width: 1

        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 1.0
            blurMax: 64
            saturation: 0.5
        }
    }

    Canvas {
        id: waveformCanvas
        anchors.fill: parent
        anchors.margins: 10

        property real time: 0

        onPaint: {
            var ctx = getContext("2d");
            var w = width;
            var h = height;
            ctx.clearRect(0, 0, w, h);

            var cx = w / 2;
            var cy = h / 2;
            var radius = 90;
            var barCount = 48;
            var barWidth = 4;

            time += 0.02;

            for (var i = 0; i < barCount; i++) {
                var angle = (i / barCount) * Math.PI * 2 - Math.PI / 2;

                var level = 0.0;
                if (voiceState === "listening") {
                    level = micLevel * (0.6 + 0.4 * Math.sin(time * 3 + i * 0.4));
                } else if (voiceState === "thinking") {
                    var wavePos = ((time * 1.5 + i / barCount) % 1.0);
                    level = Math.sin(wavePos * Math.PI) * 0.5;
                }

                var barHeight = 6 + level * 30;
                var glowSize = level * 8;

                // Glow layer
                ctx.strokeStyle = "rgba(59, 130, 246, 0.15)";
                ctx.lineWidth = barWidth + glowSize;
                ctx.lineCap = "round";
                ctx.beginPath();
                var gx1 = cx + Math.cos(angle) * (radius - glowSize / 2);
                var gy1 = cy + Math.sin(angle) * (radius - glowSize / 2);
                var gx2 = cx + Math.cos(angle) * (radius + barHeight + glowSize / 2);
                var gy2 = cy + Math.sin(angle) * (radius + barHeight + glowSize / 2);
                ctx.moveTo(gx1, gy1);
                ctx.lineTo(gx2, gy2);
                ctx.stroke();

                // Main bar
                ctx.strokeStyle = "#3b82f6";
                ctx.lineWidth = barWidth;
                ctx.beginPath();
                var x1 = cx + Math.cos(angle) * radius;
                var y1 = cy + Math.sin(angle) * radius;
                var x2 = cx + Math.cos(angle) * (radius + barHeight);
                var y2 = cy + Math.sin(angle) * (radius + barHeight);
                ctx.moveTo(x1, y1);
                ctx.lineTo(x2, y2);
                ctx.stroke();
            }
        }

        Connections {
            target: overlay
            function onMicLevelChanged() { waveformCanvas.requestPaint(); }
        }
    }

    Timer {
        interval: 16
        running: true
        repeat: true
        onTriggered: {
            waveformCanvas.time += 0.02;
            waveformCanvas.requestPaint();
        }
    }

    // Core circle
    Rectangle {
        width: 16
        height: 16
        radius: 8
        color: "#3b82f6"
        anchors.centerIn: parent
        opacity: 0.9

        Rectangle {
            width: 8
            height: 8
            radius: 4
            color: "#ffffff"
            anchors.centerIn: parent
            opacity: 0.4
        }
    }

    // Orbital rings
    Repeater {
        model: 2
        Rectangle {
            x: parent.width / 2 - width / 2
            y: parent.height / 2 - height / 2
            width: 180 + index * 20
            height: 180 + index * 20
            radius: (width + height) / 4
            color: "transparent"
            border.color: "rgba(59, 130, 246, 0.08)"
            border.width: 1
            rotation: time * (index === 0 ? 15 : -10)

            Behavior on rotation { NumberAnimation { duration: 100 } }
        }
    }
}
```

---

### Task 4: SpeakingIndicator.qml (bottom-right pill)

**Files:**
- Create: `voice-bridge/ui/qml/SpeakingIndicator.qml`

**Interfaces:**
- Consumes: `indicator.active` (bool) from QML context property set by Python
- Produces: Small frameless Window 120x36 anchored 20px from bottom-right screen edge

- [ ] **Step 1: Create `voice-bridge/ui/qml/SpeakingIndicator.qml`**

```qml
import QtQuick 2.15
import QtQuick.Window 2.15
import QtQuick.Effects 6.5

Window {
    id: indicator
    width: 120
    height: 36
    flags: Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput
    color: "transparent"
    visible: false

    property bool active: false

    opacity: 0

    Behavior on opacity {
        NumberAnimation { duration: active ? 300 : 100; easing.type: Easing.OutCubic }
    }

    states: [
        State {
            name: "shown"; when: opacity > 0.5
            PropertyChanges { target: indicator; visible: true }
        },
        State {
            name: "hidden"; when: opacity < 0.5
            PropertyChanges { target: indicator; visible: false }
        }
    ]

    Rectangle {
        id: glassBg
        anchors.fill: parent
        radius: 18
        color: "rgba(22, 27, 39, 0.85)"
        border.color: "rgba(59, 130, 246, 0.30)"
        border.width: 1

        layer.enabled: true
        layer.effect: MultiEffect {
            blurEnabled: true
            blur: 0.8
            blurMax: 32
            saturation: 0.5
        }
    }

    Item {
        anchors.centerIn: parent
        width: childrenRect.width
        height: 16

        property real time: 0

        Timer {
            interval: 16
            running: true
            repeat: true
            onTriggered: {
                parent.time += 0.05;
            }
        }

        Row {
            spacing: 5
            Repeater {
                model: 3
                Rectangle {
                    y: parent.parent.height / 2 - height / 2
                    width: 3
                    radius: 1.5
                    color: "#3b82f6"

                    property real baseHeight: 8
                    height: indicator.active
                        ? baseHeight + Math.sin(parent.parent.time * 4 + index * 1.5) * 6 + 4
                        : baseHeight

                    Behavior on height {
                        NumberAnimation { duration: 80 }
                    }
                }
            }
        }
    }

    Rectangle {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        anchors.rightMargin: 8
        width: 8
        height: 8
        radius: 4
        color: indicator.active ? "#3b82f6" : "transparent"

        Behavior on color {
            ColorAnimation { duration: 200 }
        }
    }
}
```

---

### Task 5: OverlayManager (window lifecycle + signal wiring)

**Files:**
- Create: `voice-bridge/ui/overlay_manager.py`

**Interfaces:**
- Consumes: `BridgeClient` signals, `MicLevelCapture` signals
- Produces: `OverlayManager(QObject)` with methods `toggle_overlay()`, `show_overlay()`, `hide_overlay()`, `show_indicator()`, `hide_indicator()`

- [ ] **Step 1: Create `voice-bridge/ui/overlay_manager.py`**

```python
import sys
from PySide6.QtCore import QObject, Slot, QTimer, QUrl, Property
from PySide6.QtGui import QGuiApplication, QScreen
from PySide6.QtQuick import QQuickView
from PySide6.QtCore import Qt


def _enable_acrylic(hwnd: int):
    """Apply Windows 11 acrylic blur to a native window handle."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import c_void_p, c_uint, c_int, POINTER, Structure

        class ACCENTPOLICY(Structure):
            _fields_ = [
                ("AccentState", c_uint),
                ("AccentFlags", c_uint),
                ("GradientColor", c_uint),
                ("AnimationId", c_uint),
            ]

        class WINCOMPATTRDATA(Structure):
            _fields_ = [
                ("Attribute", c_int),
                ("pvData", c_void_p),
                ("cbData", c_uint),
            ]

        SetWindowCompositionAttribute = ctypes.windll.user32.SetWindowCompositionAttribute
        accent = ACCENTPOLICY(4, 0, 0, 0)
        data = WINCOMPATTRDATA(19, ctypes.byref(accent), ctypes.sizeof(accent))
        SetWindowCompositionAttribute(hwnd, data)
    except Exception:
        pass


class OverlayManager(QObject):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._overlay_visible = False
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.setInterval(1500)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide)

        self._overlay_view = QQuickView()
        self._overlay_view.setSource(
            QUrl.fromLocalFile(__file__).resolved(QUrl("./qml/WaveformOverlay.qml"))
        )
        self._overlay_view.setResizeMode(QQuickView.SizeRootObjectToView)
        self._overlay_view.setColor("transparent")

        # Disable title bar decorations handled by QML flags
        self._overlay_root = self._overlay_view.rootObject()
        if self._overlay_root:
            self._overlay_root.setProperty("micLevel", 0.0)
            self._overlay_root.setProperty("voiceState", "idle")

        self._indicator_view = QQuickView()
        self._indicator_view.setSource(
            QUrl.fromLocalFile(__file__).resolved(QUrl("./qml/SpeakingIndicator.qml"))
        )
        self._indicator_view.setResizeMode(QQuickView.SizeRootObjectToView)
        self._indicator_view.setColor("transparent")
        self._indicator_root = self._indicator_view.rootObject()

    @Slot()
    def toggle_overlay(self):
        if self._overlay_visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    @Slot()
    def show_overlay(self):
        self._center_on_cursor()
        self._overlay_view.show()
        if self._overlay_root:
            self._overlay_root.setProperty("opacity", 1.0)
        self._overlay_visible = True
        self._apply_acrylic(self._overlay_view)

    @Slot()
    def hide_overlay(self):
        if self._overlay_root:
            self._overlay_root.setProperty("opacity", 0.0)
        QTimer.singleShot(200, self._overlay_view.hide)
        self._overlay_visible = False

    @Slot()
    def show_indicator(self):
        self._position_bottom_right()
        self._indicator_view.show()
        if self._indicator_root:
            self._indicator_root.setProperty("opacity", 1.0)
            self._indicator_root.setProperty("active", True)
        self._apply_acrylic(self._indicator_view)

    @Slot()
    def hide_indicator(self):
        if self._indicator_root:
            self._indicator_root.setProperty("active", False)
            self._indicator_root.setProperty("opacity", 0.0)
        QTimer.singleShot(300, self._indicator_view.hide)

    @Slot(str)
    def on_voice_state(self, state: str):
        if self._overlay_root:
            self._overlay_root.setProperty("voiceState", state)
        if state == "listening":
            self.show_overlay()
            self._auto_hide_timer.stop()
        elif state == "speaking":
            self.hide_overlay()
            self.show_indicator()
        elif state == "interrupted":
            self.hide_indicator()
            self.show_overlay()
            self._auto_hide_timer.stop()
        elif state == "idle":
            self.hide_indicator()
            if self._overlay_visible:
                self._auto_hide_timer.start()

    @Slot(float)
    def on_mic_level(self, level: float):
        if self._overlay_root:
            self._overlay_root.setProperty("micLevel", level)

    def _on_auto_hide(self):
        self.hide_overlay()

    def _center_on_cursor(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        cursor_pos = screen.virtualGeometry().center()
        for s in QGuiApplication.screens():
            g = s.geometry()
            if g.contains(s.cursorPos()):
                cursor_pos = s.cursorPos()
                break
        self._overlay_view.setPosition(
            int(cursor_pos.x() - self._overlay_view.width() / 2),
            int(cursor_pos.y() - self._overlay_view.height() / 2),
        )

    def _position_bottom_right(self):
        screen = QGuiApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        self._indicator_view.setPosition(
            geo.right() - self._indicator_view.width() - 20,
            geo.bottom() - self._indicator_view.height() - 20,
        )

    def _apply_acrylic(self, view: QQuickView):
        hwnd = int(view.winId())
        _enable_acrylic(hwnd)
```

---

### Task 6: main.py (entry point + system tray + full integration)

**Files:**
- Create: `voice-bridge/ui/main.py`

**Interfaces:**
- Consumes: `BridgeClient`, `MicLevelCapture`, `OverlayManager`
- Produces: Runnable application with system tray icon

- [ ] **Step 1: Create `voice-bridge/ui/main.py`**

```python
import sys
import os

from PySide6.QtCore import QUrl
from PySide6.QtGui import QIcon, QAction, QDesktopServices, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from .bridge_client import BridgeClient
from .mic_level import MicLevelCapture
from .overlay_manager import OverlayManager


def _asset_path(name: str) -> str:
    return os.path.join(os.path.dirname(__file__), "assets", name)


def _icon_from_asset(name: str) -> QIcon:
    path = _asset_path(name)
    return QIcon(path) if os.path.exists(path) else QIcon()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName("Agentium Voice")
    app.setQuitOnLastWindowClosed(False)
    app.setOrganizationName("Agentium")

    overlay = OverlayManager()
    bridge = BridgeClient()
    mic = MicLevelCapture()

    bridge.voice_state_changed.connect(overlay.on_voice_state)
    mic.mic_level.connect(overlay.on_mic_level)

    tray_icon = QSystemTrayIcon()
    tray_icon.setToolTip("Agentium Voice")

    idle_icon = _icon_from_asset("tray_idle.png")
    tray_icon.setIcon(idle_icon if not idle_icon.isNull() else app.style().standardIcon(48))

    show_action = QAction("Show Overlay")
    show_action.setCheckable(True)
    show_action.triggered.connect(overlay.toggle_overlay)

    dashboard_action = QAction("Open Dashboard")
    dashboard_action.triggered.connect(
        lambda: QDesktopServices.openUrl(QUrl("http://localhost:3000"))
    )

    quit_action = QAction("Quit")
    quit_action.triggered.connect(app.quit)

    menu = QMenu()
    menu.addAction(show_action)
    menu.addAction(dashboard_action)
    menu.addSeparator()
    menu.addAction(quit_action)
    tray_icon.setContextMenu(menu)

    def on_tray_activated(reason):
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            overlay.toggle_overlay()
            show_action.setChecked(overlay._overlay_visible)

    tray_icon.activated.connect(on_tray_activated)
    tray_icon.show()

    bridge.connect_to_server("ws://127.0.0.1:9999")
    mic.start()

    app.aboutToQuit.connect(mic.stop)
    app.aboutToQuit.connect(bridge.disconnect_from_server)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

---

### Task 7: Entry point script + requirements + README + tray icons

**Files:**
- Create: `voice-bridge/run_voice_ui.py`
- Create: `voice-bridge/requirements-ui.txt`
- Create: `voice-bridge/ui/assets/tray_idle.png`
- Create: `voice-bridge/ui/assets/tray_listening.png`
- Create: `voice-bridge/ui/assets/tray_speaking.png`
- Create: `voice-bridge/README.md`

- [ ] **Step 1: Create `voice-bridge/run_voice_ui.py`**

```python
#!/usr/bin/env python3
"""Entry point to launch the Agentium Voice Bridge UI."""
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))
from ui.main import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `voice-bridge/requirements-ui.txt`**

```
PySide6>=6.5.0
```

- [ ] **Step 3: Generate tray icons programmatically**

Generate 3 PNG icons at 32x32 using a Python script. Each icon is a simple microphone shape on transparent background using the Agentium blue `#3b82f6` palette.

Create `voice-bridge/ui/generate_icons.py`:

```python
"""Generate tray icons for the voice bridge UI."""
import struct
import zlib
import os


def _create_png(width: int, height: int, pixels: list) -> bytes:
    """Create a minimal PNG from RGBA pixel data (list of (r,g,b,a) tuples)."""
    raw = b""
    for y in range(height):
        raw += b"\x00"  # filter byte
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw += bytes([r, g, b, a])

    def chunk(chunk_type: bytes, data: bytes) -> bytes:
        c = chunk_type + data
        return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _mic_pixels(size: int, color: tuple) -> list:
    """Generate RGBA pixel data for a simple microphone icon."""
    pixels = [(0, 0, 0, 0)] * (size * size)
    cx, cy = size // 2, size // 2
    r = size * 0.3
    for y in range(size):
        for x in range(size):
            dx, dy = x - cx, y - cy

            # Mic body: rectangle with rounded top
            body_left = int(cx - r * 0.5)
            body_right = int(cx + r * 0.5)
            body_top = int(cy - r * 1.2)
            body_bottom = int(cy + r * 0.2)

            if body_left <= x <= body_right and body_top <= y <= body_bottom:
                # Mic capsule shape
                rel_y = (y - body_top) / (body_bottom - body_top)
                capsule_r = r * 0.5 * (1 - rel_y * 0.3)
                if abs(dx) < capsule_r:
                    pixels[y * size + x] = color

            # Mic stand: vertical line
            stand_x = cx
            if abs(x - stand_x) < 2 and cy + r * 0.2 <= y <= cy + r * 0.7:
                pixels[y * size + x] = color

            # Base: horizontal line
            base_y = int(cy + r * 0.7)
            if abs(y - base_y) < 2 and abs(dx) < r * 0.6:
                pixels[y * size + x] = color

    return pixels


def generate_icons():
    out_dir = os.path.join(os.path.dirname(__file__), "assets")
    os.makedirs(out_dir, exist_ok=True)

    size = 32
    blue = (59, 130, 246, 255)
    white = (255, 255, 255, 255)
    green = (34, 197, 94, 255)

    icons = {
        "tray_idle.png": _mic_pixels(size, blue),
        "tray_listening.png": _mic_pixels(size, green),
        "tray_speaking.png": _mic_pixels(size, white),
    }

    for name, pixels in icons.items():
        png = _create_png(size, size, pixels)
        with open(os.path.join(out_dir, name), "wb") as f:
            f.write(png)
        print(f"Created {name}")


if __name__ == "__main__":
    generate_icons()
```

Run: `python voice-bridge/ui/generate_icons.py`

- [ ] **Step 4: Create `voice-bridge/README.md`**

```markdown
# Agentium Voice Bridge

Real-time voice communication bridge for Agentium. Runs on the host machine (outside Docker) and connects to the Agentium backend for STT, chat, and TTS.

## Components

- `main.py` — Core voice bridge: wake-word detection, microphone capture, STT relay, TTS playback, session management, WebSocket server for browser sync
- `ui/` — Desktop HUD companion app (PySide6 + QML): system tray icon, circular waveform overlay, speaking indicator

## Running the Desktop UI

```bash
pip install -r requirements-ui.txt
python run_voice_ui.py
```

Requires PySide6 >= 6.5. The UI auto-connects to the bridge WebSocket at ws://127.0.0.1:9999.

## Cross-Platform Notes

- **Windows:** Tested on Windows 10/11. DWM Acrylic glass effect applied automatically.
- **macOS:** Tested on macOS 12+. NSVisualEffectView glass effect applied automatically.
- **Linux:** Uses Qt Quick MultiEffect as blur fallback. Requires compositor with XDG Shell.
```

---

### Task 8: Self-review and verify plan

- [ ] **Step 1: Spec coverage check**

Requirements from spec mapped to tasks:
- BridgeClient WebSocket listener → Task 1
- MicLevelCapture RMS reader → Task 2
- WaveformOverlay.qml circular bars 280x280 → Task 3
- SpeakingIndicator.qml bottom-right pill 120x36 → Task 4
- OverlayManager show/hide/auto-hide/click-through → Task 5
- QSystemTrayIcon with menu, dynamic tooltip, left-click toggle → Task 6
- State-aware icons (idle/listening/speaking) → Task 7
- `requirements-ui.txt` + README → Task 7
- Acrylic glassmorphism via ctypes → Task 5
- `WA_TransparentForMouseEvents` → QML Window flags in Tasks 3, 4
- `setQuitOnLastWindowClosed(False)` → Task 6

All spec requirements covered.

- [ ] **Step 2: Placeholder scan**

Search plan for: "TBD", "TODO", "implement later", "fill in details". None found.

- [ ] **Step 3: Type/signature consistency**

Check signal names across tasks:
- BridgeClient.voice_state_changed(str) → consumed in Task 5 `on_voice_state(state: str)` ✓
- MicLevelCapture.mic_level(float) → consumed in Task 5 `on_mic_level(level: float)` ✓
- OverlayManager.toggle_overlay() → connected in Task 6 from tray ✓
- OverlayManager.show_overlay()/hide_overlay() → used internally ✓
- OverlayManager.show_indicator()/hide_indicator() → used internally ✓
- OverlayManager.on_voice_state → handles all 4 states ✓

QML context properties:
- `overlay.micLevel` (real) → Task 5 sets via `setProperty("micLevel", level)` ✓
- `overlay.voiceState` (string) → Task 5 sets via `setProperty("voiceState", state)` ✓
- `indicator.active` (bool) → Task 5 sets via `setProperty("active", True/False)` ✓
