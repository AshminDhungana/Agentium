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
from backend.models.schemas.messages import AgentMessage


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


@pytest.mark.asyncio
async def test_broadcast_from_head_also_publishes_to_websocket():
    """13.3.1: MessageBus.broadcast_from_head calls publish_to_websocket for global events."""
    message_bus = MessageBus()
    message_bus.publish = AsyncMock()
    message_bus.publish_to_websocket = AsyncMock()
    # Mock db to avoid actual database queries
    from unittest.mock import MagicMock
    message_bus.db = MagicMock()
    message_bus.db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

    # Create a test message
    message = AgentMessage(
        message_id="test-123",
        sender_id="00001",
        recipient_id="broadcast",
        message_type="notification",
        content="Test alert",
        route_direction="broadcast"
    )

    await message_bus.broadcast_from_head(message)

    # Should call publish_to_websocket for global broadcast
    message_bus.publish_to_websocket.assert_called_once()
    call_args = message_bus.publish_to_websocket.call_args
    # call_args is a tuple of (args, kwargs)
    if call_args[0]:  # positional args
        event = call_args[0][0]
    else:  # keyword args
        event = call_args[1].get('event')
    assert event["type"] == "notification"
    assert event["content"] == "Test alert"