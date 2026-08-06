"""
End-to-end integration tests for Agentium task execution workflows.

Covers:
1. AgentOrchestrator.execute_task() → multi-tool LLM loop with stall/provider failure handling
2. WorkflowExecutor.run_dag() → DAG with parallel branches, context merge, deferred tasks
3. AgentOrchestrator.delegate_to_task() → critic review cycles (retry/escalate)

Failure modes verified:
- Agent reasoning stalls (StalledReasoningError, max 3 retries with ethos compression)
- Provider exhaustion / rate limits (structured failure reasons)
"""
import uuid
import asyncio
import contextlib
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch, MagicMock

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    AgentStatus,
    AgentType,
    HeadOfCouncil,
    CouncilMember,
)
from backend.models.entities.task import (
    Task,
    TaskStatus,
    TaskPriority,
    TaskType,
)
from backend.models.entities.audit import AuditLog
from backend.services.reincarnation_service import ReincarnationService
from backend.services.knowledge_assist import CheckpointOutcome
from backend.services.agent_orchestrator import StalledReasoningError


@pytest.fixture
def mock_llm_client():
    """
    Mock LLMClient.generate_with_tools for various scenarios.
    Returns an AsyncMock that can be configured per test.
    """
    with patch("backend.core.llm_client.LLMClient.generate_with_tools", new_callable=AsyncMock) as mock:
        mock.return_value = {
            "content": "Task completed successfully",
            "completed_steps": [],
            "model": "mock-model",
            "tokens_used": 150,
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "finish_reason": "stop",
            "skills_used": [],
            "knowledge_needed": False,
        }
        yield mock


@pytest.fixture
def mock_checkpoint_write():
    """
    Mock checkpoint_write returning successful CheckpointOutcome.
    """
    with patch("backend.services.tasks.task_executor.checkpoint_write", new_callable=AsyncMock) as mock:
        mock.return_value = CheckpointOutcome(
            stage="received",
            queried_chroma=True,
            searched_web=True,
            wrote_back=True,
            fallback_used=False,
            parent_id="ckpt:test123",
        )
        yield mock


@pytest.fixture
def fake_get_task_db(seeded_db: Session):
    """
    Context manager yielding seeded_db for Celery task execution.
    Patches backend.services.tasks.task_executor.get_task_db.
    """
    @contextlib.contextmanager
    def _fake_get_task_db():
        yield seeded_db

    from backend.services.tasks import task_executor as te
    with patch.object(te, "get_task_db", _fake_get_task_db):
        yield


@pytest.fixture
def mock_asyncio_run():
    """
    Patch asyncio.run to execute coroutines directly in the event loop.
    """
    async def _run_async(coro):
        return await coro

    with patch("backend.services.tasks.task_executor.asyncio.run", side_effect=_run_async):
        yield