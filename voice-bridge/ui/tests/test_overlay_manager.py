import sys
import os
from unittest.mock import MagicMock, patch, ANY

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

import ui.overlay_manager as ovm  # noqa: E402
from ui.overlay_manager import OverlayManager, _enable_acrylic  # noqa: E402


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

@pytest.fixture
def mock_quickview():
    with patch("ui.overlay_manager.QQuickView") as cls:
        view = MagicMock()
        root = MagicMock()
        view.rootObject.return_value = root
        cls.return_value = view
        yield cls, view, root


@pytest.fixture
def mock_qtimer():
    with patch("ui.overlay_manager.QTimer") as cls:
        timer = MagicMock()
        cls.return_value = timer
        yield cls, timer


@pytest.fixture
def mock_qguiapplication():
    with patch("ui.overlay_manager.QGuiApplication") as cls:
        yield cls


@pytest.fixture
def overlay(mock_quickview, mock_qtimer):
    _, view, root = mock_quickview
    _, timer = mock_qtimer
    mgr = OverlayManager()
    mgr._overlay_view = view
    mgr._overlay_root = root
    mgr._indicator_view = view
    mgr._indicator_root = root
    mgr._auto_hide_timer = timer
    return mgr, view, root, timer


@pytest.fixture
def overlay_no_root(mock_quickview, mock_qtimer):
    cls, view, _ = mock_quickview
    view.rootObject.return_value = None
    _, timer = mock_qtimer
    mgr = OverlayManager()
    mgr._overlay_view = view
    mgr._overlay_root = None
    mgr._indicator_view = view
    mgr._indicator_root = None
    mgr._auto_hide_timer = timer
    return mgr, view, timer


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

class TestInit:
    def test_default_state(self, mock_quickview, mock_qtimer):
        _, view, root = mock_quickview
        _, timer = mock_qtimer
        mgr = OverlayManager()
        assert mgr._overlay_visible is False

    def test_configures_auto_hide_timer(self, mock_quickview, mock_qtimer):
        _, view, root = mock_quickview
        cls, timer = mock_qtimer
        mgr = OverlayManager()
        timer.setSingleShot.assert_called_once_with(True)
        timer.setInterval.assert_called_once_with(1500)
        timer.timeout.connect.assert_called_once_with(mgr._on_auto_hide)

    def test_loads_waveform_overlay_qml(self, mock_quickview, mock_qtimer):
        cls, view, root = mock_quickview
        mgr = OverlayManager()
        view.setSource.assert_any_call(ANY)

    def test_loads_speaking_indicator_qml(self, mock_quickview, mock_qtimer):
        cls, view, root = mock_quickview
        mgr = OverlayManager()
        assert view.setSource.call_count == 2

    def test_sets_resize_mode(self, mock_quickview, mock_qtimer):
        cls, view, root = mock_quickview
        mgr = OverlayManager()
        assert view.setResizeMode.call_count == 2
        view.setResizeMode.assert_called_with(ANY)

    def test_sets_transparent_color(self, mock_quickview, mock_qtimer):
        cls, view, root = mock_quickview
        mgr = OverlayManager()
        assert view.setColor.call_count == 2
        view.setColor.assert_called_with("transparent")

    def test_initialises_root_properties(self, mock_quickview, mock_qtimer):
        _, view, root = mock_quickview
        mgr = OverlayManager()
        root.setProperty.assert_any_call("micLevel", 0.0)
        root.setProperty.assert_any_call("voiceState", "idle")

    def test_safe_when_no_root_object(self, mock_quickview, mock_qtimer):
        cls, view, _ = mock_quickview
        view.rootObject.return_value = None
        mgr = OverlayManager()


class TestToggleOverlay:
    def test_toggle_shows_when_hidden(self, overlay):
        mgr, view, root, timer = overlay
        mgr._overlay_visible = False
        with patch.object(mgr, "show_overlay") as show:
            mgr.toggle_overlay()
            show.assert_called_once()

    def test_toggle_hides_when_visible(self, overlay):
        mgr, view, root, timer = overlay
        mgr._overlay_visible = True
        with patch.object(mgr, "hide_overlay") as hide:
            mgr.toggle_overlay()
            hide.assert_called_once()


class TestShowOverlay:
    def test_shows_view(self, overlay):
        mgr, view, root, timer = overlay
        mgr.show_overlay()
        view.show.assert_called_once()

    def test_sets_opacity(self, overlay):
        mgr, view, root, timer = overlay
        mgr.show_overlay()
        root.setProperty.assert_any_call("opacity", 1.0)

    def test_sets_visible_flag(self, overlay):
        mgr, view, root, timer = overlay
        mgr.show_overlay()
        assert mgr._overlay_visible is True

    def test_centers_on_cursor(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "_center_on_cursor") as center:
            mgr.show_overlay()
            center.assert_called_once()

    def test_applies_acrylic(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "_apply_acrylic") as acrylic:
            mgr.show_overlay()
            acrylic.assert_called_once_with(view)

    def test_safe_when_no_root(self, overlay_no_root):
        mgr, view, timer = overlay_no_root
        mgr.show_overlay()
        assert mgr._overlay_visible is True


class TestHideOverlay:
    def test_sets_opacity_to_zero(self, overlay):
        mgr, view, root, timer = overlay
        mgr.hide_overlay()
        root.setProperty.assert_any_call("opacity", 0.0)

    def test_schedules_hide_with_single_shot(self, overlay):
        mgr, view, root, timer = overlay
        with patch("ui.overlay_manager.QTimer.singleShot") as ss:
            mgr.hide_overlay()
            ss.assert_called_once_with(200, view.hide)

    def test_sets_visible_flag_false(self, overlay):
        mgr, view, root, timer = overlay
        mgr._overlay_visible = True
        mgr.hide_overlay()
        assert mgr._overlay_visible is False

    def test_safe_when_no_root(self, overlay_no_root):
        mgr, view, timer = overlay_no_root
        mgr._overlay_visible = True
        mgr.hide_overlay()
        assert mgr._overlay_visible is False


class TestShowIndicator:
    def test_shows_view(self, overlay):
        mgr, view, root, timer = overlay
        mgr.show_indicator()
        view.show.assert_called_once()

    def test_sets_opacity(self, overlay):
        mgr, view, root, timer = overlay
        mgr.show_indicator()
        root.setProperty.assert_any_call("opacity", 1.0)

    def test_sets_active(self, overlay):
        mgr, view, root, timer = overlay
        mgr.show_indicator()
        root.setProperty.assert_any_call("active", True)

    def test_positions_bottom_right(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "_position_bottom_right") as pos:
            mgr.show_indicator()
            pos.assert_called_once()

    def test_applies_acrylic(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "_apply_acrylic") as acrylic:
            mgr.show_indicator()
            acrylic.assert_called_once_with(view)

    def test_safe_when_no_root(self, overlay_no_root):
        mgr, view, timer = overlay_no_root
        mgr.show_indicator()


class TestHideIndicator:
    def test_sets_active_false(self, overlay):
        mgr, view, root, timer = overlay
        mgr.hide_indicator()
        root.setProperty.assert_any_call("active", False)

    def test_sets_opacity_zero(self, overlay):
        mgr, view, root, timer = overlay
        mgr.hide_indicator()
        root.setProperty.assert_any_call("opacity", 0.0)

    def test_schedules_hide_with_single_shot(self, overlay):
        mgr, view, root, timer = overlay
        with patch("ui.overlay_manager.QTimer.singleShot") as ss:
            mgr.hide_indicator()
            ss.assert_called_once_with(300, view.hide)

    def test_safe_when_no_root(self, overlay_no_root):
        mgr, view, timer = overlay_no_root
        mgr.hide_indicator()


class TestOnVoiceState:
    def test_updates_root_voice_state(self, overlay):
        mgr, view, root, timer = overlay
        mgr.on_voice_state("listening")
        root.setProperty.assert_any_call("voiceState", "listening")

    @pytest.mark.parametrize("state", ["listening", "speaking", "interrupted", "idle"])
    def test_state_transitions(self, overlay, state):
        mgr, view, root, timer = overlay
        with (
            patch.object(mgr, "show_overlay") as show_o,
            patch.object(mgr, "hide_overlay") as hide_o,
            patch.object(mgr, "show_indicator") as show_i,
            patch.object(mgr, "hide_indicator") as hide_i,
        ):
            mgr.on_voice_state(state)
            if state == "listening":
                show_o.assert_called_once()
                hide_o.assert_not_called()
                show_i.assert_not_called()
                hide_i.assert_not_called()
            elif state == "speaking":
                show_o.assert_not_called()
                hide_o.assert_called_once()
                show_i.assert_called_once()
                hide_i.assert_not_called()
            elif state == "interrupted":
                show_o.assert_called_once()
                hide_o.assert_not_called()
                show_i.assert_not_called()
                hide_i.assert_called_once()
            elif state == "idle":
                show_o.assert_not_called()
                hide_o.assert_not_called()
                show_i.assert_not_called()
                hide_i.assert_called_once()

    def test_listening_stops_auto_hide_timer(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "show_overlay"):
            mgr.on_voice_state("listening")
            timer.stop.assert_called_once()

    def test_interrupted_stops_auto_hide_timer(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "show_overlay"), patch.object(mgr, "hide_indicator"):
            mgr.on_voice_state("interrupted")
            timer.stop.assert_called_once()

    def test_idle_starts_auto_hide_when_visible(self, overlay):
        mgr, view, root, timer = overlay
        mgr._overlay_visible = True
        with patch.object(mgr, "hide_indicator"):
            mgr.on_voice_state("idle")
            timer.start.assert_called_once()

    def test_idle_does_not_start_auto_hide_when_hidden(self, overlay):
        mgr, view, root, timer = overlay
        mgr._overlay_visible = False
        with patch.object(mgr, "hide_indicator"):
            mgr.on_voice_state("idle")
            timer.start.assert_not_called()

    def test_speaking_hides_overlay_shows_indicator(self, overlay):
        mgr, view, root, timer = overlay
        with (
            patch.object(mgr, "hide_overlay") as hide_o,
            patch.object(mgr, "show_indicator") as show_i,
        ):
            mgr.on_voice_state("speaking")
            hide_o.assert_called_once()
            show_i.assert_called_once()

    def test_interrupted_hides_indicator_shows_overlay(self, overlay):
        mgr, view, root, timer = overlay
        with (
            patch.object(mgr, "hide_indicator") as hide_i,
            patch.object(mgr, "show_overlay") as show_o,
        ):
            mgr.on_voice_state("interrupted")
            hide_i.assert_called_once()
            show_o.assert_called_once()

    def test_unknown_state_does_not_crash(self, overlay):
        mgr, view, root, timer = overlay
        mgr.on_voice_state("unknown")

    def test_safe_when_no_root(self, overlay_no_root):
        mgr, view, timer = overlay_no_root
        mgr.on_voice_state("listening")


class TestOnMicLevel:
    def test_updates_root_mic_level(self, overlay):
        mgr, view, root, timer = overlay
        mgr.on_mic_level(0.75)
        root.setProperty.assert_any_call("micLevel", 0.75)

    def test_safe_when_no_root(self, overlay_no_root):
        mgr, view, timer = overlay_no_root
        mgr.on_mic_level(0.5)


class TestAutoHide:
    def test_auto_hide_calls_hide_overlay(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "hide_overlay") as hide:
            mgr._on_auto_hide()
            hide.assert_called_once()

    def test_auto_hide_timer_configured(self, overlay):
        mgr, view, root, timer = overlay
        timer.setSingleShot.assert_called_once_with(True)
        timer.setInterval.assert_called_once_with(1500)


class TestCenterOnCursor:
    def test_centers_on_cursor(self, overlay, mock_qguiapplication):
        mgr, view, root, timer = overlay
        screen = MagicMock()
        screen.virtualGeometry().center.return_value = MagicMock()
        screen.virtualGeometry().center().x.return_value = 100
        screen.virtualGeometry().center().y.return_value = 100
        mock_qguiapplication.primaryScreen.return_value = screen
        mock_qguiapplication.screens.return_value = []
        view.width.return_value = 280
        view.height.return_value = 280
        mgr._center_on_cursor()
        view.setPosition.assert_called_once_with(-40, -40)

    def test_safe_when_no_screen(self, overlay, mock_qguiapplication):
        mgr, view, root, timer = overlay
        mock_qguiapplication.primaryScreen.return_value = None
        mgr._center_on_cursor()
        view.setPosition.assert_not_called()

    def test_uses_cursor_position(self, overlay, mock_qguiapplication):
        mgr, view, root, timer = overlay
        primary = MagicMock()
        primary.virtualGeometry().center.return_value = MagicMock()
        primary.virtualGeometry().center().x.return_value = 500
        primary.virtualGeometry().center().y.return_value = 500
        mock_qguiapplication.primaryScreen.return_value = primary

        screen = MagicMock()
        screen.geometry.return_value = MagicMock()
        screen.geometry().contains.return_value = True
        cursor = MagicMock()
        cursor.x.return_value = 1000
        cursor.y.return_value = 600
        screen.cursorPos.return_value = cursor
        mock_qguiapplication.screens.return_value = [screen]

        view.width.return_value = 280
        view.height.return_value = 280
        mgr._center_on_cursor()
        view.setPosition.assert_called_once_with(860, 460)


class TestPositionBottomRight:
    def test_positions_bottom_right(self, overlay, mock_qguiapplication):
        mgr, view, root, timer = overlay
        screen = MagicMock()
        geo = MagicMock()
        geo.right.return_value = 1920
        geo.bottom.return_value = 1080
        screen.availableGeometry.return_value = geo
        mock_qguiapplication.primaryScreen.return_value = screen
        view.width.return_value = 120
        view.height.return_value = 36
        mgr._position_bottom_right()
        view.setPosition.assert_called_once_with(1780, 1024)

    def test_safe_when_no_screen(self, overlay, mock_qguiapplication):
        mgr, view, root, timer = overlay
        mock_qguiapplication.primaryScreen.return_value = None
        mgr._position_bottom_right()
        view.setPosition.assert_not_called()


class TestApplyAcrylic:
    def test_calls_enable_acrylic(self, overlay):
        mgr, view, root, timer = overlay
        view.winId.return_value = 12345
        with patch("ui.overlay_manager._enable_acrylic") as ea:
            mgr._apply_acrylic(view)
            ea.assert_called_once_with(12345)


class TestEnableAcrylic:
    def test_noop_on_non_windows(self):
        with patch("sys.platform", "linux"):
            _enable_acrylic(12345)

    def test_calls_setwindowcompositionattribute(self):
        with patch("sys.platform", "win32"):
            mock_swca = MagicMock()
            with patch("ctypes.windll", create=True) as mock_windll:
                mock_windll.user32 = MagicMock()
                mock_windll.user32.SetWindowCompositionAttribute = mock_swca
                _enable_acrylic(12345)
                mock_swca.assert_called_once()

    def test_swallows_exception(self):
        with patch("sys.platform", "win32"):
            with patch("ctypes.windll", create=True) as mock_windll:
                mock_windll.user32 = MagicMock()
                mock_windll.user32.SetWindowCompositionAttribute.side_effect = Exception("fail")
                _enable_acrylic(12345)


class TestIntegration:
    def test_full_listening_speaking_idle_cycle(self, overlay):
        mgr, view, root, timer = overlay
        with (
            patch.object(mgr, "show_overlay") as show_o,
            patch.object(mgr, "hide_overlay") as hide_o,
            patch.object(mgr, "show_indicator") as show_i,
            patch.object(mgr, "hide_indicator") as hide_i,
        ):
            mgr.on_voice_state("listening")
            show_o.assert_called_once()
            timer.stop.assert_called_once()

            hide_o.reset_mock()
            show_i.reset_mock()
            mgr.on_voice_state("speaking")
            hide_o.assert_called_once()
            show_i.assert_called_once()

            hide_o.reset_mock()
            show_o.reset_mock()
            hide_i.reset_mock()
            mgr.on_voice_state("interrupted")
            hide_i.assert_called_once()
            show_o.assert_called_once()

            hide_i.reset_mock()
            mgr._overlay_visible = True
            mgr.on_voice_state("idle")
            hide_i.assert_called_once()
            timer.start.assert_called_once()

    def test_toggle_overlay_cycle(self, overlay):
        mgr, view, root, timer = overlay
        mgr._overlay_visible = False
        with patch.object(mgr, "show_overlay") as show_o:
            mgr.toggle_overlay()
            show_o.assert_called_once()

        mgr._overlay_visible = True
        with patch.object(mgr, "hide_overlay") as hide_o:
            mgr.toggle_overlay()
            hide_o.assert_called_once()

    def test_acrylic_applied_on_show(self, overlay):
        mgr, view, root, timer = overlay
        with patch.object(mgr, "_apply_acrylic") as aa:
            mgr.show_overlay()
            aa.assert_called_once_with(view)

            aa.reset_mock()
            mgr.show_indicator()
            aa.assert_called_once_with(view)

    def test_on_mic_level_updates_root(self, overlay):
        mgr, view, root, timer = overlay
        mgr.on_mic_level(0.42)
        root.setProperty.assert_called_with("micLevel", 0.42)
