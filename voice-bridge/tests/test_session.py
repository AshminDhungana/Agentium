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

    monkeypatch.setattr(bridge, "SR_AVAILABLE", True)
    monkeypatch.setattr(bridge, "MicrophoneSource", lambda *a, **k: FakeMic())
    monkeypatch.setattr(bridge, "WakeWordDetector", lambda *a, **k: _TriggeredDetector())
    monkeypatch.setattr(bridge, "_play_wake_chime", lambda: state.__setitem__("chime", 1))
    monkeypatch.setattr(bridge, "VAD", lambda *a, **k: _SilentVAD())
    monkeypatch.setattr(bridge, "TTSEngine", lambda *a, **k: _NoopTTS())

    async def _once(self):
        state["session"] = 1
        raise asyncio.CancelledError()

    monkeypatch.setattr(bridge.VoiceSession, "run", _once)

    # End the session quickly: capture returns None after first call.
    cap_calls = {"n": 0}

    async def _cap(mic, vad=None, timeout=8.0, **kwargs):
        cap_calls["n"] += 1
        return None if cap_calls["n"] > 1 else "hello"

    async def _fake_stream(*a, **k):
        if False:
            yield ""

    monkeypatch.setattr(bridge, "_capture_utterance", _cap)
    monkeypatch.setattr(bridge, "_stream_chat", _fake_stream)
    monkeypatch.setattr(bridge, "_maybe_handle_pending_card", lambda: asyncio.sleep(0))

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
            self._playing = False

        @property
        def is_playing(self):
            return self._playing and not self.cancelled

        def synth(self, text):
            return b"audio"

        def play(self, audio):
            self._playing = True

        def flush(self):
            self.cancelled = True
            self._playing = False

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
            if state["phase"].upper() == "SPEAKING" and self.n >= 3:
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
            return 1.0 if state["phase"].upper() == "SPEAKING" and self.n >= 3 else 0.0

        def is_speech(self, s):
            return s == 1.0

    monkeypatch.setattr(bridge, "MicrophoneSource", lambda *a, **k: FakeMic())
    monkeypatch.setattr(bridge, "VAD", lambda *a, **k: FakeVAD())
    tts = FakeTTS()
    monkeypatch.setattr(bridge, "TTSEngine", lambda *a, **k: tts)

    async def _stream(*a, **k):
        yield "This is a long answer that should be interrupted. "

    monkeypatch.setattr(bridge, "_stream_chat", _stream)

    cap_calls = {"n": 0}

    async def _cap(mic, vad=None, timeout=8.0, **kwargs):
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
    assert state["phase"].upper() in ("INTERRUPTED", "LISTENING", "IDLE")


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


class _FakeAiohttpContent:
    def __init__(self, lines):
        self._lines = list(lines)
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._lines):
            raise StopAsyncIteration
        val = self._lines[self._idx]
        self._idx += 1
        return val


class _FakeAiohttpResponse:
    def __init__(self, lines):
        self.content = _FakeAiohttpContent(lines)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _FakeAiohttpSession:
    def __init__(self, lines, on_post=None):
        self.lines = lines
        self.on_post = on_post

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def post(self, url, **kwargs):
        if self.on_post:
            self.on_post(url, kwargs)
        return _FakeAiohttpResponse(self.lines)


def test_stream_chat_yields_sentences(monkeypatch):
    import asyncio, aiohttp

    lines = [
        b'data: {"type":"content","content":"The time is "}\n',
        b"data: {\"type\":\"content\",\"content\":\"ten o'clock.\"}\n",
        b'data: {"type":"done"}\n',
    ]

    def _post_check(url, kwargs):
        body = kwargs.get("json", {})
        assert body.get("stream") is True, "must request streaming"

    monkeypatch.setattr(bridge, "VOICE_TOKEN", "t")
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeAiohttpSession(lines, _post_check))

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

    async def _stream(*a, **k):
        for c in chunks:
            yield c

    monkeypatch.setattr(bridge, "_stream_chat", _stream)

    # Capture returns a dummy text so run() proceeds into SPEAKING.
    cap_calls = {"n": 0}

    async def _cap(mic, vad=None, timeout=8.0, **kwargs):
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


def test_load_persona_reads_env(monkeypatch):
    monkeypatch.setattr(bridge, "VOICE_PERSONA", "You are Jarvis.")
    assert bridge._load_persona() == "You are Jarvis."


def test_load_persona_reads_file_when_no_env(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "VOICE_PERSONA", "")
    fake = tmp_path / "persona.md"
    fake.write_text("You are Jarvis.")
    monkeypatch.setattr(bridge, "Path", lambda *a, **k: fake)
    assert "Jarvis" in bridge._load_persona()


def test_proactive_disabled_by_default(monkeypatch):
    monkeypatch.setattr(bridge, "VOICE_PROACTIVE_ENABLED", False)
    ann = bridge.ProactiveAnnouncer()
    assert ann.enabled is False
    assert ann.maybe_announce("agent_crashed") is None


def test_proactive_announces_when_enabled(monkeypatch):
    monkeypatch.setattr(bridge, "VOICE_PROACTIVE_ENABLED", True)
    ann = bridge.ProactiveAnnouncer()
    line = ann.maybe_announce("agent_crashed")
    assert line is not None
    # second call within cooldown is suppressed
    assert ann.maybe_announce("agent_crashed") is None


def test_identify_speaker_returns_name(monkeypatch):
    import json

    class FakeResp:
        def read(self):
            return json.dumps(
                {"speaker_id": "s1", "name": "Ashmin", "confidence": 0.9}
            ).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

    monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout=None: FakeResp())
    monkeypatch.setattr(bridge, "VOICE_TOKEN", "t")
    sp = bridge._identify_speaker(b"WAVDATA")
    assert sp.get("name") == "Ashmin"


def test_stream_chat_includes_speaker_id(monkeypatch):
    import asyncio, aiohttp

    captured = {}

    def _post(url, kwargs):
        captured["body"] = kwargs.get("json", {})

    lines = [b'data: {"type":"done"}\n']
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeAiohttpSession(lines, _post))
    monkeypatch.setattr(bridge, "VOICE_TOKEN", "t")

    async def go():
        out = [c async for c in bridge._stream_chat("hi", persona=None, speaker_id="s1")]

    asyncio.run(go())
    assert captured["body"].get("speaker_id") == "s1"


def test_stream_chat_handles_envelope_events(monkeypatch):
    import asyncio, aiohttp

    lines = [
        b'data: {"type":"ack","stream_id":"s1","seq":1,"content":"Thinking..."}\n',
        b'data: {"type":"summary","stream_id":"s1","seq":2,"content":"Battery at 42%."}\n',
        b'data: {"type":"part_end","stream_id":"s1","seq":3,"part":"summary"}\n',
        b'data: {"type":"detail","stream_id":"s1","seq":4,"content":"Discharging at 5%/h."}\n',
        b'data: {"type":"part_end","stream_id":"s1","seq":5,"part":"detail"}\n',
        b'data: {"type":"complete","stream_id":"s1","seq":6,"content":"Battery at 42%. Discharging at 5%/h."}\n',
    ]

    monkeypatch.setattr(bridge, "VOICE_TOKEN", "t")
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeAiohttpSession(lines))

    async def go():
        out = [c async for c in bridge._stream_chat("battery?")]
        return out

    out = asyncio.run(go())
    text = "".join(out)
    assert "Battery at 42%" in text
    assert "Discharging at 5%/h" in text
    assert "Thinking..." not in text


def test_capture_tolerates_initial_silence(monkeypatch):
    """Verify that _capture_utterance does not cut off during initial silence before speech starts."""
    import asyncio

    # 10 silent frames (800ms) + 3 speech frames (240ms) + 12 silent frames (endpoint)
    frames_list = (
        [(np.zeros(1280, dtype=np.int16)).tobytes()] * 10
        + [(np.ones(1280, dtype=np.int16) * 300).tobytes()] * 3
        + [(np.zeros(1280, dtype=np.int16)).tobytes()] * 12
    )

    class FakeMic:
        available = True
        def open(self): pass
        def close(self): pass
        def __init__(self):
            self.it = iter(frames_list)
        def read_frame(self):
            return next(self.it, (np.zeros(1280, dtype=np.int16)).tobytes())

    class DelayedSpeechVAD:
        available = True
        threshold = 0.5
        silence_base_ms = 700

        def __init__(self):
            self.call_idx = 0

        def push_frame(self, f):
            self.call_idx += 1
            # Frames 11..13 are speech
            return 1.0 if 11 <= self.call_idx <= 13 else 0.0

        def is_speech(self, score):
            return score == 1.0

        def should_endpoint(self, text, silence_ms, base):
            return silence_ms >= base

    monkeypatch.setattr(bridge, "_transcribe_via_backend", lambda wav: "captured after pause")
    monkeypatch.setattr(bridge, "_recognize_pcm_fallback", lambda pcm: None)

    out = asyncio.run(bridge._capture_utterance(FakeMic(), DelayedSpeechVAD(), timeout=5.0))
    assert out == "captured after pause"


def test_session_broadcasts_transcripts(monkeypatch):
    """Verify that VoiceSession broadcasts transcript events for user and agent."""
    import asyncio

    broadcast_events = []

    async def _fake_broadcast(evt):
        broadcast_events.append(evt)

    monkeypatch.setattr(bridge, "_broadcast", _fake_broadcast)

    class _SilentMic:
        available = True
        def open(self): pass
        def close(self): pass
        def read_frame(self):
            return (np.zeros(1280, dtype=np.int16)).tobytes()

    class _DummyVAD:
        available = True
        threshold = 0.5
        silence_base_ms = 700
        def push_frame(self, f): return 0.0
        def is_speech(self, s): return False

    class _MockTTS:
        available = True
        is_playing = False
        def synth(self, t): return b"wav"
        def play(self, a): pass
        def flush(self): pass

    # First call returns user text, second call returns None to end session
    cap_count = {"n": 0}
    async def _cap(*a, **k):
        cap_count["n"] += 1
        if cap_count["n"] == 1:
            return "turn off lights", b""
        return None, b""

    monkeypatch.setattr(bridge, "_capture_utterance", _cap)

    async def _stream(*a, **k):
        yield "Acknowledged. "
        yield "Lights turned off."

    monkeypatch.setattr(bridge, "_stream_chat", _stream)

    sess = bridge.VoiceSession(_SilentMic(), _DummyVAD(), _MockTTS(), barge_in=False)
    asyncio.run(sess.run())

    transcripts = [e for e in broadcast_events if e.get("type") == "transcript"]
    roles = [t.get("role") for t in transcripts]
    texts = [t.get("text") for t in transcripts]

    assert "user" in roles
    assert "turn off lights" in texts
    assert "agent" in roles
    assert any("Acknowledged." in t for t in texts)

