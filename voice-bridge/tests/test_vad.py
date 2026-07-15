import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import vad as v

import numpy as np  # noqa: E402


class FakeVADIterator:
    def __init__(self, model):
        self.model = model

    def __call__(self, chunk):
        # chunk: 512-sample int16. Return speech if mean abs > 0 (synthetic speech)
        return {"start": 0} if abs(int(chunk.mean())) > 0 else {}


def test_push_frame_returns_probability(monkeypatch):
    monkeypatch.setattr(v, "_load_silero", lambda: object())
    monkeypatch.setattr(v, "VADIterator", lambda m: FakeVADIterator(m))
    vad = v.VAD.__new__(v.VAD)
    vad._model = object()
    vad._iter = FakeVADIterator(object())
    vad.available = True
    vad.threshold = 0.5
    vad.silence_base_ms = 700
    vad.noise_suppression = False
    vad._buf = np.zeros(0, dtype=np.int16)
    speech = (np.ones(1280, dtype=np.int16) * 200).tobytes()  # 80ms loud
    silent = (np.zeros(1280, dtype=np.int16)).tobytes()
    vad.push_frame(speech)
    prob = vad.push_frame(speech)
    assert prob is not None and vad.is_speech(prob)


def test_dynamic_endpoint_extends_on_incomplete():
    # Trailing "and" -> wait longer before closing the turn.
    assert v.VAD.should_endpoint("please turn on the light and", 200, 700) is False
    # Complete question -> close immediately.
    assert v.VAD.should_endpoint("what time is it?", 800, 700) is True
    # Long silence on complete phrase -> close.
    assert v.VAD.should_endpoint("turn it off", 1500, 700) is True


def test_aec_reduces_playback_echo(monkeypatch):
    class FakeAec:
        def process(self, playback, mic):
            return b"\x00" * len(mic)

    monkeypatch.setattr(v, "_AEC_AVAILABLE", True)
    monkeypatch.setattr(v, "Aec", lambda: FakeAec())
    vad = v.VAD.__new__(v.VAD)
    vad.available = True
    mic = (np.ones(1280, dtype=np.int16) * 100).tobytes()
    pb = (np.ones(1280, dtype=np.int16) * 100).tobytes()
    out = vad.apply_aec(mic, pb)
    assert out == b"\x00" * len(mic)  # echo cancelled


def test_noise_suppression_passthrough_when_missing(monkeypatch):
    monkeypatch.setattr(v, "_NS_AVAILABLE", False)
    vad = v.VAD.__new__(v.VAD)
    vad.available = True
    frame = (np.ones(1280, dtype=np.int16) * 50).tobytes()
    assert vad.apply_noise_suppression(frame) == frame  # no-op fallback
