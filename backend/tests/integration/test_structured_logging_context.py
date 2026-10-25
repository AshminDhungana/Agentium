"""Integration test for structured logging context enrichment (Phase C: 21.4.1, 21.4.2).

Verifies that when execute_task_async hits an error path, the structured log
calls contain elapsed_ms, input_summary, and execution_context fields.
"""

import json
import time
from unittest.mock import MagicMock, patch

import pytest

from backend.models.entities.task import Task, TaskType, TaskStatus, TaskPriority
from backend.models.entities.agents import Agent, AgentStatus, AgentType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_task(task_id="T99999"):
    """Build a mock Task that quacks like the ORM model."""
    t = MagicMock(spec=Task)
    t.agentium_id = task_id
    t.title = "Structured Logging Verification Task"
    t.description = "Task designed to fail for logging verification"
    t.task_type = TaskType.EXECUTION
    t.status = TaskStatus.PENDING
    t.priority = TaskPriority.NORMAL
    t.execution_context = json.dumps({"attempt": 1, "target": "synthetic_error"})
    t.progress = 0
    t.mark_failed = MagicMock()
    return t


def _make_mock_agent(agent_id="A00001", side_effect=None):
    t = MagicMock(spec=Agent)
    t.agentium_id = agent_id
    t.status = AgentStatus.ACTIVE
    t.agent_type = AgentType.LEAD_AGENT
    t.execute_with_skill_rag = MagicMock(
        side_effect=side_effect or RuntimeError("Pipeline crash simulation")
    )
    return t


def _make_mock_db(mock_task, mock_agent):
    """Build a mock DB session that returns our task/agent fixtures."""
    mock_db = MagicMock()

    def _query_side_effect(model):
        q = MagicMock()
        if model is Task:
            q.filter_by.return_value.first.return_value = mock_task
        elif model is Agent:
            q.filter_by.return_value.first.return_value = mock_agent
            q.filter.return_value.first.return_value = mock_agent
        else:
            q.filter_by.return_value.first.return_value = None
            q.filter.return_value.first.return_value = None
        return q

    mock_db.query.side_effect = _query_side_effect
    return mock_db


def _run_task_async(mock_db, mock_logger, retries=None):
    """Call the underlying execute_task_async.run() bypassing Celery dispatch."""
    from contextlib import contextmanager

    @contextmanager
    def _mock_get_task_db():
        yield mock_db

    with patch("backend.services.tasks.task_executor.get_task_db", _mock_get_task_db):
        with patch("backend.api.routes.websocket.manager", MagicMock()):
            with patch("backend.core.vector_store.get_vector_store", MagicMock()):
                from backend.services.tasks.task_executor import execute_task_async
                # Access the raw unwrapped function to bypass Celery's PromiseProxy;
                raw_fn = execute_task_async.__wrapped__
                if retries is not None:
                    execute_task_async.request.retries = retries
                else:
                    execute_task_async.request.retries = execute_task_async.max_retries or 3
                return raw_fn("T99999", "A00001")


def _find_structured_error_call(mock_logger):
    """Return the kwargs dict of the first logger.error call that has 'elapsed_ms'."""
    for call in mock_logger.error.call_args_list:
        _, kwargs = call
        if "elapsed_ms" in kwargs:
            return kwargs
    return None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestStructuredLoggingContext:
    """Verify that error-path logs emitted by execute_task_async contain
    elapsed_ms, input_summary, and execution_context as structured fields."""

    @patch("backend.services.tasks.task_executor.logger")
    def test_runtime_error_includes_structured_fields(self, mock_logger):
        """RuntimeError handler should emit elapsed_ms, input_summary, execution_context."""
        mock_task = _make_mock_task()
        mock_agent = _make_mock_agent()
        mock_db = _make_mock_db(mock_task, mock_agent)

        result = _run_task_async(mock_db, mock_logger)

        assert result["status"] == "failed"

        kwargs = _find_structured_error_call(mock_logger)
        assert kwargs is not None, (
            f"No logger.error call contained 'elapsed_ms'. "
            f"Calls: {mock_logger.error.call_args_list}"
        )
        assert isinstance(kwargs["elapsed_ms"], (int, float))
        assert kwargs["elapsed_ms"] >= 0
        assert "input_summary" in kwargs
        assert "execution_context" in kwargs
        ctx = kwargs["execution_context"]
        assert "synthetic_error" in (ctx or ""), f"Expected 'synthetic_error' in execution_context, got: {ctx}"

    @patch("backend.services.tasks.task_executor.logger")
    def test_generic_exception_includes_structured_fields(self, mock_logger):
        """Generic Exception handler should also emit structured context."""
        mock_task = _make_mock_task()
        mock_agent = _make_mock_agent(side_effect=ValueError("Unexpected value failure"))
        mock_db = _make_mock_db(mock_task, mock_agent)

        result = _run_task_async(mock_db, mock_logger)

        assert result["status"] == "failed"

        kwargs = _find_structured_error_call(mock_logger)
        assert kwargs is not None, f"Structured context not found in error calls: {mock_logger.error.call_args_list}"
        assert kwargs["elapsed_ms"] >= 0
        assert "input_summary" in kwargs
        assert "Unexpected value failure" in kwargs.get("error", "")

    @patch("backend.services.tasks.task_executor.logger")
    def test_elapsed_ms_is_positive_duration(self, mock_logger):
        """elapsed_ms should reflect actual wall-clock time, not zero."""
        def _slow_fail(*a, **kw):
            time.sleep(0.01)  # 10ms
            raise RuntimeError("Slow failure")

        mock_task = _make_mock_task()
        mock_agent = _make_mock_agent(side_effect=_slow_fail)
        mock_db = _make_mock_db(mock_task, mock_agent)

        _run_task_async(mock_db, mock_logger)

        kwargs = _find_structured_error_call(mock_logger)
        assert kwargs is not None, "No logger.error call with elapsed_ms found"
        assert kwargs["elapsed_ms"] >= 10.0, (
            f"elapsed_ms should be >= 10ms (sleep was 10ms), got {kwargs['elapsed_ms']}"
        )
