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
    os.path.join(os.path.dirname(__file__), "..", "qml", "WaveformOverlay.qml")
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


class TestWaveformOverlay:
    def test_qml_file_exists(self):
        assert os.path.isfile(QML_PATH), f"QML file not found at {QML_PATH}"

    def test_qml_file_readable(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert len(content) > 0
        assert "import QtQuick 2.15" in content
        assert "Window" in content
        assert "waveformCanvas" in content

    def test_loads_with_qqmlapplicationengine(self, qml_app):
        _, _, root_objects = qml_app
        assert len(root_objects) > 0, "No root objects loaded"
        root = root_objects[0]
        assert root is not None
        assert root.property("micLevel") == 0.0
        assert root.property("voiceState") == "idle"

    def test_no_rectangular_glow(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "RectangularGlow" not in content, (
            "RectangularGlow is not available in Qt6/PySide6"
        )

    def test_has_required_imports(self):
        with open(QML_PATH, "r", encoding="utf-8") as f:
            content = f.read()
        assert "import QtQuick 2.15" in content
        assert "import QtQuick.Window 2.15" in content
        assert "import QtQuick.Effects 6.5" in content

    def test_context_properties(self, qml_app):
        _, _, root_objects = qml_app
        root = root_objects[0]
        assert root.property("micLevel") is not None
        assert root.property("voiceState") is not None

    def test_state_properties_exist(self, qml_app):
        _, _, root_objects = qml_app
        root = root_objects[0]
        assert root.property("micLevel") == 0.0
        assert root.property("voiceState") == "idle"
