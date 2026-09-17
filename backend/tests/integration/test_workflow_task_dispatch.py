"""
Integration test for WorkflowEngine._execute_task_step state-machine compliance.

Section 10.2.2 defect: workflow steps created a Task at the default PENDING
status and dispatched it to Celery immediately, leaving it in PENDING. When the
Celery executor later called task.complete() (PENDING -> COMPLETED) or
task.fail() (PENDING -> RETRYING/ESCALATED), those transitions are illegal per
TaskStateMachine, so workflow tasks could never converge to a terminal state.

The fix: `_execute_task_step` must advance the task through LEGAL transitions
(PENDING -> APPROVED -> IN_PROGRESS) via set_status BEFORE dispatch, so the
executor's subsequent complete()/fail() are all legal from IN_PROGRESS and the
transition is recorded in the task's status_history audit trail.
"""

import uuid
from unittest.mock import patch

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowStepType,
    WorkflowExecutionStatus,
)
from backend.models.entities.task import Task, TaskStatus
from backend.services.workflow_engine import WorkflowEngine

pytestmark = pytest.mark.integration


class TestWorkflowTaskDispatchState:
    """Workflow TASK steps must dispatch tasks from a legal execution state."""

    def _dispatch_workflow_task_step(self, seeded_db: Session) -> Task:
        workflow = Workflow(
            name=f"wf-{uuid.uuid4().hex[:8]}",
            template_json={},
            version=1,
        )
        seeded_db.add(workflow)
        seeded_db.flush()

        execution = WorkflowExecution(
            workflow_id=workflow.id,
            status=WorkflowExecutionStatus.RUNNING,
            current_step_index=0,
            context_data={},
            original_message="test dispatch",
            triggered_by="test",
        )
        seeded_db.add(execution)
        seeded_db.flush()

        step = WorkflowStep(
            agentium_id=f"WS{uuid.uuid4().hex[:5].upper()}",
            workflow_id=workflow.id,
            step_index=0,
            step_type=WorkflowStepType.TASK,
            config={"prompt": "perform a workflow step"},
        )
        seeded_db.add(step)
        seeded_db.commit()

        with patch(
            "backend.services.tasks.task_executor.execute_task_async.delay"
        ) as mock_delay:
            success = WorkflowEngine._execute_task_step(seeded_db, execution, step)

        assert success is True
        mock_delay.assert_called_once()

        # The dispatched task id is recorded in the execution context by the step.
        task_id = execution.context_data["step_0_task_id"]
        task = seeded_db.query(Task).filter(Task.id == task_id).first()
        assert task is not None
        return task

    def test_workflow_task_is_in_progress_before_dispatch(self, seeded_db: Session):
        """
        A workflow TASK step must advance its task to IN_PROGRESS (through the
        legal PENDING -> APPROVED -> IN_PROGRESS path) so that the Celery
        executor's later complete()/fail() are legal state-machine transitions.
        """
        task = self._dispatch_workflow_task_step(seeded_db)

        assert task.status == TaskStatus.IN_PROGRESS

    def test_workflow_task_dispatch_advance_is_recorded(self, seeded_db: Session):
        """
        The status advance before dispatch must go through set_status, so the
        transitions appear in the task's status_history (audit trail) rather
        than being a silent direct-status mutation.
        """
        task = self._dispatch_workflow_task_step(seeded_db)

        history = task.status_history or []
        assert any(
            entry.get("status") == TaskStatus.IN_PROGRESS.value
            for entry in history
        ), "workflow dispatch bypassed the state machine — no IN_PROGRESS in status_history"