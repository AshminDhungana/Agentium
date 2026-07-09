"""
Integration test for 19.2 Single-Use Agent Timer.
Requires running infrastructure: postgres, redis, celery-worker, celery-beat.
Run with: pytest backend/tests/integration/test_execution_wait.py -v
"""
import pytest
import time
from datetime import datetime
from backend.services.remote_executor.service import RemoteExecutorService
from backend.services.agent_orchestrator import AgentOrchestrator
from backend.services.wait_poll_service import WaitPollService
from backend.models.entities.wait_condition import WaitStrategy, WaitConditionStatus
from backend.models.entities.task import Task, TaskStatus
from backend.models.entities.remote_execution import RemoteExecutionRecord, ExecutionStatus
from backend.models.database import get_db_context


class TestExecutionWaitIntegration:
    """End-to-end test of agent waiting for execution completion."""

    @pytest.fixture
    def db(self):
        with get_db_context() as db:
            yield db

    @pytest.fixture
    def test_task(self, db):
        """Create a test task."""
        task = Task(
            title="Test Execution Wait",
            description="Task that waits for remote execution",
            task_type="execution",
            created_by="00001",
        )
        db.add(task)
        db.commit()
        db.refresh(task)
        yield task
        # Cleanup
        db.query(WaitCondition).filter(WaitCondition.task_id == task.id).delete()
        db.query(RemoteExecutionRecord).filter(RemoteExecutionRecord.task_id == task.id).delete()
        db.delete(task)
        db.commit()

    def test_agent_can_wait_for_execution_completion(self, db, test_task):
        """
        Full flow: Agent executes code -> gets execution_id -> enters WAIT ->
        Celery polls -> execution completes -> task resumes IN_PROGRESS.
        """
        # 1. Create remote executor and run a simple async execution
        # (In integration test, we create a mock execution record directly)
        execution_id = f"exec_test_{int(time.time())}"

        record = RemoteExecutionRecord(
            execution_id=execution_id,
            agent_id="30001",
            task_id=test_task.id,
            code="result = {'value': 42}",
            language="python",
            status=ExecutionStatus.RUNNING,
        )
        db.add(record)
        db.commit()

        # 2. Agent enters WAIT state via orchestrator
        orchestrator = AgentOrchestrator(db)
        condition_dict = orchestrator.enter_wait(
            task_id=test_task.id,
            strategy="execution",
            config={"execution_id": execution_id},
            poll_interval_seconds=20,
            timeout_seconds=60,
            actor_id="30001",
        )

        assert condition_dict["strategy"] == "execution"
        assert condition_dict["config"]["execution_id"] == execution_id

        # Verify task is in WAITING
        db.refresh(test_task)
        assert test_task.status == TaskStatus.WAITING

        # 3. Simulate execution completing (in real flow, RemoteExecutorService would do this)
        record.status = ExecutionStatus.COMPLETED
        record.completed_at = datetime.utcnow()
        record.summary = {"schema": {"value": "int"}, "row_count": 1, "sample": [{"value": 42}], "stats": {}}
        record.execution_time_ms = 100
        db.commit()

        # 4. Poll the condition (simulates Celery beat)
        WaitPollService.poll_all_active(db)

        # 5. Verify task resumed to IN_PROGRESS
        db.refresh(test_task)
        assert test_task.status == TaskStatus.IN_PROGRESS

        # Verify condition is RESOLVED
        condition = db.query(WaitCondition).filter(
            WaitCondition.task_id == test_task.id
        ).first()
        assert condition.status == WaitConditionStatus.RESOLVED
        assert condition.resolution_data["status"] == "completed"

    def test_agent_wait_times_out_on_execution_failure(self, db, test_task):
        """If execution fails, wait condition expires and task fails."""
        execution_id = f"exec_fail_{int(time.time())}"

        record = RemoteExecutionRecord(
            execution_id=execution_id,
            agent_id="30001",
            task_id=test_task.id,
            code="raise Exception('boom')",
            language="python",
            status=ExecutionStatus.RUNNING,
        )
        db.add(record)
        db.commit()

        orchestrator = AgentOrchestrator(db)
        orchestrator.enter_wait(
            task_id=test_task.id,
            strategy="execution",
            config={"execution_id": execution_id},
            poll_interval_seconds=20,
            timeout_seconds=60,
            actor_id="30001",
        )

        db.refresh(test_task)
        assert test_task.status == TaskStatus.WAITING

        # Simulate execution failure
        record.status = ExecutionStatus.FAILED
        record.completed_at = datetime.utcnow()
        record.error_message = "Container crashed: OOM"
        db.commit()

        # Poll
        WaitPollService.poll_all_active(db)

        # Task should be FAILED (not IN_PROGRESS)
        db.refresh(test_task)
        assert test_task.status == TaskStatus.FAILED  # or ESCALATED per retry logic

        condition = db.query(WaitCondition).filter(
            WaitCondition.task_id == test_task.id
        ).first()
        assert condition.status == WaitConditionStatus.EXPIRED