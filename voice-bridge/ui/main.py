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


_TOOLTIP_MAP = {
    "listening": "Agentium Voice — Listening...",
    "speaking": "Agentium Voice — Speaking...",
    "idle": "Agentium Voice — Idle",
}

_ICON_MAP = {
    "idle": "tray_idle.png",
    "listening": "tray_listening.png",
    "speaking": "tray_speaking.png",
}


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

    state_icons = {
        "idle": _icon_from_asset("tray_idle.png"),
        "listening": _icon_from_asset("tray_listening.png"),
        "speaking": _icon_from_asset("tray_speaking.png"),
    }

    def _update_tray_state(state: str):
        tip = _TOOLTIP_MAP.get(state, "Agentium Voice")
        tray_icon.setToolTip(tip)
        icon = state_icons.get(state)
        if icon and not icon.isNull():
            tray_icon.setIcon(icon)

    bridge.voice_state_changed.connect(_update_tray_state)

    idle_icon = state_icons["idle"]
    tray_icon.setIcon(idle_icon if not idle_icon.isNull() else app.style().standardIcon(48))

    show_action = QAction("Show Overlay")
    show_action.setCheckable(True)
    show_action.triggered.connect(overlay.toggle_overlay)
    overlay.overlay_visible_changed.connect(show_action.setChecked)

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
