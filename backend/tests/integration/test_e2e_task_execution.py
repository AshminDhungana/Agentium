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
from backend.services.workflow_planner import WorkflowPlan, SubTaskSpec
from backend.models.entities.workflow import WorkflowExecution, WorkflowSubTask


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


@pytest.fixture
def mock_critic_service():
    """Mock CriticService for delegate_to_task tests."""
    with patch("backend.services.agent_orchestrator.critic_service") as mock:
        mock.spawn_critics_for_task = AsyncMock(return_value=["critic_output", "critic_plan"])
        mock.review_with_all_task_critics = AsyncMock(return_value={"verdict": "pass", "blocking_critic_type": "output"})
        mock.terminate_critics_for_task = AsyncMock()
        mock.DEFAULT_MAX_RETRIES = 3
        yield mock


@pytest.fixture
def mock_celery_workflow_tasks():
    """Mock Celery deferred task enqueueing for WorkflowExecutor tests."""
    with patch("backend.services.workflow_executor.execute_deferred_subtask") as mock:
        mock.apply_async = MagicMock(return_value=MagicMock(id="celery-test-123"))
        yield mock


@pytest.fixture
def mock_tool_execution():
    """Mock ToolCreationService.execute_tool for execute_task tests."""
    with patch("backend.services.tool_creation_service.ToolCreationService.execute_tool") as mock:
        mock.return_value = {"status": "success", "data": {"result": "ok"}}
        yield mock


# Test Data Builders — add after fixtures, before test classes

def make_task(
    db: Session,
    description: str = "Test task",
    agent_id: str = "3xxxx0001",
    execution_context: dict = None,
) -> Task:
    """Create and persist a Task entity for testing."""
    task = Task(
        agentium_id=f"TST{uuid.uuid4().hex[:5].upper()}",
        description=description,
        status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        task_type=TaskType.GENERAL,
        assigned_agent_id=agent_id,
        execution_context=execution_context or {},
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


def make_agent(
    db: Session,
    tier: str = "3",
    agentium_id: str = None,
    agent_type: AgentType = None,
) -> Agent:
    """Create and persist an Agent entity for testing."""
    aid = agentium_id or f"{tier}xxx{uuid.uuid4().hex[:4]}"
    if agent_type is None:
        agent_type = AgentType.TASK_AGENT if tier == "3" else AgentType.LEAD_AGENT
    agent = Agent(
        agentium_id=aid,
        agent_type=agent_type,
        status=AgentStatus.ACTIVE,
        is_active=True,
        ethos="Test ethos",
        preferred_config_id="cfg-test",
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)
    return agent


def make_workflow_plan(subtasks: list) -> WorkflowPlan:
    """Create a WorkflowPlan with given SubTaskSpec objects."""
    return WorkflowPlan(
        workflow_id=f"WF{uuid.uuid4().hex[:8]}",
        original_message="Test workflow",
        subtasks=subtasks,
    )


def make_subtask_spec(
    intent: str,
    params: dict = None,
    depends_on: list = None,
    schedule_offset_days: int = 0,
    step_index: int = 0,
) -> SubTaskSpec:
    """Create a SubTaskSpec for WorkflowPlan."""
    return SubTaskSpec(
        intent=intent,
        params=params or {},
        depends_on=depends_on or [],
        schedule_offset_days=schedule_offset_days,
        step_index=step_index,
    )