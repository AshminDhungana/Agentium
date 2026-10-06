"""
Integration tests for cross-worker Message Bus functionality (Section 13.3 of TODO.md).
Tests that:
  - 13.3.1: MessageBus publishes to correct WebSocket clients via Pub/Sub
  - 13.3.2: Cross-worker event distribution via Redis Pub/Sub
  - 13.3.3: Per-user filtering works - User A receives only their events
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
import asyncio
from backend.services.message_bus import MessageBus
from backend.models.schemas.messages import AgentMessage
from backend.api.routes.websocket import ConnectionManager


@pytest.mark.asyncio
async def test_messagebus_publishes_to_correct_websocket_channels():
    """13.3.1: MessageBus.publish_to_websocket publishes to ws:broadcast and ws:user channels."""
    message_bus = MessageBus()
    message_bus._redis = AsyncMock()
    message_bus._append_user_history = AsyncMock()

    # Test global broadcast
    event = {"type": "system_alert", "message": "test"}
    await message_bus.publish_to_websocket(event)
    message_bus._redis.publish.assert_called_once_with("ws:broadcast", json.dumps(event))

    # Reset mock
    message_bus._redis.reset_mock()

    # Test per-user
    event = {"type": "task_update", "task_id": "task-123"}
    await message_bus.publish_to_websocket(event, usernames=["alice", "bob"])
    assert message_bus._redis.publish.call_count == 2
    message_bus._redis.publish.assert_any_call("ws:user:alice", json.dumps(event))
    message_bus._redis.publish.assert_any_call("ws:user:bob", json.dumps(event))


@pytest.mark.asyncio
async def test_connectionmanager_subscribe_unsubscribe_user():
    """13.3.3: ConnectionManager subscribes/unsubscribes per-user channels."""
    manager = ConnectionManager()
    manager._pubsub = AsyncMock()
    manager._user_channels = set()

    # Subscribe
    await manager.subscribe_user("alice")
    manager._pubsub.subscribe.assert_called_with("ws:user:alice")
    assert "ws:user:alice" in manager._user_channels

    # Unsubscribe
    await manager.unsubscribe_user("alice")
    manager._pubsub.unsubscribe.assert_called_with("ws:user:alice")
    assert "ws:user:alice" not in manager._user_channels


@pytest.mark.asyncio
async def test_pubsub_message_forwarding_broadcast():
    """13.3.1/13.3.2: ConnectionManager forwards ws:broadcast to all local connections."""
    manager = ConnectionManager()
    manager._broadcast_local = AsyncMock()

    # Mock pubsub listen
    async def mock_listen():
        yield {"type": "message", "channel": "ws:broadcast", "data": json.dumps({"type": "test_event"})}
        manager._pubsub_task.cancel()

    manager._pubsub = AsyncMock()
    manager._pubsub.listen = mock_listen
    manager._pubsub_task = asyncio.create_task(manager._listen_pubsub())

    try:
        await manager._pubsub_task
    except asyncio.CancelledError:
        pass

    manager._broadcast_local.assert_called_once_with({"type": "test_event"})


@pytest.mark.asyncio
async def test_pubsub_message_forwarding_per_user():
    """13.3.3: ConnectionManager forwards ws:user:{username} to specific user."""
    manager = ConnectionManager()
    manager.send_personal_message = AsyncMock(return_value=True)

    # Mock pubsub listen
    async def mock_listen():
        yield {"type": "message", "channel": "ws:user:alice", "data": json.dumps({"type": "task_update", "task_id": "123"})}
        manager._pubsub_task.cancel()

    manager._pubsub = AsyncMock()
    manager._pubsub.listen = mock_listen
    manager._pubsub_task = asyncio.create_task(manager._listen_pubsub())

    try:
        await manager._pubsub_task
    except asyncio.CancelledError:
        pass

    manager.send_personal_message.assert_called_once()
    call_args = manager.send_personal_message.call_args
    assert call_args[0][0] == {"type": "task_update", "task_id": "123"}
    assert call_args[0][1] == "alice"


@pytest.mark.asyncio
async def test_route_up_publishes_to_websocket_for_head():
    """13.3.1: route_up publishes to websocket when recipient is Head (00001)."""
    message_bus = MessageBus()
    message_bus.publish = AsyncMock()
    message_bus.publish_to_websocket = AsyncMock()
    message_bus._get_parent_id = AsyncMock(return_value="00001")
    message_bus.get_usernames_for_agent = AsyncMock(return_value=["alice"])
    from unittest.mock import MagicMock
    message_bus.db = MagicMock()
    message_bus.db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

    message = AgentMessage(
        message_id="task-123-done",
        sender_id="30001",
        recipient_id="20001",
        message_type="execution",
        content="Task completed",
        route_direction="up"
    )

    await message_bus.route_up(message)

    # Should change recipient to parent (Head)
    assert message.recipient_id == "00001"

    # Should call publish_to_websocket
    message_bus.publish_to_websocket.assert_called_once()
    call_args = message_bus.publish_to_websocket.call_args
    if call_args[0]:
        event = call_args[0][0]
    else:
        event = call_args[1].get('event')
    assert event["type"] == "execution"
    assert "usernames" in (call_args[1] if len(call_args) > 1 else call_args[0])


@pytest.mark.asyncio
async def test_route_down_publishes_to_websocket_for_task_agent():
    """13.3.1/13.3.3: route_down publishes to websocket when recipient is Task agent."""
    message_bus = MessageBus()
    message_bus.publish = AsyncMock()
    message_bus.publish_to_websocket = AsyncMock()
    message_bus.get_usernames_for_agent = AsyncMock(return_value=["alice"])

    message = AgentMessage(
        message_id="delegation-456",
        sender_id="10001",
        recipient_id="30001",
        message_type="delegation",
        content="New task assigned",
        route_direction="down"
    )

    await message_bus.route_down(message)

    message_bus.publish_to_websocket.assert_called_once()
    call_args = message_bus.publish_to_websocket.call_args
    if call_args[0]:
        event = call_args[0][0]
    else:
        event = call_args[1].get('event')
    assert event["type"] == "delegation"
    assert event["content"] == "New task assigned"


@pytest.mark.asyncio
async def test_broadcast_from_head_publishes_to_websocket():
    """13.3.1: broadcast_from_head calls publish_to_websocket for global events."""
    message_bus = MessageBus()
    message_bus.publish = AsyncMock()
    message_bus.publish_to_websocket = AsyncMock()
    from unittest.mock import MagicMock
    message_bus.db = MagicMock()
    message_bus.db.query.return_value.filter.return_value.filter.return_value.all.return_value = []

    message = AgentMessage(
        message_id="test-123",
        sender_id="00001",
        recipient_id="broadcast",
        message_type="notification",
        content="Test alert",
        route_direction="broadcast"
    )

    await message_bus.broadcast_from_head(message)

    message_bus.publish_to_websocket.assert_called_once()
    call_args = message_bus.publish_to_websocket.call_args
    if call_args[0]:
        event = call_args[0][0]
    else:
        event = call_args[1].get('event')
    assert event["type"] == "notification"
    assert event["content"] == "Test alert"


@pytest.mark.asyncio
async def test_cross_worker_simulation():
    """13.3.2: Simulate cross-worker event distribution via Pub/Sub."""
    # This test simulates Worker A publishing and Worker B receiving
    # In real deployment, these would be separate processes

    # Worker A: MessageBus publishes event
    message_bus = MessageBus()
    message_bus._redis = AsyncMock()
    message_bus._append_user_history = AsyncMock()

    event = {"type": "task_update", "task_id": "task-456", "username": "bob"}
    await message_bus.publish_to_websocket(event, usernames=["bob"])

    # Verify publish was called to user channel
    message_bus._redis.publish.assert_called_with("ws:user:bob", json.dumps(event))

    # Worker B: ConnectionManager receives via Pub/Sub and forwards
    manager = ConnectionManager()
    manager.send_personal_message = AsyncMock(return_value=True)

    # Mock pubsub listen to receive the message
    async def mock_listen():
        yield {"type": "message", "channel": "ws:user:bob", "data": json.dumps(event)}
        manager._pubsub_task.cancel()

    manager._pubsub = AsyncMock()
    manager._pubsub.listen = mock_listen
    manager._pubsub_task = asyncio.create_task(manager._listen_pubsub())

    try:
        await manager._pubsub_task
    except asyncio.CancelledError:
        pass

    # Worker B should forward to local connection for bob
    manager.send_personal_message.assert_called_once_with(event, "bob")


@pytest.mark.asyncio
async def test_per_user_filtering_isolation():
    """13.3.3: Per-user filtering - User A doesn't see User B's events."""
    manager = ConnectionManager()
    manager.send_personal_message = AsyncMock(return_value=True)
    received_messages = []

    async def capture_message(msg, username):
        received_messages.append((msg, username))
        return True

    manager.send_personal_message = capture_message

    # Simulate messages for alice and bob coming through Pub/Sub
    async def mock_listen():
        yield {"type": "message", "channel": "ws:user:alice", "data": json.dumps({"type": "task_update", "for": "alice"})}
        yield {"type": "message", "channel": "ws:user:bob", "data": json.dumps({"type": "task_update", "for": "bob"})}
        manager._pubsub_task.cancel()

    manager._pubsub = AsyncMock()
    manager._pubsub.listen = mock_listen
    manager._pubsub_task = asyncio.create_task(manager._listen_pubsub())

    try:
        await manager._pubsub_task
    except asyncio.CancelledError:
        pass

    # Verify each user only receives their own messages
    assert len(received_messages) == 2
    alice_msgs = [msg for msg, user in received_messages if user == "alice"]
    bob_msgs = [msg for msg, user in received_messages if user == "bob"]

    assert len(alice_msgs) == 1
    assert alice_msgs[0]["for"] == "alice"
    assert len(bob_msgs) == 1
    assert bob_msgs[0]["for"] == "bob"