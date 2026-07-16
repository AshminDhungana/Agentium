"""
Tests for POST /api/v1/genesis/set-country-name and the awaiting_name
genesis-status state.
"""
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.routes import websocket as ws
from backend.api.routes import genesis as genesis_route
from backend.core.auth import get_current_user


@pytest.fixture
def client(monkeypatch):
    app = FastAPI()
    app.include_router(genesis_route.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: {"user_id": 1, "role": "sovereign"}
    return TestClient(app)


def test_endpoint_accepts_name_when_awaiting(client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.initialization_service.submit_country_name",
        lambda name: name == "Veridia",
    )
    resp = client.post("/api/v1/genesis/set-country-name", json={"name": "Veridia"})
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


def test_endpoint_rejects_empty_name(client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.initialization_service.submit_country_name",
        lambda name: False,
    )
    resp = client.post("/api/v1/genesis/set-country-name", json={"name": "  "})
    assert resp.status_code == 422


def test_endpoint_reports_not_awaiting(client, monkeypatch):
    monkeypatch.setattr(
        "backend.services.initialization_service.submit_country_name",
        lambda name: False,
    )
    resp = client.post("/api/v1/genesis/set-country-name", json={"name": "Veridia"})
    assert resp.status_code == 200
    assert resp.json()["accepted"] is False


async def test_status_reports_awaiting_name(monkeypatch):
    fake_active = MagicMock()
    fake_active.awaiting_country_name = True
    fake_active.country_name_prompt = "Name your nation"
    fake_active.COUNTRY_NAME_TIMEOUT_SECONDS = 60
    with patch.object(ws, "get_fresh_db"), \
         patch("backend.api.routes.websocket.get_redis_client", lambda: AsyncMock(get=AsyncMock(return_value=None))), \
         patch("backend.services.initialization_service.get_active_genesis", return_value=fake_active):
        resp = await ws.genesis_status(current_user=MagicMock())
    assert resp["status"] == "awaiting_name"
    assert resp["prompt"] == "Name your nation"
    assert resp["timeout_seconds"] == 60
