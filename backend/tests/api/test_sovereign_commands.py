# tests/api/test_sovereign_commands.py
# Fix 2 regression (TODO 12.4.3): close the command_log phantom contract.
# 1. GET /api/v1/sovereign/commands returns seeded sovereign AuditLog entries.
# 2. Sovereign container actions emit a command_log WebSocket push via
#    notify_sovereign() — even when the action itself fails (audit is written
#    before the Docker call, so the push must fire there too).
#
# Auth note: the sovereign router uses backend/api/middleware/auth.py's
# get_current_user, which resolves the JWT "sub" claim against
# User.username. Production logins set sub=user.username, so the token
# here must too — sub=<uuid id> (the conftest auth_client shape) 401s
# with USER_NOT_FOUND.
from datetime import datetime

import pytest
from httpx import AsyncClient, ASGITransport

from backend.main import app
from backend.models.database import get_db
from backend.core.auth import create_access_token
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.user import User

import pytest_asyncio


@pytest_asyncio.fixture(scope="function")
async def sovereign_client(db_session):
    """AsyncClient whose JWT matches the production login shape (sub=username).

    Same override pattern as the conftest auth_client fixture, but with a
    sub the middleware-auth username lookup can actually resolve.
    """
    sovereign = db_session.query(User).filter_by(username="admin").first()
    if not sovereign:
        sovereign = User(
            username="admin",
            email="admin@agentium.local",
            hashed_password=User.hash_password("admin"),
            is_admin=True,
            is_active=True,
            is_pending=False,
        )
        db_session.add(sovereign)
        db_session.commit()
        db_session.refresh(sovereign)

    token = create_access_token(data={
        "sub": "admin",
        "username": "admin",
        "user_id": sovereign.id,
        "is_admin": True,
        "is_active": True,
    })

    async def get_test_db():
        yield db_session

    app.dependency_overrides[get_db] = get_test_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            client.headers.update({"Authorization": f"Bearer {token}"})
            yield client
    finally:
        app.dependency_overrides.clear()


async def test_commands_returns_sovereign_entries(db_session, sovereign_client):
    audit = AuditLog(
        level=AuditLevel.INFO,
        category=AuditCategory.GOVERNANCE,
        actor_type="sovereign",
        actor_id="admin",
        action="sovereign_command",
        target_type="host_system",
        target_id="root",
        description="Sovereign executed: test",
        is_active=True,
        created_at=datetime.utcnow(),
    )
    db_session.add(audit)
    db_session.commit()

    resp = await sovereign_client.get("/api/v1/sovereign/commands")
    assert resp.status_code == 200
    items = resp.json()
    assert any(i["action"] == "sovereign_command" for i in items)
    # Items are AuditLog.to_dict() shapes — the frontend mapper consumes these keys.
    assert all(
        "actor" in i and "timestamp" in i and "result" in i and "action" in i
        for i in items
    )


async def test_container_action_emits_command_log_push(db_session, sovereign_client, monkeypatch):
    pushes = []

    async def fake_notify(message):
        pushes.append(message)

    monkeypatch.setattr("backend.api.sovereign.notify_sovereign", fake_notify)

    class FakeHead:
        def manage_container(self, action, name):
            return {"success": False, "error": "container not found"}

    monkeypatch.setattr("backend.api.sovereign._get_head_service", lambda: FakeHead())

    resp = await sovereign_client.post(
        "/api/v1/sovereign/containers/nonexistent-id/restart", json={}
    )
    # The action failed (400) — but the audit + push happened before execution.
    assert resp.status_code == 400
    assert len(pushes) == 1
    assert pushes[0]["type"] == "command_log"
    assert pushes[0]["payload"]["action"] == "container_restart"
    assert pushes[0]["payload"]["actor"]["id"] == "admin"


async def test_command_endpoint_emits_command_log_push(db_session, sovereign_client, monkeypatch):
    pushes = []

    async def fake_notify(message):
        pushes.append(message)

    monkeypatch.setattr("backend.api.sovereign.notify_sovereign", fake_notify)

    class FakeHead:
        def execute_command(self, command, cwd=None):
            return {"success": True, "output": "ok"}

        def read_file(self, path):
            return {"success": True, "content": ""}

        def write_file(self, path, content):
            return {"success": True}

    monkeypatch.setattr("backend.api.sovereign._get_head_service", lambda: FakeHead())

    resp = await sovereign_client.post(
        "/api/v1/sovereign/command",
        json={"command": "read_file", "params": {"path": "/tmp/x"}, "target": "head_of_council"},
    )
    assert resp.status_code == 200
    assert len(pushes) == 1
    assert pushes[0]["type"] == "command_log"
    assert pushes[0]["payload"]["action"] == "sovereign_command"
