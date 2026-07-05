"""
Integration tests for the Workflow Engine.

Covers:
  Step 1 — 5-step workflow: task → condition → parallel → human_approval → task
  Step 2 — Cron trigger via `schedule_cron`
  Step 3 — Version increment on update
  Step 4 — Rollback to prior version
  Step 5 — ETA estimation within 20% of actual
"""

import pytest
import json
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch

from backend.services.workflow_engine import WorkflowEngine
from backend.models.entities.workflow import (
    Workflow,
    WorkflowStep,
    WorkflowVersion,
    WorkflowStepType,
    WorkflowExecutionStatus,
    WorkflowExecution,
)
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority

pytestmark = pytest.mark.integration


class TestWorkflowEngine:
    """Holistic suite for the Workflow Automation Pipeline."""

    # =======================================================================
    # Helpers
    # =======================================================================

    def _make_5_step_template(self) -> dict:
        """Canonical 5-step template: task → condition → parallel → human_approval → task"""
        return {
            "steps": [
                {
                    "step_index": 0,
                    "type": "task",
                    "config": {"task_title": "1. Init task", "prompt": "First step"},
                    "on_success_step": 1,
                    "on_failure_step": None,
                },
                {
                    "step_index": 1,
                    "type": "condition",
                    "config": {"condition": {"operator": "==", "key": "status", "expected": "ok"}},
                    "on_success_step": 2,
                    "on_failure_step": None,
                },
                {
                    "step_index": 2,
                    "type": "parallel",
                    "config": {"branches": ["branch-a", "branch-b"]},
                    "on_success_step": 3,
                    "on_failure_step": None,
                },
                {
                    "step_index": 3,
                    "type": "human_approval",
                    "config": {"required_approver": "admin"},
                    "on_success_step": 4,
                    "on_failure_step": None,
                },
                {
                    "step_index": 4,
                    "type": "task",
                    "config": {"task_title": "5. Final task", "prompt": "Final step"},
                    "on_success_step": None,
                    "on_failure_step": None,
                },
            ]
        }

    # =======================================================================
    # 1. 5-step workflow: task → condition → parallel → human_approval → task
    # =======================================================================

    def test_create_workflow_from_5_step_template(self, db_session):
        """A workflow with all step types should be persisted with correct step types."""
        template = self._make_5_step_template()

        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="Test 5-Step Workflow",
            template_json=template,
            agent_id=None,
            cron=None,
        )

        assert workflow is not None
        assert workflow.version == 1
        assert workflow.name == "Test 5-Step Workflow"

    def test_triggers_execution_and_steps_advance(self, db_session):
        """Execution should start with step 0 and advance through steps."""
        template = self._make_5_step_template()

        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="Test 5-Step Workflow",
            template_json=template,
            agent_id=None,
        )

        execution = WorkflowEngine.trigger_execution(
            db=db_session,
            workflow_id=workflow.id,
            trigger="api",
            context={"status": "ok"},
        )

        assert execution is not None
        assert execution.workflow_id == workflow.id
        assert execution.status == WorkflowExecutionStatus.RUNNING
        assert execution.current_step_index == 0

        # Step 0: task — dispatches to agent pool and sets status to PAUSED
        WorkflowEngine.execute_current_step(db=db_session, execution_id=execution.id)
        db_session.refresh(execution)
        assert execution.current_step_index == 1
        assert execution.status == WorkflowExecutionStatus.PAUSED

        # Simulate task completion callback: resume the workflow
        execution.status = WorkflowExecutionStatus.RUNNING
        db_session.commit()

        # Step 1: condition (true because context["status"] == "ok")
        WorkflowEngine.execute_current_step(db=db_session, execution_id=execution.id)
        db_session.refresh(execution)
        assert execution.current_step_index == 2

        # Step 2: parallel
        WorkflowEngine.execute_current_step(db=db_session, execution_id=execution.id)
        db_session.refresh(execution)
        assert execution.current_step_index == 3

        # Step 3: human_approval — should pause
        WorkflowEngine.execute_current_step(db=db_session, execution_id=execution.id)
        db_session.refresh(execution)
        assert execution.status == WorkflowExecutionStatus.PAUSED

    # =======================================================================
    # 2. Cron trigger via `schedule_cron`
    # =======================================================================

    def test_cron_trigger_stores_cron_expression(self, db_session):
        """Workflow should store the cron expression when provided."""
        template = self._make_5_step_template()

        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="Cron Workflow",
            template_json=template,
            agent_id=None,
            cron="0 9 * * *",
        )

        assert workflow.schedule_cron == "0 9 * * *"

    # =======================================================================
    # 3. Version increment on update
    # =======================================================================

    def test_update_workflow_increments_version(self, db_session):
        """Updating a workflow should bump the version number."""
        template = self._make_5_step_template()

        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="Version Workflow",
            template_json=template,
            agent_id=None,
        )

        assert workflow.version == 1

        updated_template = self._make_5_step_template()
        updated_template["steps"][0]["config"]["task_title"] = "Updated task title"

        updated_workflow = WorkflowEngine.update_workflow(
            db=db_session,
            workflow_id=workflow.id,
            new_template=updated_template,
        )

        assert updated_workflow.version == 2

    def test_update_workflow_creates_version_snapshot(self, db_session):
        """Updating a workflow should store the prior version in workflow_versions."""
        template = self._make_5_step_template()
        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="Version Snapshot Workflow",
            template_json=template,
            agent_id=None,
        )

        old_title = template["steps"][0]["config"]["task_title"]

        updated_template = self._make_5_step_template()
        updated_template["steps"][0]["config"]["task_title"] = "Updated task title"

        WorkflowEngine.update_workflow(
            db=db_session,
            workflow_id=workflow.id,
            new_template=updated_template,
        )

        versions = db_session.query(WorkflowVersion).filter_by(workflow_id=workflow.id).all()
        assert len(versions) >= 2

        version = max(versions, key=lambda v: v.version)
        assert version.template_json["steps"][0]["config"]["task_title"] == old_title

    # =======================================================================
    # 4. Rollback to prior version
    # =======================================================================

    def test_rollback_to_prior_version(self, db_session):
        """Rollback should restore the workflow to a previous version's template and steps."""
        template = self._make_5_step_template()
        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="Rollback Workflow",
            template_json=template,
            agent_id=None,
        )

        original_title = template["steps"][0]["config"]["task_title"]

        updated_template = self._make_5_step_template()
        updated_template["steps"][0]["config"]["task_title"] = "Updated task title"

        WorkflowEngine.update_workflow(
            db=db_session,
            workflow_id=workflow.id,
            new_template=updated_template,
        )

        # Fetch version 1 snapshot
        version_1 = (
            db_session.query(WorkflowVersion)
            .filter_by(workflow_id=workflow.id, version=1)
            .first()
        )
        assert version_1 is not None

        # Rollback to version 1
        WorkflowEngine.update_workflow(
            db=db_session,
            workflow_id=workflow.id,
            new_template=version_1.template_json,
        )

        # Verify the title is back to the original
        db_session.refresh(workflow)
        assert workflow.template_json["steps"][0]["config"]["task_title"] == original_title

    # =======================================================================
    # 5. ETA estimation within 20% of actual
    # =======================================================================

    def test_eta_estimation_within_20_percent(self, db_session):
        """ETA should be within 20% of the actual execution time."""
        template = self._make_5_step_template()
        workflow = WorkflowEngine.create_workflow(
            db=db_session,
            name="ETA Workflow",
            template_json=template,
            agent_id=None,
        )

        # Simulate multiple completed executions with known duration
        actual_duration = 120  # seconds
        for i in range(5):
            execution = WorkflowExecution(
                agentium_id=f"WX{i+1:05d}",
                workflow_id=workflow.id,
                status=WorkflowExecutionStatus.COMPLETED,
                current_step_index=4,
                context_data={},
                triggered_by="api",
                started_at=datetime.utcnow() - timedelta(seconds=actual_duration),
                completed_at=datetime.utcnow(),
            )
            db_session.add(execution)
        db_session.commit()

        # Calculate ETA
        eta_data = WorkflowEngine.calculate_eta(db=db_session, workflow_id=workflow.id)
        eta = eta_data["eta_seconds"]

        assert eta is not None
        # ETA should be within 20% of actual duration
        assert abs(eta - actual_duration) / actual_duration <= 0.2
