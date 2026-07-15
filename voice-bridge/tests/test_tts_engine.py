import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tts_engine as te

import numpy as np  # noqa: E402


class FakeKokoro:
    def __init__(self):
        self.calls = 0

    def create(self, text, voice):
        self.calls += 1
        yield (None, None, np.zeros(2400, dtype="float32"))  # 100ms @24k


def test_synth_uses_kokoro_when_available(monkeypatch):
    monkeypatch.setattr(te, "_load_kokoro", lambda *a, **k: ("pipe", FakeKokoro()))
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._pipeline = FakeKokoro()
    eng._kokoro_voice = "af_bella"
    eng.available = True
    eng._queue = te.PlaybackQueue()
    audio = eng.synth("hello")
    assert isinstance(audio, (bytes, bytearray)) and len(audio) > 0


def test_flush_stops_playback(monkeypatch):
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._queue = te.PlaybackQueue()
    eng.available = True
    eng.flush()
    assert eng._queue.aborted is True


def test_fallback_when_kokoro_absent(monkeypatch):
    monkeypatch.setattr(te, "_KOKORO_AVAILABLE", False)
    eng = te.TTSEngine()
    assert eng.available is False
    assert eng.synth("hi") == b""  # caller must use pyttsx3 / WS
