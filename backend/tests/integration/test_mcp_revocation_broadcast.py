# backend/tests/integration/test_mcp_revocation_broadcast.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient


@pytest.mark.integration
def test_revoke_endpoint_broadcasts_websocket_event(client, db_session, auth_headers):
    """POST /revoke should emit mcp_tool_revoked WebSocket event after successful revocation."""
    # 1. Create and approve a tool
    r = client.post("/api/v1/mcp-tools", json={
        "name": "Test Tool for Revoke",
        "description": "Test tool for revocation",
        "server_url": "http://localhost:9999/test",
        "tier": "pre_approved",
        "capabilities": [],
    }, headers=auth_headers)
    assert r.status_code == 201
    tool_id = r.json()["id"]

    r = client.post(f"/api/v1/mcp-tools/{tool_id}/approve", json={"approved_by": "admin"}, headers=auth_headers)
    assert r.status_code == 200

    # 2. Mock ConnectionManager.broadcast to capture call
    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager.emit_mcp_tool_revoked = AsyncMock()

        # 3. Revoke the tool
        r = client.post(f"/api/v1/mcp-tools/{tool_id}/revoke", json={
            "revoked_by": "admin",
            "reason": "Test revocation"
        }, headers=auth_headers)
        assert r.status_code == 200

        # 4. Verify broadcast was called with correct args
        mock_manager.emit_mcp_tool_revoked.assert_called_once()
        call_kwargs = mock_manager.emit_mcp_tool_revoked.call_args.kwargs

        assert call_kwargs["tool_id"] == tool_id
        assert call_kwargs["tool_name"] == "Test Tool for Revoke"
        assert call_kwargs["reason"] == "Test revocation"
        assert call_kwargs["revoked_by"] == "admin"