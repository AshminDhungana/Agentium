import sys
import os
from unittest.mock import MagicMock, patch

import pytest

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


QML_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "qml", "SpeakingIndicator.qml")
)


@pytest.fixture(scope="module")
def qml_app():
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtCore import QUrl
    from PySide6.QtQml import QQmlApplicationEngine

    app = QGuiApplication(sys.argv[:1] if sys.argv else [])
    engine = QQmlApplicationEngine()
    engine.load(QUrl.fromLocalFile(QML_PATH))
    root_objects = engine.rootObjects()
    yield app, engine, root_objects
    del engine
    del app


class TestSpeakingIndicator:
    def test_qml_file_exists(self):
        assert os.path.isfile(QML_PATH), f"QML file not found at {QML_PATH}"

    def test_qml_file_readable(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 0
        assert "import QtQuick 2.15" in content
        assert "Window" in content
        assert "indicator" in content

    def test_loads_with_qqmlapplicationengine(self, qml_app):
        _, _, root_objects = qml_app
        assert len(root_objects) > 0, "No root objects loaded"
        root = root_objects[0]
        assert root is not None
        assert root.property("active") == False
        assert root.property("width") == 120
        assert root.property("height") == 36

    def test_no_states_block(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "states:" not in content, (
            "Window 'states' property is not available in Qt6/PySide6"
        )

    def test_no_rgba_calls(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "rgba(" not in content, (
            "rgba() in QML property bindings may not work in Qt6; use #AARRGGBB hex"
        )

    def test_has_required_imports(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "import QtQuick 2.15" in content
        assert "import QtQuick.Window 2.15" in content
        assert "import QtQuick.Effects 6.5" in content

    def test_context_property_active(self, qml_app):
        _, _, root_objects = qml_app
        root = root_objects[0]
        assert root.property("active") is not None

    def test_on_opacity_changed_visibility(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "onOpacityChanged" in content

    def test_frameless_window_flags(self, qml_app):
        _, _, root_objects = qml_app
        root = root_objects[0]
        from PySide6.QtCore import Qt
        flags = root.flags()
        assert flags & Qt.FramelessWindowHint
        assert flags & Qt.WindowStaysOnTopHint
        assert flags & Qt.WindowTransparentForInput

    def test_glass_bg_hex_colors(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "#D9161B27" in content
        assert "#4D3B82F6" in content

    def test_repeater_three_bars(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "model: 3" in content

    def test_behavior_on_opacity(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "Behavior on opacity" in content
        assert "NumberAnimation" in content
