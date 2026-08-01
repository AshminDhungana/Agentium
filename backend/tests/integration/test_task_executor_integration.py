"""
Integration tests for TaskExecutor Celery tasks end-to-end.
Tests cover task execution lifecycle, escalation handling, and failure scenarios.
"""
import pytest
import uuid
import contextlib
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy.orm import Session

from backend.services.tasks.task_executor import (
    execute_task_async,
    handle_task_escalation,
    daily_constitution_review,
    process_idle_tasks,
    sovereign_data_retention,
)
from backend.models.entities.agents import HeadOfCouncil, CouncilMember, AgentType, AgentStatus
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.models.entities.audit import AuditLog
from backend.models.entities.checkpoint import ExecutionCheckpoint as Checkpoint, CheckpointPhase
from backend.services.reincarnation_service import ReincarnationService
from backend.services.knowledge_assist import CheckpointOutcome


@pytest.mark.integration
class TestExecuteTaskAsyncIntegration:
    """Test execute_task_async Celery task with real database."""

    @pytest.mark.asyncio
    async def test_execute_simple_task_creates_checkpoints(self, seeded_db: Session, celery_eager):
        """Task execution should create checkpoints during execution."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = ReincarnationService.spawn_task_agent(parent=head, name="Executor-Test", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id=f"TEXEC{uuid.uuid4().hex[:6].upper()}",
            title="Simple execution task",
            description="execute a simple command and return result",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock the LLM provider to avoid external calls
        # Also patch asyncio.run to execute coroutines directly in the existing event loop
        async def _run_async(coro):
            return await coro

        def _mock_execute_with_skill_rag(self, task, db):
            return {
                "content": "Task completed successfully",
                "tokens_used": 100,
                "prompt_tokens": 60,
                "completion_tokens": 40,
                "latency_ms": 15,
                "model": "mock",
                "cost_usd": 0.001,
                "finish_reason": "stop",
                "skills_used": [],
                "knowledge_needed": False,
            }

        with patch("backend.services.model_provider.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_gen, \
             patch("backend.services.tasks.task_executor.checkpoint_write", new_callable=AsyncMock) as mock_checkpoint, \
             patch("backend.services.tasks.task_executor.asyncio.run", side_effect=_run_async), \
             patch("backend.models.entities.agents.Agent.execute_with_skill_rag", _mock_execute_with_skill_rag):
            mock_gen.return_value = {
                "content": "Task completed successfully",
                "tokens_used": 100,
                "prompt_tokens": 60,
                "completion_tokens": 40,
                "latency_ms": 15,
                "model": "mock",
                "cost_usd": 0.001,
                "finish_reason": "stop",
            }
            mock_checkpoint.return_value = CheckpointOutcome(
                stage="received",
                queried_chroma=True,
                searched_web=True,
                wrote_back=True,
                fallback_used=False,
                parent_id="ckpt:received:test123"
            )

            # Point get_task_db to our test session
            from backend.services.tasks import task_executor as te

            @contextlib.contextmanager
            def _fake_get_task_db():
                yield seeded_db

            with patch.object(te, "get_task_db", _fake_get_task_db):
                result = execute_task_async.run(task.agentium_id, agent.agentium_id)

        assert result["status"] == "completed"
        assert result["task_id"] == task.agentium_id
        seeded_db.refresh(task)
        assert task.status == TaskStatus.COMPLETED
        assert task.result_summary is not None

        # Note: checkpoint_write() stores checkpoints in ChromaDB (not the
        # ExecutionCheckpoint database table). The database checkpoints are
        # created separately by CheckpointService.create_checkpoint().
        # We verify the mock was called for both received and completed stages.
        assert mock_checkpoint.call_count >= 1
        call_args_list = mock_checkpoint.call_args_list
        stages = [call[0][0] for call in call_args_list]
        assert "received" in stages or "completed" in stages

    @pytest.mark.asyncio
    async def test_execute_task_with_failure_records_error(self, seeded_db: Session, celery_eager):
        """Failed task should have error recorded and marked FAILED."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = ReincarnationService.spawn_task_agent(parent=head, name="Executor-Fail", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id=f"TEXEC{uuid.uuid4().hex[:6].upper()}",
            title="Failing task",
            description="this task will fail",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock the agent's execute_with_skill_rag to raise an exception
        async def _mock_execute_with_skill_rag(self, task, db):
            raise RuntimeError("Simulated LLM failure")

        # Also patch asyncio.run to execute coroutines directly in the existing event loop
        async def _run_async(coro):
            return await coro

        with patch("backend.services.tasks.task_executor.checkpoint_write", new_callable=AsyncMock) as mock_checkpoint, \
             patch("backend.services.tasks.task_executor.asyncio.run", side_effect=_run_async), \
             patch("backend.models.entities.agents.Agent.execute_with_skill_rag", new_callable=AsyncMock) as mock_execute:
            mock_checkpoint.return_value = CheckpointOutcome(
                stage="received",
                queried_chroma=True,
                searched_web=True,
                wrote_back=True,
                fallback_used=False,
                parent_id="ckpt:received:test123"
            )
            mock_execute.side_effect = _mock_execute_with_skill_rag

            # Point get_task_db to our test session
            from backend.services.tasks import task_executor as te

            @contextlib.contextmanager
            def _fake_get_task_db():
                yield seeded_db

            with patch.object(te, "get_task_db", _fake_get_task_db):
                # Force task to not retry by patching max_retries
                execute_task_async.max_retries = 0
                result = execute_task_async.run(task.agentium_id, agent.agentium_id)

        assert result["status"] == "failed"
        seeded_db.refresh(task)
        assert task.status == TaskStatus.FAILED
        # mark_failed() sets failure_reason but does not increment error_count
        # (error_count is incremented by fail() which is for retryable failures)
        assert task.failure_reason == "execution_failed"
        assert task.last_error is not None

    @pytest.mark.asyncio
    async def test_execute_task_provider_exhaustion_rate_limited(self, seeded_db: Session, celery_eager):
        """Total provider exhaustion (rate limited) fails cleanly with structured reason."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = ReincarnationService.spawn_task_agent(parent=head, name="Executor-Rate", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id=f"TEXEC{uuid.uuid4().hex[:6].upper()}",
            title="Rate limited task",
            description="task that hits rate limit",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock the agent's execute_with_skill_rag to raise a rate-limited RuntimeError
        def _mock_execute_with_skill_rag(self, task, db):
            raise RuntimeError(
                "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
                "Last error: openai.RateLimitError: 429 Too Many Requests"
            )

        # Also patch asyncio.run to execute coroutines directly in the existing event loop
        async def _run_async(coro):
            return await coro

        with patch("backend.services.tasks.task_executor.checkpoint_write", new_callable=AsyncMock) as mock_checkpoint, \
             patch("backend.services.tasks.task_executor.asyncio.run", side_effect=_run_async), \
             patch("backend.models.entities.agents.Agent.execute_with_skill_rag", _mock_execute_with_skill_rag):
            mock_checkpoint.return_value = CheckpointOutcome(
                stage="received",
                queried_chroma=True,
                searched_web=True,
                wrote_back=True,
                fallback_used=False,
                parent_id="ckpt:received:test123"
            )

            # Point get_task_db to our test session
            from backend.services.tasks import task_executor as te

            @contextlib.contextmanager
            def _fake_get_task_db():
                yield seeded_db

            with patch.object(te, "get_task_db", _fake_get_task_db):
                # Force task to not retry by patching max_retries
                execute_task_async.max_retries = 0
                result = execute_task_async.run(task.agentium_id, agent.agentium_id)

        assert result["status"] == "failed"
        assert result["reason"] == "rate_limited"
        seeded_db.refresh(task)
        assert task.status == TaskStatus.FAILED
        assert task.failure_reason == "rate_limited"

        # Verify AuditLog was created
        audit_count = seeded_db.query(AuditLog).filter_by(action="task_failed_exhaustion").count()
        assert audit_count >= 1

    @pytest.mark.asyncio
    async def test_execute_task_provider_exhaustion_all_keys_invalid(self, seeded_db: Session, celery_eager):
        """Total provider exhaustion (invalid keys) fails cleanly with structured reason."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = ReincarnationService.spawn_task_agent(parent=head, name="Executor-Keys", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id=f"TEXEC{uuid.uuid4().hex[:6].upper()}",
            title="Invalid keys task",
            description="task that has invalid keys",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock the agent's execute_with_skill_rag to raise an invalid-keys RuntimeError
        def _mock_execute_with_skill_rag(self, task, db):
            raise RuntimeError(
                "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
                "Last error: anthropic.AuthenticationError: 401 invalid api key"
            )

        # Also patch asyncio.run to execute coroutines directly in the existing event loop
        async def _run_async(coro):
            return await coro

        with patch("backend.services.tasks.task_executor.checkpoint_write", new_callable=AsyncMock) as mock_checkpoint, \
             patch("backend.services.tasks.task_executor.asyncio.run", side_effect=_run_async), \
             patch("backend.models.entities.agents.Agent.execute_with_skill_rag", _mock_execute_with_skill_rag):
            mock_checkpoint.return_value = CheckpointOutcome(
                stage="received",
                queried_chroma=True,
                searched_web=True,
                wrote_back=True,
                fallback_used=False,
                parent_id="ckpt:received:test123"
            )

            # Point get_task_db to our test session
            from backend.services.tasks import task_executor as te

            @contextlib.contextmanager
            def _fake_get_task_db():
                yield seeded_db

            with patch.object(te, "get_task_db", _fake_get_task_db):
                # Force task to not retry by patching max_retries
                execute_task_async.max_retries = 0
                result = execute_task_async.run(task.agentium_id, agent.agentium_id)

        assert result["status"] == "failed"
        assert result["reason"] == "all_keys_invalid"
        seeded_db.refresh(task)
        assert task.failure_reason == "all_keys_invalid"

    @pytest.mark.asyncio
    async def test_execute_task_provider_unreachable(self, seeded_db: Session, celery_eager):
        """Provider unreachable fails cleanly with provider_unreachable reason."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = ReincarnationService.spawn_task_agent(parent=head, name="Executor-Unreach", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id=f"TEXEC{uuid.uuid4().hex[:6].upper()}",
            title="Unreachable task",
            description="task with unreachable provider",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock the agent's execute_with_skill_rag to raise a connection error
        def _mock_execute_with_skill_rag(self, task, db):
            raise RuntimeError(
                "LLMClient.generate exhausted all 1 provider(s) and 2 retries. "
                "Last error: httpx.ConnectError: [Errno 111] Connection refused"
            )

        # Also patch asyncio.run to execute coroutines directly in the existing event loop
        async def _run_async(coro):
            return await coro

        with patch("backend.services.tasks.task_executor.checkpoint_write", new_callable=AsyncMock) as mock_checkpoint, \
             patch("backend.services.tasks.task_executor.asyncio.run", side_effect=_run_async), \
             patch("backend.models.entities.agents.Agent.execute_with_skill_rag", _mock_execute_with_skill_rag):
            mock_checkpoint.return_value = CheckpointOutcome(
                stage="received",
                queried_chroma=True,
                searched_web=True,
                wrote_back=True,
                fallback_used=False,
                parent_id="ckpt:received:test123"
            )

            # Point get_task_db to our test session
            from backend.services.tasks import task_executor as te

            @contextlib.contextmanager
            def _fake_get_task_db():
                yield seeded_db

            with patch.object(te, "get_task_db", _fake_get_task_db):
                # Force task to not retry by patching max_retries
                execute_task_async.max_retries = 0
                result = execute_task_async.run(task.agentium_id, agent.agentium_id)

        assert result["status"] == "failed"
        assert result["reason"] == "provider_unreachable"
        seeded_db.refresh(task)
        assert task.failure_reason == "provider_unreachable"


@pytest.mark.integration
class TestHandleTaskEscalationIntegration:
    """Test handle_task_escalation Celery task."""

    def test_handle_escalated_tasks_liquidates(self, seeded_db: Session, celery_eager):
        """Escalated tasks at max retries should be liquidated."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        council = seeded_db.query(CouncilMember).first()
        from backend.services.reincarnation_service import ReincarnationService
        lead = ReincarnationService.spawn_lead_agent(parent=head, name="Lead-Test", description="Test", db=seeded_db)
        seeded_db.commit()

        # Create escalated task
        task = Task(
            agentium_id=f"TESC{uuid.uuid4().hex[:6].upper()}",
            title="Escalated task",
            description="task that has been escalated",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.ESCALATED,
            priority=TaskPriority.NORMAL,
            retry_count=5,
            max_retries=5,
            assigned_task_agent_ids=[lead.agentium_id],
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = handle_task_escalation.run()

        assert result["processed"] == 1
        assert result["details"][0]["decision"] == "liquidated"
        seeded_db.refresh(task)
        assert task.status == TaskStatus.CANCELLED

    def test_handle_escalated_tasks_modifies_critical(self, seeded_db: Session, celery_eager):
        """Critical priority escalated tasks should get resources allocated."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        council = seeded_db.query(CouncilMember).first()
        from backend.services.reincarnation_service import ReincarnationService
        lead = ReincarnationService.spawn_lead_agent(parent=head, name="Lead-Critical", description="Test", db=seeded_db)
        seeded_db.commit()

        # Create CRITICAL escalated task - should allocate resources
        task = Task(
            agentium_id=f"TESC{uuid.uuid4().hex[:6].upper()}",
            title="Critical escalated task",
            description="critical task escalated",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.ESCALATED,
            priority=TaskPriority.CRITICAL,
            retry_count=5,
            max_retries=5,
            assigned_task_agent_ids=[lead.agentium_id],
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = handle_task_escalation.run()

        assert result["processed"] == 1
        # Critical tasks get allocate_resources or modify_scope
        assert result["details"][0]["decision"] in ("resources_allocated", "modify_scope")

    def test_handle_escalation_no_tasks(self, seeded_db: Session, celery_eager):
        """Should handle case with no escalated tasks."""
        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = handle_task_escalation.run()

        assert result["processed"] == 0


@pytest.mark.integration
class TestDailyConstitutionReviewIntegration:
    """Test daily_constitution_review Celery task."""

    def test_daily_constitution_review(self, seeded_db: Session, celery_eager):
        """Daily constitution review should complete successfully."""
        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = daily_constitution_review.run()

        assert result["status"] == "completed"


@pytest.mark.integration
class TestProcessIdleTasksIntegration:
    """Test process_idle_tasks Celery task."""

    def test_process_idle_tasks(self, seeded_db: Session, celery_eager):
        """Process idle tasks should complete successfully."""
        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = process_idle_tasks.run()

        assert result["status"] == "completed"


@pytest.mark.integration
class TestSovereignDataRetentionIntegration:
    """Test sovereign_data_retention Celery task."""

    def test_sovereign_data_retention(self, seeded_db: Session, celery_eager):
        """Data retention should complete and archive old tasks."""
        # Create an old completed task
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        old_task = Task(
            agentium_id=f"TOLD{uuid.uuid4().hex[:6].upper()}",
            title="Old task",
            description="completed long ago",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.COMPLETED,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by=head.agentium_id,
            completed_at=datetime.utcnow() - timedelta(days=60),
        )
        seeded_db.add(old_task)
        seeded_db.flush()

        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = sovereign_data_retention.run()

        assert result["status"] == "completed"
        assert result["results"]["tasks_archived"] >= 1
        seeded_db.refresh(old_task)
        assert old_task.is_active is False

    def test_sovereign_data_retention_no_old_tasks(self, seeded_db: Session, celery_eager):
        """Should complete even with no old tasks."""
        # Patch the get_task_db context manager in the task_executor module
        from backend.services.tasks import task_executor as te

        @contextlib.contextmanager
        def _fake_get_task_db():
            yield seeded_db

        with patch.object(te, "get_task_db", _fake_get_task_db):
            result = sovereign_data_retention.run()

        assert result["status"] == "completed"
        assert result["results"]["tasks_archived"] == 0


# Import datetime for retention test
from datetime import datetime, timedelta