import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audio_source as src

try:
    import pyaudio  # noqa: E402
    _HAS_PYAUDIO = True
except ImportError:
    _HAS_PYAUDIO = False


class FakeStream:
    def __init__(self, chunks):
        self._chunks = list(chunks)
        self._idx = 0
        self.is_stopped = False

    def read(self, n, exception_on_overflow=False):
        if self._idx >= len(self._chunks):
            return b"\x00" * n
        c = self._chunks[self._idx]
        self._idx += 1
        return c

    def stop_stream(self):
        self.is_stopped = True

    def close(self):
        pass


class FakePyAudio:
    def __init__(self, chunks):
        self._chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return None

    def get_default_input_device_info(self):
        return {"index": 0}

    def open(self, **kw):
        return FakeStream(self._chunks)

    def terminate(self):
        pass


def test_available_true_when_pyaudio_present(monkeypatch):
    monkeypatch.setattr(src, "_PYAUDIO_AVAILABLE", True)
    monkeypatch.setattr(src, "_SOUNDDEVICE_AVAILABLE", False)
    ms = src.MicrophoneSource()
    assert ms.available is True


def test_available_true_when_sounddevice_present(monkeypatch):
    monkeypatch.setattr(src, "_PYAUDIO_AVAILABLE", False)
    monkeypatch.setattr(src, "_SOUNDDEVICE_AVAILABLE", True)
    ms = src.MicrophoneSource()
    assert ms.available is True


def test_available_false_when_both_missing(monkeypatch):
    monkeypatch.setattr(src, "_PYAUDIO_AVAILABLE", False)
    monkeypatch.setattr(src, "_SOUNDDEVICE_AVAILABLE", False)
    ms = src.MicrophoneSource()
    assert ms.available is False


def test_read_frame_returns_fixed_size(monkeypatch):
    if not _HAS_PYAUDIO:
        return
    frame = b"\x01\x00" * 1280
    fake = FakePyAudio([frame, frame])
    monkeypatch.setattr(src, "pyaudio", pyaudio)
    monkeypatch.setattr(pyaudio, "PyAudio", lambda: fake)
    monkeypatch.setattr(src, "_PYAUDIO_AVAILABLE", True)
    monkeypatch.setattr(src, "_SOUNDDEVICE_AVAILABLE", False)
    ms = src.MicrophoneSource()
    ms.open()
    got = ms.read_frame()
    ms.close()
    assert len(got) == 2560
    assert got == frame
