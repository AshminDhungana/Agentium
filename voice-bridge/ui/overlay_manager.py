import sys
from PySide6.QtCore import QObject, Signal, Slot, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QScreen, QCursor
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
        data = WINCOMPATTRDATA(19, ctypes.cast(ctypes.pointer(accent), c_void_p), ctypes.sizeof(accent))
        SetWindowCompositionAttribute(hwnd, data)
    except Exception:
        pass


class OverlayManager(QObject):
    overlay_visible_changed = Signal(bool)

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
        self._overlay_view.setFlag(Qt.WindowType.WindowTransparentForInput, True)

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
        self._indicator_view.setFlag(Qt.WindowType.WindowTransparentForInput, True)
        self._indicator_root = self._indicator_view.rootObject()

        self._transcript_view = QQuickView()
        self._transcript_view.setSource(
            QUrl.fromLocalFile(__file__).resolved(QUrl("./qml/TranscriptOverlay.qml"))
        )
        self._transcript_view.setResizeMode(QQuickView.SizeRootObjectToView)
        self._transcript_view.setColor("transparent")
        self._transcript_view.setFlag(Qt.WindowType.WindowTransparentForInput, True)
        self._transcript_root = self._transcript_view.rootObject()

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
        self._overlay_view.raise_()
        if self._overlay_root:
            self._overlay_root.setProperty("opacity", 1.0)
        self._overlay_visible = True
        self.overlay_visible_changed.emit(True)
        self._apply_acrylic(self._overlay_view)

    @Slot()
    def hide_overlay(self):
        if self._overlay_root:
            self._overlay_root.setProperty("opacity", 0.0)
        QTimer.singleShot(200, self._overlay_view.hide)
        self._overlay_visible = False
        self.overlay_visible_changed.emit(False)

    @Slot()
    def show_indicator(self):
        self._position_bottom_right()
        self._indicator_view.show()
        self._indicator_view.raise_()
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
            self.show_transcript()
            self._auto_hide_timer.stop()
            if self._indicator_root:
                self._indicator_root.setProperty("stateLabel", "Listening...")
        elif state == "speaking":
            self.hide_overlay()
            self.hide_transcript()
            self.show_indicator()
            if self._indicator_root:
                self._indicator_root.setProperty("stateLabel", "Speaking...")
        elif state == "thinking":
            if self._indicator_root:
                self._indicator_root.setProperty("stateLabel", "Thinking...")
        elif state == "interrupted":
            self.hide_indicator()
            self.show_overlay()
            self.show_transcript()
            self._auto_hide_timer.stop()
            if self._indicator_root:
                self._indicator_root.setProperty("stateLabel", "Listening...")
        elif state == "idle":
            self.hide_indicator()
            self.hide_transcript()
            if self._overlay_visible:
                self._auto_hide_timer.start()

    @Slot(float)
    def on_mic_level(self, level: float):
        if self._overlay_root:
            self._overlay_root.setProperty("micLevel", level)

    @Slot(str, str)
    def on_transcript(self, text: str, role: str):
        if self._transcript_root:
            self._transcript_root.setProperty("transcriptText", text)
            self._transcript_root.setProperty("transcriptRole", role)
            self._transcript_root.setProperty("isVisible", True)

    def show_transcript(self):
        self._position_under_orb()
        self._transcript_view.show()
        self._transcript_view.raise_()
        if self._transcript_root:
            self._transcript_root.setProperty("isVisible", True)

    def hide_transcript(self):
        if self._transcript_root:
            self._transcript_root.setProperty("isVisible", False)
        self._transcript_view.hide()

    def _on_auto_hide(self):
        self.hide_overlay()

    def _center_on_cursor(self):
        cursor_pos = QCursor.pos()
        self._overlay_view.setPosition(
            int(cursor_pos.x() - self._overlay_view.width() / 2),
            int(cursor_pos.y() - self._overlay_view.height() / 2),
        )

    def _position_under_orb(self):
        cursor_pos = QCursor.pos()
        self._transcript_view.setPosition(
            int(cursor_pos.x() - self._transcript_view.width() / 2),
            int(cursor_pos.y() + 170),
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
