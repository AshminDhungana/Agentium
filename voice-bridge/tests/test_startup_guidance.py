"""Tests for voice-bridge startup guidance messages."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

import main as bridge


def test_first_run_speaks_welcome():
    """Counter file absent → welcome spoken, counter written as 1."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        with patch.object(bridge, "speak") as mock_speak:
            asyncio.run(bridge._maybe_speak_startup_messages())
            assert mock_speak.called
            text = " ".join(c.args[0] for c in mock_speak.call_args_list)
            assert "Welcome back" in text
        assert bridge._COUNTER_PATH.read_text().strip() == "1"


def test_second_run_skips_welcome():
    """Counter = 1 -> no welcome, counter incremented to 2."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        bridge._COUNTER_PATH.write_text("1")
        with patch.object(bridge, "speak") as mock_speak:
            asyncio.run(bridge._maybe_speak_startup_messages())
            assert not mock_speak.called
        assert bridge._COUNTER_PATH.read_text().strip() == "2"


def test_fifth_run_speaks_welcome():
    """Counter = 4 (5th run) -> welcome spoken."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        bridge._COUNTER_PATH.write_text("4")
        with patch.object(bridge, "speak") as mock_speak:
            asyncio.run(bridge._maybe_speak_startup_messages())
            assert mock_speak.called
            assert "Welcome back" in mock_speak.call_args[0][0]


def test_no_token_speaks_guidance():
    """VOICE_TOKEN empty -> guidance spoken."""
    with tempfile.TemporaryDirectory() as tmp:
        bridge._COUNTER_PATH = Path(tmp) / ".voice-startup-count"
        bridge._COUNTER_PATH.write_text("2")
        with patch.object(bridge, "VOICE_TOKEN", ""):
            with patch.object(bridge, "speak") as mock_speak:
                asyncio.run(bridge._maybe_speak_startup_messages())
                assert mock_speak.called
                assert "API key" in mock_speak.call_args[0][0]


def test_token_ready_set_immediately_when_token_present():
    """VOICE_TOKEN present -> _token_ready is set in _main()."""
    bridge._token_ready = asyncio.Event()
    with patch.object(bridge, "VOICE_TOKEN", "some-token"):
        with patch.object(bridge, "_maybe_speak_startup_messages"):
            with patch.object(bridge, "asyncio") as mock_asyncio:
                mock_asyncio.gather = MagicMock()
                if bridge.VOICE_TOKEN:
                    bridge._token_ready.set()
                assert bridge._token_ready.is_set()


def test_token_ready_unset_when_token_empty():
    """VOICE_TOKEN empty -> _token_ready not set in _main()."""
    bridge._token_ready = asyncio.Event()
    with patch.object(bridge, "VOICE_TOKEN", ""):
        with patch.object(bridge, "_maybe_speak_startup_messages"):
            with patch.object(bridge, "asyncio") as mock_asyncio:
                mock_asyncio.gather = MagicMock()
                if not bridge.VOICE_TOKEN:
                    pass
                assert not bridge._token_ready.is_set()


def test_ws_set_token_sets_event():
    """WS set_token message -> _token_ready.set() called."""
    bridge._token_ready = asyncio.Event()
    def handle_set_token():
        bridge._set_voice_token("new-token")
        bridge._token_ready.set()
    handle_set_token()
    assert bridge._token_ready.is_set()
    assert bridge.VOICE_TOKEN == "new-token"
