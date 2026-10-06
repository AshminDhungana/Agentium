"""
Unit tests for ConnectionManager Pub/Sub integration (Section 13.3 of TODO.md).
Tests that:
  - 13.3.1: ConnectionManager subscribes to Pub/Sub channels
  - 13.3.2: Cross-worker event distribution via Pub/Sub
  - 13.3.3: Per-user filtering via ws:user:{username} channels
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import json
import asyncio
from backend.api.routes.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_connectionmanager_ensure_pubsub_initializes_subscription():
    """13.3.2: ConnectionManager._ensure_pubsub initializes Pub/Sub and subscribes to ws:broadcast."""
    manager = ConnectionManager()
    manager._get_redis = AsyncMock()
    mock_redis = AsyncMock()
    mock_pubsub = AsyncMock()
    mock_redis.pubsub.return_value = mock_pubsub
    manager._get_redis.return_value = mock_redis

    await manager._ensure_pubsub()

    # Should create pubsub and subscribe to ws:broadcast
    mock_redis.pubsub.assert_called_once()
    mock_pubsub.subscribe.assert_called_once_with("ws:broadcast")
    assert manager._pubsub == mock_pubsub
    assert manager._pubsub_task is not None  # Task should be created


@pytest.mark.asyncio
async def test_connectionmanager_subscribe_user_adds_channel():
    """13.3.3: ConnectionManager.subscribe_user adds user channel to subscription set."""
    manager = ConnectionManager()
    manager._pubsub = AsyncMock()
    manager._user_channels = set()

    await manager.subscribe_user("alice")

    manager._pubsub.subscribe.assert_called_once_with("ws:user:alice")
    assert "ws:user:alice" in manager._user_channels


@pytest.mark.asyncio
async def test_connectionmanager_unsubscribe_user_removes_channel():
    """13.3.3: ConnectionManager.unsubscribe_user removes user channel from subscription set."""
    manager = ConnectionManager()
    manager._pubsub = AsyncMock()
    manager._user_channels = {"ws:user:alice"}

    await manager.unsubscribe_user("alice")

    manager._pubsub.unsubscribe.assert_called_once_with("ws:user:alice")
    assert "ws:user:alice" not in manager._user_channels


@pytest.mark.asyncio
async def test_connectionmanager_listen_pubsub_forwards_broadcast_to_local():
    """13.3.1/13.3.2: ConnectionManager._listen_pubsub forwards ws:broadcast messages to local connections."""
    manager = ConnectionManager()
    manager._broadcast_local = AsyncMock()

    # Mock pubsub listen to return one message then cancel
    async def mock_listen():
        yield {"type": "message", "channel": "ws:broadcast", "data": json.dumps({"type": "test_event"})}
        # Cancel the task after first message
        manager._pubsub_task.cancel()

    manager._pubsub = AsyncMock()
    manager._pubsub.listen = mock_listen

    # Start the listen task
    manager._pubsub_task = asyncio.create_task(manager._listen_pubsub())

    # Wait for task to complete
    try:
        await manager._pubsub_task
    except asyncio.CancelledError:
        pass

    # Should have forwarded to local connections
    manager._broadcast_local.assert_called_once_with({"type": "test_event"})


@pytest.mark.asyncio
async def test_connectionmanager_listen_pubsub_forwards_user_to_specific_connection():
    """13.3.3: ConnectionManager._listen_pubsub forwards ws:user:{username} to specific user connection."""
    manager = ConnectionManager()
    manager.send_personal_message = AsyncMock(return_value=True)

    # Mock pubsub listen to return one message then cancel
    async def mock_listen():
        yield {"type": "message", "channel": "ws:user:alice", "data": json.dumps({"type": "task_update", "task_id": "123"})}
        # Cancel the task after first message
        manager._pubsub_task.cancel()

    manager._pubsub = AsyncMock()
    manager._pubsub.listen = mock_listen

    # Start the listen task
    manager._pubsub_task = asyncio.create_task(manager._listen_pubsub())

    # Wait for task to complete
    try:
        await manager._pubsub_task
    except asyncio.CancelledError:
        pass

    # Should have sent personal message to alice
    manager.send_personal_message.assert_called_once()
    call_args = manager.send_personal_message.call_args
    assert call_args[0][0] == {"type": "task_update", "task_id": "123"}  # message
    assert call_args[0][1] == "alice"  # username