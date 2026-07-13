import asyncio
from unittest.mock import patch, MagicMock

import pytest

from backend.core.exceptions import ServerSTTUnavailable
from backend.services.audio_service import AudioService
from backend.services.whisper_cpp_service import LocalSTTError


def _whisper_svc(available=True, text="local transcript"):
    svc = MagicMock()
    svc.is_available.return_value = available
    async def _transcribe(*args, **kwargs):
        return text
    svc.transcribe.side_effect = _transcribe
    return svc


@pytest.fixture
def svc():
    return AudioService()


def test_whisper_primary_used_when_available(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=True),
    ), patch.object(AudioService, "_get_openai_api_key", return_value=None):
        result = asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))
    assert result == "local transcript"


def test_whisper_failure_falls_back_to_openai(svc):
    w = _whisper_svc(available=True)
    w.transcribe.side_effect = LocalSTTError("crash")
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service", return_value=w
    ), patch.object(
        AudioService, "_get_openai_api_key", return_value="sk-test"
    ), patch.object(
        AudioService, "_transcribe_openai", return_value="openai transcript"
    ):
        result = asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))
    assert result == "openai transcript"


def test_openai_used_when_whisper_unavailable(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=False),
    ), patch.object(
        AudioService, "_get_openai_api_key", return_value="sk-test"
    ), patch.object(
        AudioService, "_transcribe_openai", return_value="openai transcript"
    ):
        result = asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))
    assert result == "openai transcript"


def test_no_engine_raises_server_stt_unavailable(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=False),
    ), patch.object(AudioService, "_get_openai_api_key", return_value=None):
        with pytest.raises(ServerSTTUnavailable):
            asyncio.run(svc.transcribe(db=MagicMock(), user_id="u", audio_bytes=b"x"))


def test_is_available_true_when_whisper_present(svc):
    with patch(
        "backend.services.audio_service.get_whisper_cpp_service",
        return_value=_whisper_svc(available=True),
    ):
        assert svc.is_available(db=MagicMock(), user_id="u") is True