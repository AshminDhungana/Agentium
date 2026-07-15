import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import main as bridge

import numpy as np  # noqa: E402


def test_capture_returns_transcript_on_vad_end(monkeypatch):
    class FakeMic:
        available = True

        def open(self):
            pass

        def close(self):
            pass

        def __init__(self):
            self.frames = iter(
                [(np.ones(1280, dtype=np.int16) * 200).tobytes()] * 3
                + [(np.zeros(1280, dtype=np.int16)).tobytes()] * 20
            )

        def read_frame(self):
            return next(self.frames)

    def _fake_transcribe(wav):
        return "hello jarvis"

    monkeypatch.setattr(bridge, "MicrophoneSource", lambda *a, **k: FakeMic())
    monkeypatch.setattr(bridge, "_transcribe_via_backend", _fake_transcribe)
    monkeypatch.setattr(bridge, "_recognize_with_vosk", lambda a: None)

    class FakeVAD:
        available = True
        threshold = 0.5
        silence_base_ms = 700

        def __init__(self):
            self.n = 0

        def push_frame(self, f):
            self.n += 1
            return 1.0 if self.n <= 3 else 0.0

        def is_speech(self, s):
            return s == 1.0

    import asyncio

    out = asyncio.run(bridge._capture_utterance(FakeMic(), FakeVAD()))
    assert out == "hello jarvis"
