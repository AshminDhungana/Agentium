# backend/tests/unit/test_websocket_revocation_broadcast.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.api.routes.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_emit_mcp_tool_revoked_broadcasts_correct_payload():
    """emit_mcp_tool_revoked should broadcast a properly structured event."""
    manager = ConnectionManager()
    manager.broadcast = AsyncMock()

    await manager.emit_mcp_tool_revoked(
        tool_id="tool-123",
        tool_name="Test Tool",
        reason="Security issue",
        revoked_by="admin-001"
    )

    manager.broadcast.assert_called_once()
    call_args = manager.broadcast.call_args[0][0]

    assert call_args["type"] == "mcp_tool_revoked"
    assert call_args["tool_id"] == "tool-123"
    assert call_args["tool_name"] == "Test Tool"
    assert call_args["reason"] == "Security issue"
    assert call_args["revoked_by"] == "admin-001"
    assert "timestamp" in call_args  # ISO8601 string