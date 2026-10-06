"""
Unit tests for MessageBus WebSocket integration (Section 13.3 of TODO.md).
Tests that:
  - 13.3.1: MessageBus publishes to correct WebSocket Pub/Sub channels
  - 13.3.3: Per-user filtering via ws:user:{username} channels
  - 13.3.4: Per-user history streams for replay
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
import json
from backend.services.message_bus import MessageBus


@pytest.mark.asyncio
async def test_publish_to_websocket_global():
    """13.3.1: MessageBus publishes to ws:broadcast when no usernames/room_ids specified."""
    message_bus = MessageBus()
    message_bus._redis = AsyncMock()

    event = {"type": "system_alert", "message": "test"}
    await message_bus.publish_to_websocket(event)

    message_bus._redis.publish.assert_called_once_with(
        "ws:broadcast",
        json.dumps(event)
    )


@pytest.mark.asyncio
async def test_publish_to_websocket_per_user():
    """13.3.1/13.3.3: MessageBus publishes to ws:user:{username} and appends to history when usernames provided."""
    message_bus = MessageBus()
    message_bus._redis = AsyncMock()
    message_bus._append_user_history = AsyncMock()

    event = {"type": "task_update", "task_id": "task-123"}
    await message_bus.publish_to_websocket(event, usernames=["alice", "bob"])

    # Should publish to both user channels
    assert message_bus._redis.publish.call_count == 2
    message_bus._redis.publish.assert_any_call("ws:user:alice", json.dumps(event))
    message_bus._redis.publish.assert_any_call("ws:user:bob", json.dumps(event))

    # Should append to history for both users
    assert message_bus._append_user_history.call_count == 2
    message_bus._append_user_history.assert_any_call("alice", event)
    message_bus._append_user_history.assert_any_call("bob", event)


@pytest.mark.asyncio
async def test_publish_to_websocket_no_persistence():
    """13.3.4: MessageBus does not append to history when persistent=False."""
    message_bus = MessageBus()
    message_bus._redis = AsyncMock()
    message_bus._append_user_history = AsyncMock()

    event = {"type": "task_update", "task_id": "task-123"}
    await message_bus.publish_to_websocket(event, usernames=["alice"], persistent=False)

    message_bus._redis.publish.assert_called_once_with("ws:user:alice", json.dumps(event))
    message_bus._append_user_history.assert_not_called()