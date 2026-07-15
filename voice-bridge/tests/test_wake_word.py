import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import wake_word as ww

import numpy as np  # noqa: E402


class FakeModel:
    def __init__(self):
        self.calls = 0

    def predict(self, audio):
        self.calls += 1
        # audio: int16 np array length 16000. Return high score only when the
        # buffer has non-zero mean (our synthetic "trigger" pattern).
        return {"hey_jarvis": 0.9 if int(audio.mean()) > 0 else 0.01}


def _make_detector(monkeypatch):
    fake = FakeModel()
    monkeypatch.setattr(ww, "_load_model", lambda *a, **k: fake)
    det = ww.WakeWordDetector.__new__(ww.WakeWordDetector)
    det._model = fake
    det._buf = np.zeros(0, dtype=np.int16)
    det.available = True
    det.threshold = 0.5
    return det


def test_push_frame_buffers_to_one_second(monkeypatch):
    det = _make_detector(monkeypatch)
    frame = (np.ones(1280, dtype=np.int16) * 1).tobytes()  # 80ms trigger-ish
    scores = [det.push_frame(frame) for _ in range(13)]  # 13*80ms > 1s, 1 fires
    fired = [s for s in scores if s is not None]
    assert len(fired) >= 1
    assert max(fired) >= 0.9


def test_no_score_before_one_second(monkeypatch):
    det = _make_detector(monkeypatch)
    frame = (np.zeros(1280, dtype=np.int16)).tobytes()
    assert det.push_frame(frame) is None  # < 1s buffered yet
