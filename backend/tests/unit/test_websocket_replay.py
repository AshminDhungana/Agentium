"""
Unit tests for WebSocket replay endpoint enhancement (Section 13.3.4 of TODO.md).
Tests that:
  - 13.3.4: /ws/replay returns per-user history from Redis Streams
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json
from datetime import datetime, timezone


@pytest.mark.asyncio
async def test_replay_endpoint_requires_username_param():
    """13.3.4: /ws/replay accepts username parameter for per-user replay."""
    from backend.api.routes.websocket import replay_events
    from backend.models.entities.user import User

    # Mock current_user
    current_user = {"username": "alice", "role": "sovereign", "user_id": "1"}

    # Mock manager._get_redis
    mock_redis = AsyncMock()
    mock_redis.xread = AsyncMock(return_value=[])

    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager._get_redis = AsyncMock(return_value=mock_redis)

        result = await replay_events(since="2024-01-01T00:00:00", username="alice", current_user=current_user)

        # Should call xread on user's history stream
        mock_redis.xread.assert_called_once()
        call_args = mock_redis.xread.call_args
        stream_key = call_args[0][0].keys().__iter__().__next__()
        assert stream_key == "ws:user:alice:history"


@pytest.mark.asyncio
async def test_replay_endpoint_uses_current_user_when_no_username():
    """13.3.4: /ws/replay defaults to current user when username not provided."""
    from backend.api.routes.websocket import replay_events

    current_user = {"username": "bob", "role": "sovereign", "user_id": "2"}

    mock_redis = AsyncMock()
    mock_redis.xread = AsyncMock(return_value=[])

    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager._get_redis = AsyncMock(return_value=mock_redis)

        result = await replay_events(since="2024-01-01T00:00:00", username=None, current_user=current_user)

        # Should call xread on current user's history stream
        mock_redis.xread.assert_called_once()
        call_args = mock_redis.xread.call_args
        stream_key = list(call_args[0][0].keys())[0]
        assert stream_key == "ws:user:bob:history"


@pytest.mark.asyncio
async def test_replay_endpoint_forbidden_for_other_user():
    """13.3.4: /ws/replay forbids non-sovereign users from replaying other users' events."""
    from backend.api.routes.websocket import replay_events
    from fastapi import HTTPException

    current_user = {"username": "alice", "role": "user", "user_id": "1"}

    mock_redis = AsyncMock()
    mock_redis.xread = AsyncMock(return_value=[])

    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager._get_redis = AsyncMock(return_value=mock_redis)

        with pytest.raises(HTTPException) as exc_info:
            await replay_events(since="2024-01-01T00:00:00", username="bob", current_user=current_user)

        assert exc_info.value.status_code == 403


@pytest.mark.asyncio
async def test_replay_endpoint_allows_sovereign_for_other_user():
    """13.3.4: /ws/replay allows sovereign to replay other users' events."""
    from backend.api.routes.websocket import replay_events

    current_user = {"username": "alice", "role": "sovereign", "user_id": "1"}

    mock_redis = AsyncMock()
    mock_redis.xread = AsyncMock(return_value=[])

    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager._get_redis = AsyncMock(return_value=mock_redis)

        result = await replay_events(since="2024-01-01T00:00:00", username="bob", current_user=current_user)

        # Should succeed for sovereign
        mock_redis.xread.assert_called_once()
        call_args = mock_redis.xread.call_args
        stream_key = list(call_args[0][0].keys())[0]
        assert stream_key == "ws:user:bob:history"


@pytest.mark.asyncio
async def test_replay_endpoint_parses_stream_events():
    """13.3.4: /ws/replay correctly parses events from Redis Stream."""
    from backend.api.routes.websocket import replay_events

    current_user = {"username": "alice", "role": "sovereign", "user_id": "1"}

    # Mock stream entries with proper format
    mock_entries = [
        ("12345-0", {"data": json.dumps({"type": "task_update", "task_id": "1", "timestamp": "2024-01-01T01:00:00"})}),
        ("12346-0", {"data": json.dumps({"type": "chat_message", "content": "hello", "timestamp": "2024-01-01T02:00:00"})}),
    ]

    mock_redis = AsyncMock()
    mock_redis.xread = AsyncMock(return_value=[("ws:user:alice:history", mock_entries)])

    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager._get_redis = AsyncMock(return_value=mock_redis)

        result = await replay_events(since="2024-01-01T00:00:00", username="alice", current_user=current_user)

        assert "events" in result
        assert len(result["events"]) == 2
        assert result["events"][0]["type"] == "task_update"
        assert result["events"][1]["type"] == "chat_message"
        # Should be sorted by timestamp
        assert result["events"][0]["timestamp"] < result["events"][1]["timestamp"]


@pytest.mark.asyncio
async def test_replay_endpoint_handles_missing_stream():
    """13.3.4: /ws/replay returns empty events when stream doesn't exist."""
    from backend.api.routes.websocket import replay_events

    current_user = {"username": "newuser", "role": "sovereign", "user_id": "3"}

    mock_redis = AsyncMock()
    mock_redis.xread = AsyncMock(return_value=[])

    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager._get_redis = AsyncMock(return_value=mock_redis)

        result = await replay_events(since="2024-01-01T00:00:00", username="newuser", current_user=current_user)

        assert result == {"events": []}