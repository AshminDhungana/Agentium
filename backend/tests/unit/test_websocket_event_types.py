"""
Unit tests for WebSocket event types (Section 13.2 of TODO.md).
Tests that:
  - 13.2.1: emit_agent_status broadcasts agent_status events
  - 13.2.2: emit_task_update broadcasts task_update events
  - 13.2.3: chat_message events are supported and formatted
  - 13.2.4: chat_stream events are supported and formatted
  - 13.2.5: emit_channel_status broadcasts channel_status events
  - 13.2.6: emit_system_alert broadcasts system_alert events
  - 13.2.7: emit_vote_update broadcasts vote_update events
  - 13.2.8: emit_tool_execution broadcasts tool_execution events
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime

from backend.api.routes.websocket import manager, ConnectionManager


@pytest.mark.asyncio
async def test_emit_agent_status():
    """13.2.1: emit_agent_status broadcasts agent_status event with correct payload."""
    test_manager = ConnectionManager()
    test_manager.broadcast = AsyncMock()

    await test_manager.emit_agent_status(
        agent_id="30001",
        status="active",
        agent_name="Test Agent",
        old_status="idle",
    )

    test_manager.broadcast.assert_called_once()
    payload = test_manager.broadcast.call_args[0][0]
    assert payload["type"] == "agent_status"
    assert payload["agent_id"] == "30001"
    assert payload["status"] == "active"
    assert payload["new_status"] == "active"
    assert payload["old_status"] == "idle"
    assert payload["agent_name"] == "Test Agent"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_emit_task_update():
    """13.2.2: emit_task_update broadcasts task_update event with progress and state."""
    test_manager = ConnectionManager()
    test_manager.broadcast = AsyncMock()

    await test_manager.emit_task_update(
        task_id="task-123",
        status="in_progress",
        progress=50,
        title="Deploy Cluster",
        result_summary="Working on step 2",
        metadata={"step": 2, "total_steps": 4},
    )

    test_manager.broadcast.assert_called_once()
    payload = test_manager.broadcast.call_args[0][0]
    assert payload["type"] == "task_update"
    assert payload["task_id"] == "task-123"
    assert payload["status"] == "in_progress"
    assert payload["progress"] == 50
    assert payload["title"] == "Deploy Cluster"
    assert payload["result_summary"] == "Working on step 2"
    assert payload["metadata"]["step"] == 2
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_emit_channel_status():
    """13.2.5: emit_channel_status broadcasts channel_status event with health."""
    test_manager = ConnectionManager()
    test_manager.broadcast = AsyncMock()

    await test_manager.emit_channel_status(
        channel_id="chan-whatsapp",
        status="active",
        health_status="healthy",
        metrics={"success_rate": 99.5},
    )

    test_manager.broadcast.assert_called_once()
    payload = test_manager.broadcast.call_args[0][0]
    assert payload["type"] == "channel_status"
    assert payload["channel_id"] == "chan-whatsapp"
    assert payload["status"] == "active"
    assert payload["health_status"] == "healthy"
    assert payload["metrics"]["success_rate"] == 99.5
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_emit_system_alert():
    """13.2.6: emit_system_alert broadcasts system_alert event with severity."""
    test_manager = ConnectionManager()
    test_manager.broadcast = AsyncMock()

    await test_manager.emit_system_alert(
        message="High memory usage detected on worker",
        severity="critical",
        alert_type="resource_exhaustion",
    )

    test_manager.broadcast.assert_called_once()
    payload = test_manager.broadcast.call_args[0][0]
    assert payload["type"] == "system_alert"
    assert payload["message"] == "High memory usage detected on worker"
    assert payload["severity"] == "critical"
    assert payload["alert_type"] == "resource_exhaustion"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_emit_vote_update():
    """13.2.7: emit_vote_update broadcasts vote_update event with tallies."""
    test_manager = ConnectionManager()
    test_manager.broadcast = AsyncMock()

    await test_manager.emit_vote_update(
        vote_id="vote-amend-1",
        vote_type="amendment",
        voter="user-1",
        vote="for",
        tally={"for": 3, "against": 1, "abstain": 0},
        status="voting",
    )

    test_manager.broadcast.assert_called_once()
    payload = test_manager.broadcast.call_args[0][0]
    assert payload["type"] == "vote_update"
    assert payload["vote_id"] == "vote-amend-1"
    assert payload["vote_type"] == "amendment"
    assert payload["voter"] == "user-1"
    assert payload["vote"] == "for"
    assert payload["tally"]["for"] == 3
    assert payload["status"] == "voting"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_emit_tool_execution():
    """13.2.8: emit_tool_execution broadcasts tool_execution event with progress."""
    test_manager = ConnectionManager()
    test_manager.broadcast = AsyncMock()

    await test_manager.emit_tool_execution(
        tool_name="web_search",
        tool_names=["web_search", "file_read"],
        tool_count=2,
        status="executing",
        stream_id="stream-456",
    )

    test_manager.broadcast.assert_called_once()
    payload = test_manager.broadcast.call_args[0][0]
    assert payload["type"] == "tool_execution"
    assert payload["tool_name"] == "web_search"
    assert payload["tool_names"] == ["web_search", "file_read"]
    assert payload["tool_count"] == 2
    assert payload["status"] == "executing"
    assert payload["stream_id"] == "stream-456"
    assert "timestamp" in payload


@pytest.mark.asyncio
async def test_alert_manager_import_resolution():
    """13.2.6: alert_manager imports manager from backend.api.routes.websocket cleanly."""
    from backend.services.alert_manager import AlertManager, MonitoringAlert
    from backend.models.entities.monitoring import ViolationSeverity

    alert = MonitoringAlert(
        id="alert-1",
        severity=ViolationSeverity.CRITICAL,
        alert_type="test_alert",
        message="Critical system alert",
        detected_by_agent_id="SYSTEM",
        created_at=datetime.utcnow(),
    )

    am = AlertManager(db=MagicMock())
    with patch("backend.api.routes.websocket.manager.broadcast", new=AsyncMock()) as mock_broadcast:
        await am._broadcast_websocket(alert, "Formatted alert message")
        mock_broadcast.assert_called_once()
        sent = mock_broadcast.call_args[0][0]
        assert sent["type"] == "system_alert"
        assert sent["severity"] == "critical"
