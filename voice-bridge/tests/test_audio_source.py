import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import audio_source as src

import pyaudio  # noqa: E402


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


def test_read_frame_returns_fixed_size(monkeypatch):
    frame = b"\x01\x00" * 1280  # 2560 bytes = 80ms @16k/16bit
    fake = FakePyAudio([frame, frame])
    monkeypatch.setattr(pyaudio, "PyAudio", lambda: fake)
    src.MicrophoneSource.RATE = 16000
    src.MicrophoneSource.FRAME_BYTES = 2560
    ms = src.MicrophoneSource()
    ms.open()
    got = ms.read_frame()
    ms.close()
    assert len(got) == 2560
    assert got == frame


def test_available_false_when_pyaudio_missing(monkeypatch):
    # _PYAUDIO_AVAILABLE is cached at import time; patch the flag directly.
    monkeypatch.setattr(src, "_PYAUDIO_AVAILABLE", False)
    ms = src.MicrophoneSource()
    assert ms.available is False
