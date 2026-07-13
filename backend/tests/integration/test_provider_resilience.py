"""
Integration tests for Phase 19.3 — Outbound Rate-Limit Resilience.

Task 12 (catch total exhaustion, fail cleanly): when every provider config is
exhausted, LLMClient.generate raises RuntimeError. The Celery executor must
catch it, mark the Task FAILED with a structured reason, write an AuditLog
row, and RETURN cleanly (no infinite re-queue, no worker crash).

These tests drive the REAL Path A execution chain
(Celery execute_task_async -> Agent.execute_with_skill_rag -> skill_rag
.execute_with_skills -> LLMClient.generate) and only stub the provider client
so exhaustion is forced deterministically.
"""

import uuid
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.agents import Agent, AgentStatus
from backend.models.entities.audit import AuditLog
from backend.services.tasks.task_executor import execute_task_async


def _make_task(
    description: str = "provider exhaustion test task",
    status: TaskStatus = TaskStatus.IN_PROGRESS,
) -> Task:
    """Build an unsaved Task row with sane defaults for resilience tests."""
    return Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title="Resilience test task",
        description=description,
        task_type=TaskType.EXECUTION,
        status=status,
        priority=TaskPriority.NORMAL,
        created_by="system",
        is_active=True,
    )


@pytest.mark.integration
class TestExhaustionFailsCleanly:
    """
    Forcing total provider exhaustion must fail the task cleanly:
      - Task.status == "failed"  (terminal, no retry loop)
      - an AuditLog row with action "task_failed_exhaustion" exists
      - the Celery task returns a clean dict (worker moves on)
      - the structured failure_reason is one of the documented values
    """

    def _run_exhausted(self, db_session: Session, exc_message: str):
        # The Celery task opens its own DB connection via get_task_db(). To let
        # it see the uncommitted test Task (and to observe its mark_failed on
        # the same identity-mapped object) we point get_task_db at the test
        # session instead of a fresh connection.
        @contextmanager
        def _fake_get_task_db():
            yield db_session

        task = _make_task()
        db_session.add(task)
        db_session.flush()

        with patch(
            "backend.core.llm_client.LLMClient"
        ) as MockLLM, patch(
            "backend.services.tasks.task_executor.get_task_db", _fake_get_task_db
        ):
            inst = MockLLM.return_value
            inst.generate = AsyncMock(side_effect=RuntimeError(exc_message))
            result = execute_task_async.run(task.agentium_id, "10003")

        db_session.refresh(task)
        return task, result

    def test_exhaustion_marks_task_failed_rate_limited(self, seeded_db: Session):
        task, result = self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 2 provider(s) and 2 retries. "
            "Last error: openai.RateLimitError: 429 Too Many Requests",
        )
        assert task.status == "failed"
        assert task.failure_reason == "rate_limited"
        assert result["status"] == "failed"
        assert result["reason"] == "rate_limited"
        assert (
            seeded_db.query(AuditLog)
            .filter_by(action="task_failed_exhaustion")
            .count()
            >= 1
        )

    def test_exhaustion_marks_task_failed_all_keys_invalid(self, seeded_db: Session):
        task, result = self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
            "Last error: anthropic.AuthenticationError: 401 invalid api key",
        )
        assert task.status == "failed"
        assert task.failure_reason == "all_keys_invalid"
        assert result["reason"] == "all_keys_invalid"
        assert (
            seeded_db.query(AuditLog)
            .filter_by(action="task_failed_exhaustion")
            .count()
            >= 1
        )

    def test_exhaustion_marks_task_failed_provider_unreachable(self, seeded_db: Session):
        # A generic, unclassifiable error defaults to provider_unreachable.
        task, result = self._run_exhausted(
            seeded_db,
            "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
            "Last error: httpx.ConnectError: [Errno 111] Connection refused",
        )
        assert task.status == "failed"
        assert task.failure_reason == "provider_unreachable"
        assert result["reason"] == "provider_unreachable"
        assert (
            seeded_db.query(AuditLog)
            .filter_by(action="task_failed_exhaustion")
            .count()
            >= 1
        )
