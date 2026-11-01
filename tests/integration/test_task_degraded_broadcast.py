# tests/integration/test_task_degraded_broadcast.py
"""
Tests for task_degraded WebSocket broadcast when LLM providers are exhausted.

Verifies:
1. task_degraded broadcast fires when all providers fail with rate limiting
2. Broadcast contains correct fields (type, task_id, reason, message)
3. No broadcast when fallback succeeds
4. Different failure reasons classified correctly
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import asyncio
import concurrent.futures

from backend.services.tasks.task_executor import execute_task_async
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.agents import Agent, AgentStatus


def _mock_run_async(coro):
    """Execute a coroutine in a new thread with a new event loop."""
    if not asyncio.iscoroutine(coro):
        return coro

    def run_in_new_thread():
        new_loop = asyncio.new_event_loop()
        try:
            return new_loop.run_until_complete(coro)
        finally:
            new_loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(run_in_new_thread)
        return future.result()


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset class-level circuit breakers before each test."""
    from backend.core.llm_client import LLMClient
    LLMClient._circuit_breakers.clear()
    yield
    LLMClient._circuit_breakers.clear()


@pytest.fixture(autouse=True)
def patch_api_key_manager():
    """Patch api_key_manager to avoid DB calls in tests."""
    with patch("backend.core.llm_client.api_key_manager") as mock_manager:
        mock_manager.is_config_healthy.return_value = True
        mock_manager.mark_key_success.return_value = None
        mock_manager.mark_key_failed.return_value = None
        mock_manager.record_spend.return_value = None
        yield mock_manager


@pytest.fixture
def mock_db_session():
    """Create a mock database session."""
    from unittest.mock import MagicMock
    db = MagicMock()
    return db


@pytest.fixture
def mock_task():
    """Create a mock Task entity."""
    task = MagicMock(spec=Task)
    task.agentium_id = "test-task-123"
    task.title = "Test Task"
    task.description = "Test task description"
    task.status = TaskStatus.IN_PROGRESS
    task.execution_context = {}
    task.is_active = True
    task.retry_count = 0
    task.max_retries = 3
    task.error_count = 0
    task.priority = TaskPriority.NORMAL
    task.started_at = None
    task.completed_at = None

    # Methods
    task.complete = MagicMock()
    task.mark_failed = MagicMock()
    task.set_status = MagicMock()
    task.cancel = MagicMock()
    task.to_dict = MagicMock(return_value={"agentium_id": "test-task-123"})

    return task


@pytest.fixture
def mock_agent():
    """Create a mock Agent entity."""
    agent = MagicMock(spec=Agent)
    agent.agentium_id = "test-agent-456"
    agent.status = AgentStatus.ACTIVE
    agent.is_active = True
    agent.preferred_config_id = "primary-config"
    return agent


@pytest.fixture
def mock_websocket_manager():
    """Mock the WebSocket manager for capturing broadcasts."""
    # The task_executor imports manager from backend.api.routes.websocket inside the try block
    with patch("backend.api.routes.websocket.manager") as mock_manager:
        mock_manager.broadcast = AsyncMock()
        yield mock_manager


class TestTaskDegradedBroadcast:
    """Tests for task_degraded WebSocket broadcast."""

    @pytest.mark.asyncio
    async def test_task_degraded_broadcast_on_rate_limited_exhaustion(
        self, mock_db_session, mock_task, mock_agent, mock_websocket_manager, patch_api_key_manager
    ):
        """When all providers exhausted with rate_limited, task_degraded broadcast fires."""

        # Setup DB query chain
        mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_task,  # Task query
            mock_agent,  # Agent query
        ]

        # Create error message that task_executor will classify as "rate_limited"
        # It checks for: "429", "ratelimit", "too many requests", "rate_limit" in msg.lower()
        exc = RuntimeError("LLMClient.generate exhausted all 3 provider(s) and 2 retries. Last error: 429 rate_limit exceeded")

        # Mock the agent's execute_with_skill_rag to raise the exhaustion error
        mock_agent.execute_with_skill_rag = AsyncMock(side_effect=exc)

        # Patch run_async to execute the coroutine properly
        with patch("backend.services.tasks.task_executor.run_async", side_effect=_mock_run_async):
            with patch("backend.services.tasks.task_executor.checkpoint_write", AsyncMock()):
                with patch("backend.services.tasks.task_executor.get_task_db") as mock_get_db:
                    # get_task_db is a context manager, so we need to mock it properly
                    from contextlib import contextmanager
                    @contextmanager
                    def mock_db_context():
                        yield mock_db_session
                    mock_get_db.return_value = mock_db_context()
                    # Execute the task
                    result = execute_task_async("test-task-123", "test-agent-456")

        # Verify task was marked failed
        mock_task.mark_failed.assert_called_once()
        call_args = mock_task.mark_failed.call_args
        assert call_args.kwargs.get("reason") == "rate_limited"

        # Verify task_degraded broadcast was sent
        mock_websocket_manager.broadcast.assert_called()
        broadcast_calls = mock_websocket_manager.broadcast.call_args_list

        # Find the task_degraded broadcast
        degraded_call = None
        for call in broadcast_calls:
            args, kwargs = call
            payload = args[0] if args else kwargs.get("payload", {})
            if payload.get("type") == "task_degraded":
                degraded_call = payload
                break

        assert degraded_call is not None, "task_degraded broadcast not sent"
        assert degraded_call["type"] == "task_degraded"
        assert degraded_call["task_id"] == "test-task-123"
        assert degraded_call["reason"] == "rate_limited"
        assert "temporarily unavailable" in degraded_call["message"].lower()

    @pytest.mark.asyncio
    async def test_task_degraded_broadcast_on_all_keys_invalid(
        self, mock_db_session, mock_task, mock_agent, mock_websocket_manager, patch_api_key_manager
    ):
        """When all keys invalid (401/403), task_degraded broadcast with all_keys_invalid reason."""

        mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_task,
            mock_agent,
        ]

        # Create error message that task_executor will classify as "all_keys_invalid"
        # It checks for: "all_keys_invalid", "401", "403", "invalid api key", "authentication", "insufficient_quota"
        exc = RuntimeError("LLMClient.generate exhausted all 1 provider(s) and 0 retries. Last error: 401 Invalid API key")

        mock_agent.execute_with_skill_rag = AsyncMock(side_effect=exc)

        with patch("backend.services.tasks.task_executor.run_async", side_effect=_mock_run_async):
            with patch("backend.services.tasks.task_executor.checkpoint_write", AsyncMock()):
                with patch("backend.services.tasks.task_executor.get_task_db") as mock_get_db:
                    from contextlib import contextmanager
                    @contextmanager
                    def mock_db_context():
                        yield mock_db_session
                    mock_get_db.return_value = mock_db_context()
                    result = execute_task_async("test-task-123", "test-agent-456")

        # Verify reason is all_keys_invalid
        call_args = mock_task.mark_failed.call_args
        assert call_args.kwargs.get("reason") == "all_keys_invalid"

        # Verify broadcast
        degraded_call = None
        for call in mock_websocket_manager.broadcast.call_args_list:
            args, kwargs = call
            payload = args[0] if args else kwargs.get("payload", {})
            if payload.get("type") == "task_degraded":
                degraded_call = payload
                break

        assert degraded_call is not None
        assert degraded_call["reason"] == "all_keys_invalid"

    @pytest.mark.asyncio
    async def test_task_degraded_broadcast_on_provider_unreachable(
        self, mock_db_session, mock_task, mock_agent, mock_websocket_manager, patch_api_key_manager
    ):
        """When providers unreachable (connection errors), task_degraded broadcast with provider_unreachable reason."""

        mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_task,
            mock_agent,
        ]

        # Create error message that task_executor will classify as "provider_unreachable"
        # This is the default when no specific keywords match
        exc = RuntimeError("LLMClient.generate exhausted all 2 provider(s) and 2 retries. Last error: Connection timeout")

        mock_agent.execute_with_skill_rag = AsyncMock(side_effect=exc)

        with patch("backend.services.tasks.task_executor.run_async", side_effect=_mock_run_async):
            with patch("backend.services.tasks.task_executor.checkpoint_write", AsyncMock()):
                with patch("backend.services.tasks.task_executor.get_task_db") as mock_get_db:
                    from contextlib import contextmanager
                    @contextmanager
                    def mock_db_context():
                        yield mock_db_session
                    mock_get_db.return_value = mock_db_context()
                    result = execute_task_async("test-task-123", "test-agent-456")

        # Verify reason is provider_unreachable (default for transient)
        call_args = mock_task.mark_failed.call_args
        assert call_args.kwargs.get("reason") == "provider_unreachable"

        # Verify broadcast
        degraded_call = None
        for call in mock_websocket_manager.broadcast.call_args_list:
            args, kwargs = call
            payload = args[0] if args else kwargs.get("payload", {})
            if payload.get("type") == "task_degraded":
                degraded_call = payload
                break

        assert degraded_call is not None
        assert degraded_call["reason"] == "provider_unreachable"

    @pytest.mark.asyncio
    async def test_no_degraded_broadcast_when_fallback_succeeds(
        self, mock_db_session, mock_task, mock_agent, mock_websocket_manager, patch_api_key_manager
    ):
        """When primary fails but fallback succeeds, no task_degraded broadcast."""

        mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_task,
            mock_agent,
        ]

        # Success result from fallback
        success_result = {
            "content": "Success from fallback provider",
            "model": "gpt-4o",
            "tokens_used": 100,
            "cost_usd": 0.001,
            "skills_used": [],
        }

        mock_agent.execute_with_skill_rag = AsyncMock(return_value=success_result)

        with patch("backend.services.tasks.task_executor.run_async", side_effect=_mock_run_async):
            with patch("backend.services.tasks.task_executor.checkpoint_write", AsyncMock()):
                with patch("backend.services.tasks.task_executor.get_task_db") as mock_get_db:
                    from contextlib import contextmanager
                    @contextmanager
                    def mock_db_context():
                        yield mock_db_session
                    mock_get_db.return_value = mock_db_context()
                    result = execute_task_async("test-task-123", "test-agent-456")

        # Task should complete successfully
        mock_task.complete.assert_called_once()
        mock_task.mark_failed.assert_not_called()

        # No task_degraded broadcast
        degraded_calls = [
            call for call in mock_websocket_manager.broadcast.call_args_list
            if call[0][0].get("type") == "task_degraded"
        ]
        assert len(degraded_calls) == 0

    @pytest.mark.asyncio
    async def test_degraded_broadcast_contains_user_friendly_message(
        self, mock_db_session, mock_task, mock_agent, mock_websocket_manager, patch_api_key_manager
    ):
        """Broadcast message is user-friendly, not a stack trace."""

        mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_task,
            mock_agent,
        ]

        # Create error message that task_executor will classify as "rate_limited"
        exc = RuntimeError("LLMClient.generate exhausted all 2 provider(s) and 2 retries. Last error: 429 rate_limit exceeded")

        mock_agent.execute_with_skill_rag = AsyncMock(side_effect=exc)

        with patch("backend.services.tasks.task_executor.run_async", side_effect=_mock_run_async):
            with patch("backend.services.tasks.task_executor.checkpoint_write", AsyncMock()):
                with patch("backend.services.tasks.task_executor.get_task_db") as mock_get_db:
                    from contextlib import contextmanager
                    @contextmanager
                    def mock_db_context():
                        yield mock_db_session
                    mock_get_db.return_value = mock_db_context()
                    execute_task_async("test-task-123", "test-agent-456")

        # Find task_degraded broadcast
        degraded_call = None
        for call in mock_websocket_manager.broadcast.call_args_list:
            args, kwargs = call
            payload = args[0] if args else kwargs.get("payload", {})
            if payload.get("type") == "task_degraded":
                degraded_call = payload
                break

        assert degraded_call is not None
        message = degraded_call["message"]
        # Should be user-friendly
        assert "temporarily unavailable" in message.lower() or "rate-limited" in message.lower()
        # Should NOT contain technical details
        assert "ProviderExhaustedError" not in message
        assert "traceback" not in message.lower()
        assert "stack" not in message.lower()


class TestTaskDegradedBroadcastIntegration:
    """Integration-style tests with more realistic setup."""

    @pytest.mark.asyncio
    async def test_execute_task_async_handles_provider_exhausted_error(
        self, mock_db_session, mock_task, mock_agent, mock_websocket_manager, patch_api_key_manager
    ):
        """Full integration: execute_task_async handles ProviderExhaustedError and broadcasts."""

        mock_db_session.query.return_value.filter_by.return_value.first.side_effect = [
            mock_task,
            mock_agent,
        ]

        # Simulate the exact error from LLMClient - with rate_limit keyword for classification
        exc = RuntimeError("LLMClient.generate exhausted all 4 provider(s) and 2 retries. Last error: 429 rate_limit exceeded")

        mock_agent.execute_with_skill_rag = AsyncMock(side_effect=exc)
        mock_agent.preferred_config_id = "primary-config"

        with patch("backend.services.tasks.task_executor.run_async", side_effect=_mock_run_async):
            with patch("backend.services.tasks.task_executor.checkpoint_write", AsyncMock()):
                with patch("backend.services.tasks.task_executor.get_task_db") as mock_get_db:
                    from contextlib import contextmanager
                    @contextmanager
                    def mock_db_context():
                        yield mock_db_session
                    mock_get_db.return_value = mock_db_context()
                    result = execute_task_async("test-task-123", "test-agent-456")

        # Verify result indicates failure
        assert result["status"] == "failed"
        assert result["task_id"] == "test-task-123"
        assert result["reason"] == "rate_limited"

        # Verify audit log was created (db.add called)
        assert mock_db_session.add.called

        # Verify task_degraded broadcast
        degraded_call = None
        for call in mock_websocket_manager.broadcast.call_args_list:
            args, kwargs = call
            payload = args[0] if args else kwargs.get("payload", {})
            if payload.get("type") == "task_degraded":
                degraded_call = payload
                break

        assert degraded_call is not None
        assert degraded_call["task_id"] == "test-task-123"
        assert degraded_call["reason"] == "rate_limited"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])