import hashlib
import math
import wave
import io
import struct

import pytest

from backend.services.audio_service import SpeakerIdentifier, SpeakerIDConfig
from backend.api.routes import audio as audio_routes


def _make_wav(duration_s=1.0, framerate=16000, amp=0):
    buf = io.BytesIO()
    n = int(duration_s * framerate)
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(framerate)
        wf.writeframes(struct.pack("<%dh" % n, *([amp] * n)))
    return buf.getvalue()


class FakeEncoder:
    def __init__(self, dim=8):
        self.dim = dim

    def embed(self, audio_bytes: bytes):
        h = hashlib.sha256(audio_bytes).digest()
        vec = [((h[i % len(h)] / 255.0) - 0.5) for i in range(self.dim)]
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]


def _make_identifier(require_liveness=False, enabled=True):
    cfg = SpeakerIDConfig(
        enabled=enabled, model_source="x", threshold=0.70,
        min_duration_s=1.0, cache_dir="/tmp", require_liveness=require_liveness,
    )
    return SpeakerIdentifier(classifier=FakeEncoder(), config=cfg)


@pytest.fixture
def fake_speaker_id(monkeypatch):
    identifier = _make_identifier()
    monkeypatch.setattr(audio_routes, "get_speaker_identifier", lambda: identifier)
    return identifier


@pytest.fixture
def fake_transcribe(monkeypatch):
    async def _t(db, user_id, audio_bytes, language=None, filename="audio.wav"):
        return "transcribed text"
    monkeypatch.setattr(
        "backend.services.audio_service.AudioService.transcribe", _t
    )


def test_register_then_identify_then_list(client, auth_headers, fake_speaker_id, fake_transcribe):
    clip = _make_wav(1.0, amp=5)

    r = client.post(
        "/api/v1/audio/speakers/register",
        data={"name": "Alice"},
        files={"audio": ("a.wav", clip, "audio/wav")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    spk = r.json()
    assert spk["name"] == "Alice"
    assert spk["has_embedding"] is True
    speaker_id = spk["id"]

    r = client.post(
        "/api/v1/audio/transcribe",
        data={"language": "en"},
        files={"audio": ("a.wav", clip, "audio/wav")},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["text"] == "transcribed text"
    assert body["speaker_id"] == speaker_id
    assert body["speaker_name"] == "Alice"

    r = client.get("/api/v1/audio/speakers", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["speakers"]) == 1


def test_soft_delete_excludes_from_list(client, auth_headers, fake_speaker_id, fake_transcribe):
    clip = _make_wav(1.0, amp=2)
    spk = client.post(
        "/api/v1/audio/speakers/register",
        data={"name": "Bob"},
        files={"audio": ("b.wav", clip, "audio/wav")},
        headers=auth_headers,
    ).json()

    r = client.delete(f"/api/v1/audio/speakers/{spk['id']}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "success"

    r = client.get("/api/v1/audio/speakers", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["speakers"] == []


def test_status_reports_speaker_id(client, auth_headers, fake_speaker_id):
    r = client.get("/api/v1/audio/status", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["speaker_id_enabled"] is True
    assert body["speaker_id_available"] is True


def test_register_rejected_when_disabled(client, auth_headers, monkeypatch):
    identifier = _make_identifier(enabled=False)
    monkeypatch.setattr(audio_routes, "get_speaker_identifier", lambda: identifier)

    r = client.post(
        "/api/v1/audio/speakers/register",
        data={"name": "Carol"},
        files={"audio": ("c.wav", _make_wav(1.0, amp=1), "audio/wav")},
        headers=auth_headers,
    )
    assert r.status_code == 400


def test_liveness_rejects_spoof_on_register(client, auth_headers, monkeypatch, fake_transcribe):
    identifier = _make_identifier(require_liveness=True)
    identifier._liveness_check = lambda audio: False
    monkeypatch.setattr(audio_routes, "get_speaker_identifier", lambda: identifier)

    r = client.post(
        "/api/v1/audio/speakers/register",
        data={"name": "Dave"},
        files={"audio": ("d.wav", _make_wav(1.0, amp=1), "audio/wav")},
        headers=auth_headers,
    )
    assert r.status_code == 400
