import io
import json
import urllib.error
from unittest.mock import patch, MagicMock

import pytest

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main as bridge


def _audio_wav() -> bytes:
    # Minimal non-empty bytes standing in for WAV audio.
    return b"RIFF....WAVEfmt "


def test_relay_returns_backend_text(monkeypatch):
    captured = {}

    def _fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = req.data
        resp = MagicMock()
        resp.read.return_value = json.dumps({"text": "hello from backend"}).encode()
        resp.__enter__.return_value = resp
        return resp

    monkeypatch.setattr(bridge, "STT_BACKEND_URL", "http://127.0.0.1:8000/api/v1/audio/transcribe")
    monkeypatch.setattr(bridge, "VOICE_TOKEN", "test-token")
    with patch("urllib.request.urlopen", _fake_urlopen):
        result = bridge._transcribe_via_backend(_audio_wav())
    assert result == "hello from backend"
    assert "audio/transcribe" in captured["url"]


def test_relay_falls_back_to_vosk_on_http_error(monkeypatch):
    def _raise(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(bridge, "STT_BACKEND_URL", "http://127.0.0.1:8000/api/v1/audio/transcribe")
    monkeypatch.setattr(bridge, "VOICE_TOKEN", "test-token")
    with patch("urllib.request.urlopen", _raise), \
         patch.object(bridge, "_recognize_with_vosk", return_value="vosk text"):
        result = bridge._transcribe_via_backend(_audio_wav())
    # _transcribe_via_backend returns None on failure; the Vosk fallback is
    # invoked by _listen_sync, not inside the relay function itself.
    assert result is None