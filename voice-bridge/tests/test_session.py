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


def test_wake_triggers_session_and_chime(monkeypatch):
    import asyncio

    state = {"phase": "IDLE", "chime": 0, "session": 0}

    class FakeMic:
        available = True

        def open(self):
            pass

        def close(self):
            pass

        def __init__(self):
            self.n = 0

        def read_frame(self):
            self.n += 1
            # frame 2 is the "trigger" (high amplitude); rest silent
            if self.n == 2:
                return (np.ones(1280, dtype=np.int16) * 1).tobytes()
            return (np.zeros(1280, dtype=np.int16)).tobytes()

    class _TriggeredDetector:
        available = True
        threshold = 0.5

        def __init__(self):
            self.n = 0

        def push_frame(self, frame):
            self.n += 1
            return 0.9 if self.n == 2 else None

        def is_triggered(self, s):
            return s is not None and s >= self.threshold

    monkeypatch.setattr(bridge, "MicrophoneSource", lambda *a, **k: FakeMic())
    monkeypatch.setattr(bridge, "WakeWordDetector", lambda *a, **k: _TriggeredDetector())
    monkeypatch.setattr(bridge, "_play_wake_chime", lambda: state.__setitem__("chime", 1))
    monkeypatch.setattr(bridge, "VAD", lambda *a, **k: _SilentVAD())
    monkeypatch.setattr(bridge, "TTSEngine", lambda *a, **k: _NoopTTS())

    orig_run = bridge.VoiceSession.run

    async def _once(self):
        state["session"] = 1
        await orig_run(self)
        raise asyncio.CancelledError()

    monkeypatch.setattr(bridge.VoiceSession, "run", _once)

    # End the session quickly: capture returns None after first call.
    cap_calls = {"n": 0}

    async def _cap(mic, vad=None, timeout=8.0):
        cap_calls["n"] += 1
        return None if cap_calls["n"] > 1 else "hello"

    monkeypatch.setattr(bridge, "_capture_utterance", _cap)

    async def go():
        await bridge._run_voice_loop_once()

    try:
        asyncio.run(go())
    except asyncio.CancelledError:
        pass
    assert state["chime"] == 1, "wake chime should play"
    assert state["session"] == 1, "session should start after wake"


def test_barge_in_interrupts_speaking(monkeypatch):
    import asyncio

    state = {"phase": "IDLE"}
    orig_broadcast = bridge.VoiceSession._broadcast_state

    async def spy(self, s):
        state["phase"] = s
        await orig_broadcast(self, s)

    monkeypatch.setattr(bridge.VoiceSession, "_broadcast_state", spy)

    class FakeTTS:
        available = True

        def __init__(self):
            self.cancelled = False

        def synth(self, text):
            return b"audio"

        def play(self, audio):
            pass

        def flush(self):
            self.cancelled = True

    class FakeMic:
        available = True

        def open(self):
            pass

        def close(self):
            pass

        def __init__(self):
            self.n = 0

        def read_frame(self):
            self.n += 1
            if state["phase"] == "SPEAKING" and self.n >= 3:
                return (np.ones(1280, dtype=np.int16) * 200).tobytes()
            return (np.zeros(1280, dtype=np.int16)).tobytes()

    class FakeVAD:
        available = True
        threshold = 0.5
        silence_base_ms = 700

        def __init__(self):
            self.n = 0

        def push_frame(self, f):
            self.n += 1
            return 1.0 if state["phase"] == "SPEAKING" and self.n >= 3 else 0.0

        def is_speech(self, s):
            return s == 1.0

    monkeypatch.setattr(bridge, "MicrophoneSource", lambda *a, **k: FakeMic())
    monkeypatch.setattr(bridge, "VAD", lambda *a, **k: FakeVAD())
    tts = FakeTTS()
    monkeypatch.setattr(bridge, "TTSEngine", lambda *a, **k: tts)

    async def _q(_):
        return "This is a long answer that should be interrupted."

    monkeypatch.setattr(bridge, "query_backend", _q)

    cap_calls = {"n": 0}

    async def _cap(mic, vad=None, timeout=8.0):
        cap_calls["n"] += 1
        return "hello" if cap_calls["n"] == 1 else None

    monkeypatch.setattr(bridge, "_capture_utterance", _cap)

    async def run():
        sess = bridge.VoiceSession(FakeMic(), FakeVAD(), tts)
        await sess.run()

    try:
        asyncio.run(run())
    except Exception:
        pass
    assert tts.cancelled is True, "TTS should be flushed on barge-in"
    assert state["phase"] in ("INTERRUPTED", "LISTENING", "IDLE")


class _SilentVAD:
    available = True
    threshold = 0.5
    silence_base_ms = 700

    def push_frame(self, f):
        return 0.0

    def is_speech(self, s):
        return False


class _NoopTTS:
    available = False

    def synth(self, t):
        return b""

    def play(self, a):
        pass

    def flush(self):
        pass


def test_stream_chat_yields_sentences(monkeypatch):
    import asyncio, json

    sse = (
        b'data: {"type":"content","content":"The time is "}\n\n'
        b'data: {"type":"content","content":"ten o\'clock."}\n\n'
        b'data: {"type":"done"}\n\n'
    )

    class FakeResp:
        def __init__(self):
            self._it = iter([sse])

        def read(self, n=-1):
            try:
                return next(self._it)
            except StopIteration:
                return b""

    def _fake_urlopen(req, timeout=None):
        body = req.data.decode()
        assert '"stream": true' in body, "must request streaming"
        r = FakeResp()
        r.__enter__ = lambda: r
        r.__exit__ = lambda *a: None
        return r

    monkeypatch.setattr(bridge, "VOICE_TOKEN", "t")
    monkeypatch.setattr("urllib.request.urlopen", _fake_urlopen)

    async def go():
        out = [c async for c in bridge._stream_chat("time?")]
        return out

    out = asyncio.run(go())
    assert "".join(out) == "The time is ten o'clock."


def test_first_sentence_spoken_before_last(monkeypatch):
    import asyncio

    chunks = ["First sentence. ", "Second sentence. ", "Third sentence."]

    class FakeTTS:
        available = True

        def __init__(self):
            self.order = []

        def synth(self, t):
            self.order.append(t)
            return b"audio"

        def play(self, a):
            pass

        def flush(self):
            pass

    class _SilentMic:
        available = True

        def open(self):
            pass

        def close(self):
            pass

        def read_frame(self):
            return (np.zeros(1280, dtype=np.int16)).tobytes()

    class _NoSpeechVAD:
        available = True
        threshold = 0.5
        silence_base_ms = 700

        def push_frame(self, f):
            return 0.0

        def is_speech(self, s):
            return False

    monkeypatch.setattr(bridge, "MicrophoneSource", lambda *a, **k: _SilentMic())
    monkeypatch.setattr(bridge, "VAD", lambda *a, **k: _NoSpeechVAD())
    monkeypatch.setattr(bridge, "TTSEngine", lambda *a, **k: FakeTTS())

    async def _stream():
        for c in chunks:
            yield c

    monkeypatch.setattr(bridge, "_stream_chat", lambda *a, **k: _stream())

    # Capture returns a dummy text so run() proceeds into SPEAKING.
    cap_calls = {"n": 0}

    async def _cap(mic, vad=None, timeout=8.0):
        cap_calls["n"] += 1
        return "go" if cap_calls["n"] == 1 else None

    monkeypatch.setattr(bridge, "_capture_utterance", _cap)

    tts = FakeTTS()

    async def run():
        sess = bridge.VoiceSession(_SilentMic(), _NoSpeechVAD(), tts, barge_in=False)
        await sess.run()

    try:
        asyncio.run(run())
    except Exception:
        pass
    assert tts.order and tts.order[0].startswith("First"), tts.order
