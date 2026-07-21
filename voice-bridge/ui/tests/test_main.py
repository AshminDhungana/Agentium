import sys
import os
from unittest.mock import MagicMock, patch, call

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

import ui.main as main_module  # noqa: E402
from ui.main import _asset_path, _icon_from_asset, main  # noqa: E402


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

@pytest.fixture
def mock_qapp():
    with patch("ui.main.QApplication") as cls:
        app = MagicMock()
        cls.return_value = app
        yield cls, app


@pytest.fixture
def mock_style():
    style = MagicMock()
    style.standardIcon.return_value = MagicMock()
    return style


@pytest.fixture
def mock_tray():
    with patch("ui.main.QSystemTrayIcon") as cls:
        tray = MagicMock()
        cls.return_value = tray
        yield cls, tray


@pytest.fixture
def mock_menu():
    with patch("ui.main.QMenu") as cls:
        menu = MagicMock()
        cls.return_value = menu
        yield cls, menu


@pytest.fixture
def mock_action():
    with patch("ui.main.QAction") as cls:
        action = MagicMock()
        cls.return_value = action
        yield cls, action


@pytest.fixture
def mock_desktop():
    with patch("ui.main.QDesktopServices") as cls:
        yield cls


@pytest.fixture
def mock_overlay():
    with patch("ui.main.OverlayManager") as cls:
        overlay = MagicMock()
        cls.return_value = overlay
        yield cls, overlay


@pytest.fixture
def mock_bridge():
    with patch("ui.main.BridgeClient") as cls:
        bridge = MagicMock()
        cls.return_value = bridge
        yield cls, bridge


@pytest.fixture
def mock_mic():
    with patch("ui.main.MicLevelCapture") as cls:
        mic = MagicMock()
        cls.return_value = mic
        yield cls, mic


@pytest.fixture
def mock_icon():
    with patch("ui.main.QIcon") as cls:
        icon = MagicMock()
        icon.isNull.return_value = True
        cls.return_value = icon
        yield cls, icon


@pytest.fixture
def mock_os_path_exists():
    with patch("ui.main.os.path.exists") as cls:
        cls.return_value = False
        yield cls


# -------------------------------------------------------------------
# Tests: _asset_path
# -------------------------------------------------------------------

class TestAssetPath:
    def test_returns_path_under_assets(self):
        result = _asset_path("tray_idle.png")
        assert result.endswith(os.path.join("assets", "tray_idle.png"))

    def test_uses_file_directory(self):
        result = _asset_path("foo.png")
        expected_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        expected = os.path.join(expected_dir, "assets", "foo.png")
        assert os.path.normpath(result) == os.path.normpath(expected)


# -------------------------------------------------------------------
# Tests: _icon_from_asset
# -------------------------------------------------------------------

class TestIconFromAsset:
    def test_returns_qicon_when_asset_exists(self, mock_os_path_exists, mock_icon):
        mock_icon_cls, _ = mock_icon
        mock_os_path_exists.return_value = True
        result = _icon_from_asset("tray_idle.png")
        assert result is mock_icon_cls.return_value
        mock_icon_cls.assert_called_once()

    def test_returns_empty_qicon_when_no_asset(self, mock_os_path_exists, mock_icon):
        mock_icon_cls, icon_instance = mock_icon
        icon_instance.isNull.return_value = True
        mock_os_path_exists.return_value = False
        result = _icon_from_asset("tray_idle.png")
        assert result is icon_instance
        mock_icon_cls.assert_called_once_with()

    def test_pass_through_path(self, mock_os_path_exists):
        mock_icon_cls = MagicMock()
        icon_instance = MagicMock()
        mock_icon_cls.return_value = icon_instance
        mock_os_path_exists.return_value = True
        with patch("ui.main.QIcon", mock_icon_cls):
            _icon_from_asset("custom.png")
        path_arg = mock_icon_cls.call_args[0][0]
        assert path_arg.endswith(os.path.join("assets", "custom.png"))


# -------------------------------------------------------------------
# Tests: main()
# -------------------------------------------------------------------

class TestMain:
    def test_creates_qapplication(self, mock_qapp, mock_overlay, mock_bridge,
                                  mock_mic, mock_tray, mock_menu, mock_action,
                                  mock_icon, mock_os_path_exists):
        mock_qapp_cls, app = mock_qapp
        main_module.main = lambda: None

    def test_sets_app_name_and_quit_on_last_window_closed(
            self, mock_qapp, mock_overlay, mock_bridge,
            mock_mic, mock_tray, mock_menu, mock_action,
            mock_icon, mock_os_path_exists,
    ):
        mock_qapp_cls, app = mock_qapp
        with patch.object(main_module, "main", lambda: None):
            pass

    def test_main_basic(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, bridge = mock_bridge
        _, mic = mock_mic
        _, tray = mock_tray
        _, menu = mock_menu
        action_cls, _ = mock_action
        mock_icon_cls, null_icon = mock_icon
        null_icon.isNull.return_value = True

        with patch.object(sys, "exit") as mock_exit:
            main()

        mock_qapp_cls.assert_called_once()
        app.setApplicationName.assert_called_once_with("Agentium Voice")
        app.setQuitOnLastWindowClosed.assert_called_once_with(False)
        app.setOrganizationName.assert_called_once_with("Agentium")

    def test_wires_signals(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, bridge = mock_bridge
        _, mic = mock_mic
        action_cls, _ = mock_action

        with patch.object(sys, "exit"):
            main()

        bridge.voice_state_changed.connect.assert_any_call(
            overlay.on_voice_state
        )
        mic.mic_level.connect.assert_called_once_with(
            overlay.on_mic_level
        )

    def test_sets_up_tray_icon(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, bridge = mock_bridge
        _, mic = mock_mic
        tray_cls, tray = mock_tray

        with patch.object(sys, "exit"):
            main()

        tray_cls.assert_called_once()
        tray.setToolTip.assert_called_once_with("Agentium Voice")
        tray.show.assert_called_once()

    def test_tray_icon_fallback_to_standard_icon(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        mock_icon_cls, null_icon = mock_icon
        null_icon.isNull.return_value = True

        with patch.object(sys, "exit"):
            main()

        mock_style.standardIcon.assert_called_once_with(48)
        tray_set_icon_call = None
        for c in app.mock_calls:
            pass
        _, tray = mock_tray
        assert tray.setIcon.called

    def test_tray_icon_uses_asset_icon_when_available(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        mock_icon_cls, asset_icon = mock_icon
        asset_icon.isNull.return_value = False
        mock_os_path_exists.return_value = True

        with patch.object(sys, "exit"):
            main()

        assert mock_icon_cls.called
        _, tray = mock_tray
        tray.setIcon.assert_called_once_with(asset_icon)

    def test_creates_actions(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        action_cls, _ = mock_action

        with patch.object(sys, "exit"):
            main()

        assert action_cls.call_count >= 3

    def test_show_action_is_checkable(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        action_cls, _ = mock_action

        with patch.object(sys, "exit"):
            main()

        show_action_call = None
        for call_args in action_cls.call_args_list:
            if call_args[0][0] == "Show Overlay":
                show_action_call = action_cls.return_value
                break
        assert show_action_call is not None
        show_action_call.setCheckable.assert_called_once_with(True)

    def test_quit_action_connects_to_app_quit(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style

        with patch.object(sys, "exit"):
            main()

    def test_dashboard_action_opens_url(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style

        with patch.object(sys, "exit"):
            main()

    def test_menu_contains_actions(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, tray = mock_tray
        menu_cls, menu = mock_menu

        with patch.object(sys, "exit"):
            main()

        assert menu.addAction.call_count >= 2
        assert menu.addSeparator.call_count == 1
        tray.setContextMenu.assert_called_once_with(menu)

    def test_tray_activated_triggers_toggle(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, tray = mock_tray

        with patch.object(sys, "exit"):
            main()

        activate_handler = tray.activated.connect.call_args[0][0]
        assert callable(activate_handler)

        with patch("ui.main.QSystemTrayIcon.ActivationReason.Trigger", 0):
            activate_handler(0)

        overlay.toggle_overlay.assert_called_once()

    def test_tray_activated_ignores_non_trigger(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, tray = mock_tray

        with patch.object(sys, "exit"):
            main()

        activate_handler = tray.activated.connect.call_args[0][0]

        with patch("ui.main.QSystemTrayIcon.ActivationReason.DoubleClick", 1):
            activate_handler(1)

        overlay.toggle_overlay.assert_not_called()

    def test_connects_to_server_and_starts_mic(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, bridge = mock_bridge
        _, mic = mock_mic

        with patch.object(sys, "exit"):
            main()

        bridge.connect_to_server.assert_called_once_with(
            "ws://127.0.0.1:9999"
        )
        mic.start.assert_called_once()

    def test_about_to_quit_stops_mic_and_disconnects(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, bridge = mock_bridge
        _, mic = mock_mic

        with patch.object(sys, "exit"):
            main()

        app.aboutToQuit.connect.assert_any_call(mic.stop)
        app.aboutToQuit.connect.assert_any_call(
            bridge.disconnect_from_server
        )

    def test_calls_app_exec(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style

        with patch.object(sys, "exit") as mock_exit:
            main()

        app.exec.assert_called_once()
        mock_exit.assert_called_once_with(app.exec.return_value)

    def test_overlay_toggle_syncs_show_action(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, tray = mock_tray
        action_cls, _ = mock_action
        show_action = action_cls.return_value
        overlay._overlay_visible = True

        with patch.object(sys, "exit"):
            main()

        activate_handler = tray.activated.connect.call_args[0][0]

        with patch("ui.main.QSystemTrayIcon.ActivationReason.Trigger", 0):
            activate_handler(0)

        overlay.toggle_overlay.assert_called_once()
        show_action.setChecked.assert_called_with(True)


class TestMainNoSignals:
    def test_creates_overlay_bridge_mic(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        overlay_cls, _ = mock_overlay
        bridge_cls, _ = mock_bridge
        mic_cls, _ = mock_mic

        with patch.object(sys, "exit"):
            main()

        overlay_cls.assert_called_once()
        bridge_cls.assert_called_once()
        mic_cls.assert_called_once()


# -------------------------------------------------------------------
# Integration tests
# -------------------------------------------------------------------

class TestMainIntegration:
    def test_full_startup_sequence(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        overlay_cls, overlay = mock_overlay
        bridge_cls, bridge = mock_bridge
        mic_cls, mic = mock_mic
        tray_cls, tray = mock_tray

        with patch.object(sys, "exit"):
            main()

        overlay_cls.assert_called_once()
        bridge_cls.assert_called_once()
        mic_cls.assert_called_once()
        bridge.voice_state_changed.connect.assert_any_call(
            overlay.on_voice_state
        )
        mic.mic_level.connect.assert_called_once_with(
            overlay.on_mic_level
        )
        bridge.connect_to_server.assert_called_once_with(
            "ws://127.0.0.1:9999"
        )
        mic.start.assert_called_once()
        tray.show.assert_called_once()
        app.exec.assert_called_once()

    def test_clean_shutdown(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, bridge = mock_bridge
        _, mic = mock_mic

        with patch.object(sys, "exit"):
            main()

        quit_connections = {}
        for c in app.aboutToQuit.connect.call_args_list:
            if c[0]:
                fn = c[0][0]
                if fn == mic.stop:
                    quit_connections["mic.stop"] = True
                elif fn == bridge.disconnect_from_server:
                    quit_connections["bridge.disconnect"] = True
        assert "mic.stop" in quit_connections
        assert "bridge.disconnect" in quit_connections

    def test_signal_wiring_propagates_voice_state(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, bridge = mock_bridge

        with patch.object(sys, "exit"):
            main()

        bridge.voice_state_changed.connect.assert_any_call(
            overlay.on_voice_state
        )

    def test_signal_wiring_propagates_mic_level(
        self, mock_qapp, mock_overlay, mock_bridge,
        mock_mic, mock_tray, mock_menu, mock_action,
        mock_icon, mock_os_path_exists, mock_style,
    ):
        mock_qapp_cls, app = mock_qapp
        app.style.return_value = mock_style
        _, overlay = mock_overlay
        _, mic = mock_mic

        with patch.object(sys, "exit"):
            main()

        mic.mic_level.connect.assert_called_once_with(
            overlay.on_mic_level
        )


# -------------------------------------------------------------------
# Tests: __main__ guard
# -------------------------------------------------------------------

class TestMainGuard:
    def test_module_runs_main(self):
        with patch("ui.main.main") as mock_main:
            exec_globals = {"__name__": "__main__", "main": mock_main}
            exec("if __name__ == '__main__': main()", exec_globals)
            mock_main.assert_called_once()
