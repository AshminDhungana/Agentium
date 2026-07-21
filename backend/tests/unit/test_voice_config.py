import sys
import os
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import voice as voice_route
from backend.core.auth import get_current_active_user
from backend.models.database import get_db


class _FakeDB:
    pass


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    app = FastAPI()
    app.include_router(voice_route.router, prefix="/api/v1")

    def _user():
        # get_current_active_user returns a normalized JWT dict in production.
        return {"sub": "user-123", "is_admin": False, "is_active": True}

    def _db():
        return _FakeDB()

    app.dependency_overrides[get_current_active_user] = _user
    app.dependency_overrides[get_db] = _db
    return TestClient(app)


def test_get_config_returns_defaults(client):
    resp = client.get("/api/v1/voice/config")
    assert resp.status_code == 200
    body = resp.json()
    assert body["requireWakeWord"] is True
    assert body["ttsVoice"] == "af_bella"
    assert body["proactiveEnabled"] is False


def test_put_config_persists_and_get_returns_it(client, tmp_path):
    resp = client.put(
        "/api/v1/voice/config",
        json={"requireWakeWord": False, "ttsVoice": "am_adam", "proactiveEnabled": True},
    )
    assert resp.status_code == 200
    saved = resp.json()
    assert saved["requireWakeWord"] is False
    assert saved["ttsVoice"] == "am_adam"
    assert saved["proactiveEnabled"] is True

    # File persisted under <home>/.agentium/voice_config/user-123.json
    cfg_file = tmp_path / ".agentium" / "voice_config" / "user-123.json"
    assert cfg_file.is_file()
    assert json.loads(cfg_file.read_text())["ttsVoice"] == "am_adam"

    # Subsequent GET returns the persisted values
    resp2 = client.get("/api/v1/voice/config")
    assert resp2.json()["ttsVoice"] == "am_adam"


def test_put_config_partial_merge(client):
    client.put("/api/v1/voice/config", json={"ttsVoice": "bf_emma"})
    resp = client.put("/api/v1/voice/config", json={"proactiveEnabled": True})
    assert resp.status_code == 200
    body = resp.json()
    # Unset fields keep their previous / default values
    assert body["ttsVoice"] == "bf_emma"
    assert body["proactiveEnabled"] is True
    assert body["requireWakeWord"] is True
