# backend/tests/integration/test_scheduled_tasks_api.py
"""Integration tests for the /api/v1/scheduled-tasks CRUD router."""

import pytest


@pytest.mark.integration
def test_scheduled_task_crud_round_trip(client, auth_headers):
    # CREATE a one-time task due in the past so it would be dispatched immediately.
    body = {
        "name": "OneShot API",
        "run_once": True,
        "run_at": "2020-01-01T00:00:00",
        "task_payload": {"action_type": "execution", "params": {"via": "api"}},
    }
    r = client.post("/api/v1/scheduled-tasks", json=body, headers=auth_headers)
    assert r.status_code == 201, r.text
    created = r.json()
    sid = created["agentium_id"]
    assert created["status"] == "active"
    assert created["run_once"] is True

    # READ (detail)
    r = client.get(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["name"] == "OneShot API"

    # LIST includes it
    r = client.get("/api/v1/scheduled-tasks?status=active", headers=auth_headers)
    assert r.status_code == 200
    assert any(item["agentium_id"] == sid for item in r.json())

    # UPDATE -> pause
    r = client.patch(f"/api/v1/scheduled-tasks/{sid}", json={"paused": True}, headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["status"] == "paused"

    # DELETE
    r = client.delete(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 204
    r = client.get(f"/api/v1/scheduled-tasks/{sid}", headers=auth_headers)
    assert r.status_code == 404


@pytest.mark.integration
def test_scheduled_task_create_rejects_mutual_exclusion(client, auth_headers):
    body = {
        "name": "Both",
        "cron_expression": "0 9 * * *",
        "run_once": True,
        "run_at": "2026-09-20T09:00:00",
    }
    r = client.post("/api/v1/scheduled-tasks", json=body, headers=auth_headers)
    assert r.status_code == 400