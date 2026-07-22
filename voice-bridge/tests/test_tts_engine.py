"""Tests for multi-provider TTS engine (Kokoro + OpenAI)."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch
import tts_engine as te


def test_synth_uses_kokoro_when_available():
    """Test that synth returns WAV bytes when Kokoro is available."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._kokoro = MagicMock()
    eng._kokoro.available = True
    eng._kokoro.synthesize.return_value = b"RIFF\x00\x00\x00\x00WAVE"
    eng._openai = MagicMock()
    eng._openai.available = False
    eng.available = True
    eng._queue = te.PlaybackQueue()
    eng.voice = "am_adam"
    eng.provider = "kokoro"

    audio = eng.synth("hello")
    assert isinstance(audio, (bytes, bytearray)) and len(audio) > 0
    eng._kokoro.synthesize.assert_called_once_with("hello", "am_adam")


def test_synth_falls_back_to_kokoro_when_openai_unavailable():
    """Test fallback to Kokoro when OpenAI provider is unavailable."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng.provider = "openai"
    eng.voice = "alloy"
    eng._kokoro = MagicMock()
    eng._kokoro.available = True
    eng._kokoro.synthesize.return_value = b"RIFF...wav_data"
    eng._openai = MagicMock()
    eng._openai.available = False
    eng.available = True
    eng._queue = te.PlaybackQueue()

    audio = eng.synth("test")
    assert audio == b"RIFF...wav_data"
    eng._kokoro.synthesize.assert_called_once()


def test_synth_uses_openai_when_available():
    """Test that synth uses OpenAI when it is the selected provider."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng.provider = "openai"
    eng.voice = "alloy"
    eng._openai = MagicMock()
    eng._openai.available = True
    eng._openai.synthesize.return_value = b"RIFF\x00\x00\x00\x00WAVE"
    eng._kokoro = MagicMock()
    eng._kokoro.available = True
    eng.available = True
    eng._queue = te.PlaybackQueue()

    audio = eng.synth("hello")
    assert len(audio) > 0
    eng._openai.synthesize.assert_called_once_with("hello", "alloy")


def test_flush_stops_playback():
    """Test that flush aborts the playback queue."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._queue = te.PlaybackQueue()
    eng.flush()
    assert eng._queue.aborted is True


def test_return_empty_when_no_providers():
    """Test synth returns empty bytes when no provider is available."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._kokoro = None
    eng._openai = None
    eng.available = False
    eng._queue = te.PlaybackQueue()
    assert eng.synth("hi") == b""


def test_detect_provider_kokoro_voices():
    """Test provider detection identifies Kokoro voices."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    assert eng._detect_provider("am_adam") == "kokoro"
    assert eng._detect_provider("af_bella") == "kokoro"
    assert eng._detect_provider("bf_emma") == "kokoro"
    assert eng._detect_provider("bm_george") == "kokoro"


def test_detect_provider_openai_voices():
    """Test provider detection identifies OpenAI voices."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    assert eng._detect_provider("alloy") == "openai"
    assert eng._detect_provider("nova") == "openai"
    assert eng._detect_provider("echo") == "openai"
    assert eng._detect_provider("onyx") == "openai"


def test_detect_provider_with_prefix():
    """Test provider detection with explicit prefix."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    assert eng._detect_provider("kokoro:am_adam") == "kokoro"
    assert eng._detect_provider("openai:alloy") == "openai"


def test_set_voice_detects_provider():
    """Test set_voice auto-detects provider from voice ID."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._queue = te.PlaybackQueue()
    eng.set_voice("alloy")
    assert eng.voice == "alloy"
    assert eng.provider == "openai"


def test_set_voice_with_explicit_provider():
    """Test set_voice respects explicit provider override."""
    eng = te.TTSEngine.__new__(te.TTSEngine)
    eng._queue = te.PlaybackQueue()
    eng.set_voice("am_adam", "kokoro")
    assert eng.voice == "am_adam"
    assert eng.provider == "kokoro"
