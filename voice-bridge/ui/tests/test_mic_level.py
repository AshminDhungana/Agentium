import sys
import os
import struct
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

import ui.mic_level as mic_level  # noqa: E402
from ui.mic_level import MicLevelCapture  # noqa: E402


# -------------------------------------------------------------------
# Helpers
# -------------------------------------------------------------------

def _int16_samples(*values):
    """Pack int16 samples into bytes (little-endian)."""
    return struct.pack("<" + "h" * len(values), *values)


# -------------------------------------------------------------------
# Fixtures
# -------------------------------------------------------------------

@pytest.fixture(autouse=True)
def mock_qt_multimedia():
    with (
        patch("ui.mic_level.QMediaDevices") as md_cls,
        patch("ui.mic_level.QAudioSource") as src_cls,
        patch("ui.mic_level.QTimer") as timer_cls,
    ):
        md_cls.audioInputs.return_value = [MagicMock()]
        yield md_cls, src_cls, timer_cls


@pytest.fixture
def capture(mock_qt_multimedia):
    _, src_cls, timer_cls = mock_qt_multimedia
    src_cls.return_value = MagicMock()
    timer_cls.return_value = MagicMock()
    c = MicLevelCapture()
    c._timer = timer_cls.return_value
    return c


@pytest.fixture
def capture_with_device(mock_qt_multimedia, capture):
    device = MagicMock()
    capture._io_device = device
    return capture, device


# -------------------------------------------------------------------
# Tests
# -------------------------------------------------------------------

class TestInit:
    def test_default_state(self, mock_qt_multimedia, capture):
        assert capture._audio_source is None
        assert capture._io_device is None
        assert capture._buffer == b""

    def test_timer_interval(self, capture):
        capture._timer.setInterval.assert_called_once_with(33)

    def test_timer_signal_connected(self, capture):
        capture._timer.timeout.connect.assert_called_once_with(
            capture._read_level
        )


class TestStart:
    def test_queries_audio_devices(self, mock_qt_multimedia, capture):
        md_cls, _, _ = mock_qt_multimedia
        capture.start()
        md_cls.audioInputs.assert_called_once()

    def test_starts_timer(self, capture):
        capture.start()
        capture._timer.start.assert_called_once()

    def test_configures_audio_format(self, mock_qt_multimedia, capture):
        _, src_cls, _ = mock_qt_multimedia
        capture.start()
        src_cls.assert_called_once()
        _fmt = src_cls.call_args[0][1]
        from PySide6.QtMultimedia import QAudioFormat
        assert _fmt.sampleRate() == 16000
        assert _fmt.channelCount() == 1
        assert _fmt.sampleFormat() == QAudioFormat.Int16

    def test_safe_when_no_devices(self, mock_qt_multimedia, capture):
        md_cls, _, _ = mock_qt_multimedia
        md_cls.audioInputs.return_value = []
        capture.start()
        capture._timer.start.assert_not_called()

    def test_stores_io_device(self, capture):
        capture.start()
        assert capture._io_device is not None


class TestStop:
    def test_stops_timer(self, capture):
        capture._timer.isActive.return_value = True
        capture.stop()
        capture._timer.stop.assert_called_once()

    def test_stops_audio_source(self, capture):
        src = MagicMock()
        capture._audio_source = src
        capture.stop()
        src.stop.assert_called_once()

    def test_clears_audio_source(self, capture):
        capture._audio_source = MagicMock()
        capture.stop()
        assert capture._audio_source is None
        assert capture._io_device is None

    def test_safe_when_no_audio_source(self, capture):
        capture._audio_source = None
        capture.stop()


class TestReadLevel:
    def test_noop_when_no_device(self, capture):
        capture._read_level()

    def test_reads_from_device(self, capture_with_device):
        cap, dev = capture_with_device
        dev.read.return_value = _int16_samples(*([0] * 480))
        cap._read_level()
        dev.read.assert_called_once_with(960)

    def test_noop_when_device_returns_nothing(self, capture_with_device):
        cap, dev = capture_with_device
        dev.read.return_value = b""
        cap._read_level()
        assert cap._buffer == b""

    def test_noop_when_device_returns_none(self, capture_with_device):
        cap, dev = capture_with_device
        dev.read.return_value = None
        cap._read_level()
        assert cap._buffer == b""

    def test_accumulates_buffer(self, capture_with_device):
        cap, dev = capture_with_device
        dev.read.return_value = _int16_samples(1, 2, 3, 4)
        cap._read_level()
        assert cap._buffer == _int16_samples(1, 2, 3, 4)

    def test_does_not_emit_below_window(self, capture_with_device):
        cap, dev = capture_with_device
        spy = MagicMock()
        cap.mic_level.connect(spy)
        dev.read.return_value = _int16_samples(*([100] * 100))
        cap._read_level()
        spy.assert_not_called()

    def test_emits_after_full_window(self, capture_with_device):
        cap, dev = capture_with_device
        spy = MagicMock()
        cap.mic_level.connect(spy)
        samples = [100] * 960
        dev.read.return_value = _int16_samples(*samples)
        cap._buffer = _int16_samples(*([0] * 960))
        cap._read_level()
        spy.assert_called_once()
        val = spy.call_args[0][0]
        assert 0.0 <= val <= 1.0
        assert isinstance(val, float)

    def test_silence_emits_zero(self, capture_with_device):
        cap, dev = capture_with_device
        spy = MagicMock()
        cap.mic_level.connect(spy)
        samples = [0] * 960
        dev.read.return_value = _int16_samples(*samples)
        cap._buffer = _int16_samples(*([0] * 960))
        cap._read_level()
        spy.assert_called_once_with(0.0)

    def test_full_scale_emits_one(self, capture_with_device):
        cap, dev = capture_with_device
        spy = MagicMock()
        cap.mic_level.connect(spy)
        samples = [32767] * 960
        dev.read.return_value = _int16_samples(*samples)
        cap._buffer = _int16_samples(*([32767] * 960))
        cap._read_level()
        val = spy.call_args[0][0]
        assert val == pytest.approx(1.0, abs=1e-4)

    def test_sliding_window_trims_buffer(self, capture_with_device):
        cap, dev = capture_with_device
        chunk = _int16_samples(*([100] * 960))
        dev.read.return_value = chunk
        cap._buffer = _int16_samples(*([0] * 2000))
        cap._read_level()
        assert len(cap._buffer) == 1920

    def test_emits_float(self, capture_with_device):
        cap, dev = capture_with_device
        spy = MagicMock()
        cap.mic_level.connect(spy)
        samples = [500] * 960
        dev.read.return_value = _int16_samples(*samples)
        cap._buffer = _int16_samples(*([0] * 960))
        cap._read_level()
        assert isinstance(spy.call_args[0][0], float)


class TestIntegration:
    def test_start_stop_no_crash(self, mock_qt_multimedia):
        _, src_cls, _ = mock_qt_multimedia
        src_cls.return_value = MagicMock()
        c = MicLevelCapture()
        c.start()
        c.stop()

    def test_double_start_no_crash(self, mock_qt_multimedia):
        _, src_cls, _ = mock_qt_multimedia
        src_cls.return_value = MagicMock()
        c = MicLevelCapture()
        c.start()
        c.start()
        c.stop()

    def test_double_stop_no_crash(self, mock_qt_multimedia):
        _, src_cls, _ = mock_qt_multimedia
        src_cls.return_value = MagicMock()
        c = MicLevelCapture()
        c.stop()
        c.stop()
