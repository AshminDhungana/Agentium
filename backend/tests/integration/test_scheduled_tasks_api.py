# backend/tests/integration/test_scheduled_tasks_api.py
"""Integration tests for the /api/v1/scheduled-tasks CRUD router."""

import pytest
import pytest_asyncio


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduled_task_crud_round_trip(client, auth_headers):
    # CREATE a one-time task due in the past so it would be dispatched immediately.
    body = {
        "name": "OneShot API",
        "run_once": True,
        "run_at": "2020-01-01T00:00:00",
        "task_payload": {"action_type": "execution", "params": {"via": "api"}},
    }
    r = await client.post("/api/v1/scheduled-tasks", json=body, headers=auth_headers)
    assert r.status_code == 201, r.text
    created = r.json()
    sid = created["agentium_id"]
    assert created["status"] == "active"
    assert created["run_once"] is True

    # READ (detail)
    r = await client.get(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "OneShot API"

    # LIST includes it
    r = await client.get("/api/v1/scheduled-tasks?status=active", headers=auth_headers)
    assert r.status_code == 200
    assert any(item["agentium_id"] == sid for item in r.json())

    # UPDATE -> pause
    r = await client.patch(f"/api/v1/scheduled-tasks/{sid}", json={"paused": True}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "paused"

    # DELETE
    r = await client.delete(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 204
    r = await client.get(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_scheduled_task_create_rejects_mutual_exclusion(client, auth_headers):
    body = {
        "name": "Both",
        "cron_expression": "0 9 * * *",
        "run_once": True,
        "run_at": "2026-09-20T09:00:00",
    }
    r = await client.post("/api/v1/scheduled-tasks", json=body, headers=auth_headers)
    assert r.status_code == 400