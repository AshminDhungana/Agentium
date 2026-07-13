import asyncio
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.core.error_responses import register_error_handlers
from backend.core.exceptions import ServerSTTUnavailable
from backend.services.audio_service import AudioService


@pytest.fixture
def client():
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/api/v1/audio/transcribe")
    async def _transcribe():
        # Mirror audio.py: AudioService.transcribe raises ServerSTTUnavailable
        # when no server engine is available; the route must re-raise it
        # (NOT wrap it in a 500 InternalServerError).
        raise ServerSTTUnavailable(
            "No server STT engine available",
            code="STT_UNAVAILABLE",
            detail={"fallback": "browser"},
        )

    return TestClient(app)


def test_server_stt_unavailable_envelope(client):
    resp = client.post("/api/v1/audio/transcribe")
    assert resp.status_code == 503
    body = resp.json()
    assert body["code"] == "STT_UNAVAILABLE"
    assert body["detail"] == {"fallback": "browser"}


def test_check_voice_available_reports_whisper_without_key():
    from backend.api.routes import voice as voice_route

    with pytest.MonkeyPatch().context() as mp:
        # check_voice_available imports get_whisper_cpp_service *inside* the
        # function, so patch the name on its source module.
        mp.setattr(
            "backend.services.whisper_cpp_service.get_whisper_cpp_service",
            lambda: _fake_whisper(available=True),
        )
        status = voice_route.check_voice_available(db=_FakeDB(), user_id="u")
    assert status["available"] is True
    assert status["provider"] == "whisper_cpp"


class _FakeDB:
    pass


def _fake_whisper(available: bool):
    class _S:
        def is_available(self):
            return available
    return _S()