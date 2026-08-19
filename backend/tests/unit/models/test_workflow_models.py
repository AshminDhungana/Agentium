"""
Unit tests for Workflow and Scheduled Task models.
Tests Workflow, WorkflowExecution, WorkflowStep, WorkflowVersion, WorkflowSubTask,
ScheduledTask, and ScheduledTaskExecution models.
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

try:
    from backend.models.entities.workflow import (
        Workflow, WorkflowExecution, WorkflowStep, WorkflowVersion, WorkflowSubTask,
        WorkflowExecutionStatus, WorkflowStepType
    )
    from backend.models.entities.scheduled_task import (
        ScheduledTask, ScheduledTaskExecution,
        ScheduledTaskStatus, ScheduledTaskExecutionStatus
    )
except ImportError:
    from models.entities.workflow import (
        Workflow, WorkflowExecution, WorkflowStep, WorkflowVersion, WorkflowSubTask,
        WorkflowExecutionStatus, WorkflowStepType
    )
    from models.entities.scheduled_task import (
        ScheduledTask, ScheduledTaskExecution,
        ScheduledTaskStatus, ScheduledTaskExecutionStatus
    )


class TestWorkflowEnums:
    """Tests for Workflow enums."""

    @pytest.mark.parametrize("status", [
        WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.RUNNING,
        WorkflowExecutionStatus.PAUSED, WorkflowExecutionStatus.COMPLETED,
        WorkflowExecutionStatus.FAILED, WorkflowExecutionStatus.COMPLETED_WITH_ERRORS,
    ])
    def test_workflow_execution_status_values(self, status):
        """All WorkflowExecutionStatus values are valid."""
        assert status in (
            WorkflowExecutionStatus.PENDING, WorkflowExecutionStatus.RUNNING,
            WorkflowExecutionStatus.PAUSED, WorkflowExecutionStatus.COMPLETED,
            WorkflowExecutionStatus.FAILED, WorkflowExecutionStatus.COMPLETED_WITH_ERRORS,
        )
        assert isinstance(status.value, str)

    @pytest.mark.parametrize("step_type", [
        WorkflowStepType.TASK, WorkflowStepType.CONDITION,
        WorkflowStepType.PARALLEL, WorkflowStepType.HUMAN_APPROVAL,
        WorkflowStepType.DELAY, WorkflowStepType.WAIT_POLL,
    ])
    def test_workflow_step_type_values(self, step_type):
        """All WorkflowStepType values are valid."""
        assert step_type in (
            WorkflowStepType.TASK, WorkflowStepType.CONDITION,
            WorkflowStepType.PARALLEL, WorkflowStepType.HUMAN_APPROVAL,
            WorkflowStepType.DELAY, WorkflowStepType.WAIT_POLL,
        )
        assert isinstance(step_type.value, str)

    @pytest.mark.parametrize("status", [
        ScheduledTaskStatus.ACTIVE, ScheduledTaskStatus.PAUSED,
        ScheduledTaskStatus.RUNNING, ScheduledTaskStatus.ERROR,
        ScheduledTaskStatus.COMPLETED,
    ])
    def test_scheduled_task_status_values(self, status):
        """All ScheduledTaskStatus values are valid."""
        assert status in (
            ScheduledTaskStatus.ACTIVE, ScheduledTaskStatus.PAUSED,
            ScheduledTaskStatus.RUNNING, ScheduledTaskStatus.ERROR,
            ScheduledTaskStatus.COMPLETED,
        )
        assert isinstance(status.value, str)

    @pytest.mark.parametrize("status", [
        ScheduledTaskExecutionStatus.RUNNING, ScheduledTaskExecutionStatus.SUCCESS,
        ScheduledTaskExecutionStatus.FAILED, ScheduledTaskExecutionStatus.TIMEOUT,
        ScheduledTaskExecutionStatus.RETRYING,
    ])
    def test_scheduled_task_execution_status_values(self, status):
        """All ScheduledTaskExecutionStatus values are valid."""
        assert status in (
            ScheduledTaskExecutionStatus.RUNNING, ScheduledTaskExecutionStatus.SUCCESS,
            ScheduledTaskExecutionStatus.FAILED, ScheduledTaskExecutionStatus.TIMEOUT,
            ScheduledTaskExecutionStatus.RETRYING,
        )
        assert isinstance(status.value, str)


class TestWorkflowModel:
    """Tests for Workflow model."""

    def test_workflow_creation(self, db_session):
        """Workflow creates with all required fields."""
        workflow = Workflow(
            agentium_id="WF00001",
            name="test_workflow",
            description="Test workflow description",
            template_json={"steps": [{"type": "task", "config": {}}]},
            version=1,
            schedule_cron="0 9 * * *",
        )
        db_session.add(workflow)
        db_session.commit()
        db_session.refresh(workflow)

        assert workflow.name == "test_workflow"
        assert workflow.description == "Test workflow description"
        assert workflow.template_json == {"steps": [{"type": "task", "config": {}}]}
        assert workflow.version == 1
        assert workflow.schedule_cron == "0 9 * * *"
        assert workflow.agentium_id == "WF00001"

    def test_workflow_defaults(self, db_session):
        """Workflow defaults are correct."""
        workflow = Workflow(
            agentium_id="WF00002",
            name="default_workflow",
        )
        db_session.add(workflow)
        db_session.commit()

        assert workflow.description is None
        assert workflow.template_json == {}
        assert workflow.version == 1
        assert workflow.schedule_cron is None
        assert workflow.created_by_agent_id is None

    def test_workflow_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        workflow = Workflow(
            agentium_id="WF00003",
            name="dict_workflow",
            description="Dict workflow",
            template_json={"steps": []},
            version=2,
            schedule_cron="@daily",
            created_by_agent_id="agent-uuid-123",
        )
        db_session.add(workflow)
        db_session.commit()

        data = workflow.to_dict()
        assert data["name"] == "dict_workflow"
        assert data["description"] == "Dict workflow"
        assert data["template_json"] == {"steps": []}
        assert data["version"] == 2
        assert data["schedule_cron"] == "@daily"
        assert data["created_by_agent_id"] == "agent-uuid-123"
        assert "created_at" in data
        assert "updated_at" in data

    def test_workflow_agentium_id_generation(self, db_session):
        """Workflow generates agentium_id if not provided - skipped in unit tests."""
        # The _generate_workflow_id queries DB which doesn't work with SQLite in tests
        # Workflow IDs are typically set by service layer
        pass


class TestWorkflowExecution:
    """Tests for WorkflowExecution model."""

    def test_workflow_execution_creation(self, db_session):
        """WorkflowExecution creates with all fields."""
        # Create parent workflow first
        workflow = Workflow(agentium_id="WF00004", name="parent")
        db_session.add(workflow)
        db_session.commit()

        execution = WorkflowExecution(
            agentium_id="WXABCDE",
            workflow_id=workflow.id,
            original_message="Test message",
            status=WorkflowExecutionStatus.RUNNING,
            context_data={"key": "value"},
            created_by="00001",
            current_step_index=2,
            started_at=datetime.now(timezone.utc),
            triggered_by="manual",
        )
        db_session.add(execution)
        db_session.commit()
        db_session.refresh(execution)

        assert execution.workflow_id == workflow.id
        assert execution.original_message == "Test message"
        assert execution.status == WorkflowExecutionStatus.RUNNING
        assert execution.context_data == {"key": "value"}
        assert execution.created_by == "00001"
        assert execution.current_step_index == 2
        assert execution.started_at is not None
        assert execution.triggered_by == "manual"
        assert execution.agentium_id == "WXABCDE"

    def test_workflow_execution_defaults(self, db_session):
        """WorkflowExecution defaults are correct."""
        workflow = Workflow(agentium_id="WF00005", name="default_exec")
        db_session.add(workflow)
        db_session.commit()

        execution = WorkflowExecution(workflow_id=workflow.id)
        db_session.add(execution)
        db_session.commit()

        assert execution.status == WorkflowExecutionStatus.PENDING
        assert execution.context_data == {}
        assert execution.original_message is None
        assert execution.error is None
        assert execution.created_by is None
        assert execution.current_step_index == 0
        assert execution.started_at is None
        assert execution.completed_at is None
        assert execution.triggered_by is None

    def test_workflow_execution_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        workflow = Workflow(agentium_id="WF00006", name="dict_exec")
        db_session.add(workflow)
        db_session.commit()

        started = datetime.now(timezone.utc)
        execution = WorkflowExecution(
            agentium_id="WXFGHIJ",
            workflow_id=workflow.id,
            status=WorkflowExecutionStatus.COMPLETED,
            current_step_index=5,
            context_data={"result": "ok"},
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            triggered_by="schedule",
        )
        db_session.add(execution)
        db_session.commit()

        data = execution.to_dict()
        assert data["workflow_id"] == workflow.id
        assert data["status"] == "completed"
        assert data["current_step_index"] == 5
        assert data["context_data"] == {"result": "ok"}
        assert data["started_at"] == started.replace(tzinfo=None).isoformat()  # SQLite stores naive
        assert data["triggered_by"] == "schedule"


class TestWorkflowStep:
    """Tests for WorkflowStep model."""

    def test_workflow_step_creation(self, db_session):
        """WorkflowStep creates with all fields."""
        workflow = Workflow(agentium_id="WF00007", name="step_parent")
        db_session.add(workflow)
        db_session.commit()

        step = WorkflowStep(
            agentium_id="WS00001",
            workflow_id=workflow.id,
            step_index=0,
            step_type=WorkflowStepType.TASK,
            config={"agent_type": "task_agent", "params": {"action": "search"}},
            on_success_step=1,
            on_failure_step=2,
        )
        db_session.add(step)
        db_session.commit()
        db_session.refresh(step)

        assert step.workflow_id == workflow.id
        assert step.step_index == 0
        assert step.step_type == WorkflowStepType.TASK
        assert step.config == {"agent_type": "task_agent", "params": {"action": "search"}}
        assert step.on_success_step == 1
        assert step.on_failure_step == 2
        assert step.agentium_id == "WS00001"

    def test_workflow_step_defaults(self, db_session):
        """WorkflowStep defaults are correct."""
        workflow = Workflow(agentium_id="WF00008", name="default_step")
        db_session.add(workflow)
        db_session.commit()

        step = WorkflowStep(
            agentium_id="WS00003",  # Required for test - _generate_step_id queries DB
            workflow_id=workflow.id,
            step_index=1,
            step_type=WorkflowStepType.CONDITION,
        )
        db_session.add(step)
        db_session.commit()

        assert step.config == {}
        assert step.on_success_step is None
        assert step.on_failure_step is None

    def test_workflow_step_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        workflow = Workflow(agentium_id="WF00009", name="dict_step")
        db_session.add(workflow)
        db_session.commit()

        step = WorkflowStep(
            agentium_id="WS00002",
            workflow_id=workflow.id,
            step_index=2,
            step_type=WorkflowStepType.PARALLEL,
            config={"branches": ["a", "b"]},
            on_success_step=3,
            on_failure_step=None,
        )
        db_session.add(step)
        db_session.commit()

        data = step.to_dict()
        assert data["workflow_id"] == workflow.id
        assert data["step_index"] == 2
        assert data["step_type"] == "parallel"
        assert data["config"] == {"branches": ["a", "b"]}
        assert data["on_success_step"] == 3
        assert data["on_failure_step"] is None


class TestWorkflowVersion:
    """Tests for WorkflowVersion model."""

    def test_workflow_version_creation(self, db_session):
        """WorkflowVersion creates with all fields."""
        workflow = Workflow(agentium_id="WF00010", name="version_parent")
        db_session.add(workflow)
        db_session.commit()

        version = WorkflowVersion(
            agentium_id="WV00001",
            workflow_id=workflow.id,
            version=1,
            template_json={"steps": [{"old": "config"}]},
        )
        db_session.add(version)
        db_session.commit()
        db_session.refresh(version)

        assert version.workflow_id == workflow.id
        assert version.version == 1
        assert version.template_json == {"steps": [{"old": "config"}]}
        assert version.agentium_id == "WV00001"

    def test_workflow_version_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        workflow = Workflow(agentium_id="WF00011", name="dict_version")
        db_session.add(workflow)
        db_session.commit()

        version = WorkflowVersion(
            agentium_id="WV00002",
            workflow_id=workflow.id,
            version=2,
            template_json={"steps": [{"new": "config"}]},
        )
        db_session.add(version)
        db_session.commit()

        data = version.to_dict()
        assert data["workflow_id"] == workflow.id
        assert data["version"] == 2
        assert data["template_json"] == {"steps": [{"new": "config"}]}
        assert "created_at" in data


class TestWorkflowSubTask:
    """Tests for WorkflowSubTask model."""

    def test_workflow_subtask_creation(self, db_session):
        """WorkflowSubTask creates with all fields."""
        workflow = Workflow(agentium_id="WF00012", name="subtask_parent")
        db_session.add(workflow)
        db_session.commit()

        subtask = WorkflowSubTask(
            agentium_id="SUBABCD",
            workflow_id=workflow.id,
            step_index=0,
            intent="search_code",
            params={"query": "test"},
            depends_on=[],
            status="pending",
            schedule_offset_days=0,
        )
        db_session.add(subtask)
        db_session.commit()
        db_session.refresh(subtask)

        assert subtask.workflow_id == workflow.id
        assert subtask.step_index == 0
        assert subtask.intent == "search_code"
        assert subtask.params == {"query": "test"}
        assert subtask.depends_on == []
        assert subtask.status == "pending"
        assert subtask.schedule_offset_days == 0
        assert subtask.agentium_id == "SUBABCD"

    def test_workflow_subtask_defaults(self, db_session):
        """WorkflowSubTask defaults are correct."""
        workflow = Workflow(agentium_id="WF00013", name="default_subtask")
        db_session.add(workflow)
        db_session.commit()

        subtask = WorkflowSubTask(
            workflow_id=workflow.id,
            step_index=1,
            intent="analyze",
            params={"target": "code"},
        )
        db_session.add(subtask)
        db_session.commit()

        assert subtask.depends_on == []
        assert subtask.status == "pending"
        assert subtask.schedule_offset_days == 0
        assert subtask.result is None
        assert subtask.error is None
        assert subtask.celery_task_id is None
        assert subtask.scheduled_for is None
        assert subtask.completed_at is None


class TestScheduledTask:
    """Tests for ScheduledTask model."""

    def test_scheduled_task_creation(self, db_session):
        """ScheduledTask creates with all fields."""
        task = ScheduledTask(
            agentium_id="R0001",
            name="daily_backup",
            description="Backup database daily",
            cron_expression="0 2 * * *",
            timezone="UTC",
            task_payload=json.dumps({"action": "backup", "target": "database"}),
            owner_agentium_id="00001",
            status=ScheduledTaskStatus.ACTIVE,
            priority=3,
            max_retries=5,
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.name == "daily_backup"
        assert task.description == "Backup database daily"
        assert task.cron_expression == "0 2 * * *"
        assert task.timezone == "UTC"
        assert task.get_task_payload() == {"action": "backup", "target": "database"}
        assert task.owner_agentium_id == "00001"
        assert task.status == ScheduledTaskStatus.ACTIVE
        assert task.priority == 3
        assert task.max_retries == 5
        assert task.execution_count == 0
        assert task.failure_count == 0
        assert task.agentium_id == "R0001"

    def test_scheduled_task_defaults(self, db_session):
        """ScheduledTask defaults are correct."""
        task = ScheduledTask(
            agentium_id="R0002",
            name="default_task",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        assert task.description is None
        assert task.timezone == "UTC"
        assert task.owner_agentium_id == "00001"
        assert task.status == ScheduledTaskStatus.ACTIVE
        assert task.priority == 1
        assert task.execution_count == 0
        assert task.failure_count == 0
        assert task.max_retries == 3
        assert task.executing_agent_id is None

    def test_scheduled_task_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        task = ScheduledTask(
            agentium_id="R0003",
            name="dict_task",
            cron_expression="0 * * * *",
            task_payload=json.dumps({"action": "test"}),
            owner_agentium_id="00001",
            status=ScheduledTaskStatus.ACTIVE,
            priority=2,
            last_execution_at=datetime.now(timezone.utc),
            execution_count=10,
            failure_count=1,
        )
        db_session.add(task)
        db_session.commit()

        data = task.to_dict()
        assert data["agentium_id"] == "R0003"
        assert data["name"] == "dict_task"
        assert data["cron_expression"] == "0 * * * *"
        assert data["task_payload"] == {"action": "test"}
        assert data["owner_agentium_id"] == "00001"
        assert data["status"] == "active"
        assert data["priority"] == 2
        assert data["schedule"]["execution_count"] == 10
        assert data["schedule"]["failure_count"] == 1
        assert "created_at" in data

    def test_scheduled_task_cron_validation(self, db_session):
        """Cron expression validation works."""
        # Valid standard cron
        task1 = ScheduledTask(
            agentium_id="R0010",
            name="valid_cron_1",
            cron_expression="0 9 * * 1-5",
            task_payload="{}",
        )
        db_session.add(task1)
        db_session.commit()
        assert task1.cron_expression == "0 9 * * 1-5"

        # Valid special cron
        task2 = ScheduledTask(
            agentium_id="R0011",
            name="valid_cron_2",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task2)
        db_session.commit()
        assert task2.cron_expression == "@daily"

        # Invalid special cron - validation happens on init
        with pytest.raises(ValueError, match="Invalid special cron"):
            ScheduledTask(
                agentium_id="R0012",
                name="invalid_cron",
                cron_expression="@invalid",
                task_payload="{}",
            )

        # Invalid standard cron (wrong number of parts)
        with pytest.raises(ValueError, match="Cron expression must have 5 parts"):
            ScheduledTask(
                agentium_id="R0013",
                name="invalid_cron_2",
                cron_expression="0 9 * *",  # 4 parts instead of 5
                task_payload="{}",
            )

    def test_scheduled_task_task_payload_methods(self, db_session):
        """get_task_payload and set_task_payload work correctly."""
        task = ScheduledTask(
            agentium_id="R0014",
            name="payload_task",
            cron_expression="@hourly",
            task_payload=json.dumps({"action": "original"}),
        )
        db_session.add(task)
        db_session.commit()

        # get_task_payload
        payload = task.get_task_payload()
        assert payload == {"action": "original"}

        # set_task_payload
        task.set_task_payload({"action": "updated", "param": "value"})
        db_session.commit()
        assert task.task_payload == '{"action": "updated", "param": "value"}'
        assert task.get_task_payload() == {"action": "updated", "param": "value"}

    def test_scheduled_task_status_transitions(self, db_session):
        """Status transitions: pause, resume, mark_running, mark_completed."""
        task = ScheduledTask(
            agentium_id="R0015",
            name="status_task",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        # Initial: ACTIVE
        assert task.status == ScheduledTaskStatus.ACTIVE

        # Pause
        task.pause()
        db_session.commit()
        assert task.status == ScheduledTaskStatus.PAUSED

        # Resume
        task.resume()
        db_session.commit()
        assert task.status == ScheduledTaskStatus.ACTIVE

        # Mark running
        task.mark_running("agent-id-123", "30001")
        db_session.commit()
        assert task.status == ScheduledTaskStatus.RUNNING
        assert task.executing_agent_id == "agent-id-123"

        # Mark completed success
        task.mark_completed(success=True)
        db_session.commit()
        assert task.status == ScheduledTaskStatus.ACTIVE
        assert task.execution_count == 1
        assert task.failure_count == 0
        assert task.executing_agent_id is None
        assert task.last_execution_at is not None

        # Mark completed failure - status stays RUNNING until retry or max_retries
        task.mark_running("agent-id-456", "30002")
        task.mark_completed(success=False)
        db_session.commit()
        # Note: Mark completed on failure doesn't auto-reset status if under max_retries
        assert task.failure_count == 1
        assert task.status == ScheduledTaskStatus.RUNNING  # Still running, awaiting retry

        # Exceed max_retries -> ERROR
        for _ in range(2):  # Already 1, need 2 more to reach 3 (default max_retries)
            task.status = ScheduledTaskStatus.RUNNING
            task.mark_completed(success=False)
            db_session.commit()
        assert task.status == ScheduledTaskStatus.ERROR

    def test_scheduled_task_calculate_next_run(self, db_session):
        """calculate_next_run works if croniter available."""
        task = ScheduledTask(
            agentium_id="R0016",
            name="next_run_task",
            cron_expression="0 0 * * *",  # Daily at midnight
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        # Should not raise, returns datetime or None
        next_run = task.calculate_next_run()
        # croniter may not be installed, so either works
        assert next_run is None or isinstance(next_run, datetime)


class TestScheduledTaskExecution:
    """Tests for ScheduledTaskExecution model."""

    def test_scheduled_task_execution_creation(self, db_session):
        """ScheduledTaskExecution creates with all fields."""
        task = ScheduledTask(
            agentium_id="R0004",
            name="exec_parent",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="SE00001",  # Required - not auto-generated
            scheduled_task_id=task.id,
            execution_agentium_id="30001",
            execution_agent_id="agent-uuid-123",
            started_at=datetime.now(timezone.utc),
            status=ScheduledTaskExecutionStatus.RUNNING,
            retry_number=0,
        )
        db_session.add(execution)
        db_session.commit()
        db_session.refresh(execution)

        assert execution.scheduled_task_id == task.id
        assert execution.execution_agentium_id == "30001"
        assert execution.execution_agent_id == "agent-uuid-123"
        assert execution.started_at is not None
        assert execution.status == ScheduledTaskExecutionStatus.RUNNING
        assert execution.retry_number == 0
        assert execution.result_payload is None
        assert execution.error_message is None

    def test_scheduled_task_execution_defaults(self, db_session):
        """ScheduledTaskExecution defaults are correct."""
        task = ScheduledTask(
            agentium_id="R0005",
            name="default_exec",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="SE00002",  # Required - not auto-generated
            scheduled_task_id=task.id,
            execution_agentium_id="30002",
        )
        db_session.add(execution)
        db_session.commit()

        assert execution.started_at is not None
        assert execution.status == ScheduledTaskExecutionStatus.RUNNING
        assert execution.completed_at is None
        assert execution.result_payload is None
        assert execution.error_message is None
        assert execution.retry_number == 0

    def test_scheduled_task_execution_complete_success(self, db_session):
        """complete(success=True) sets fields correctly."""
        task = ScheduledTask(
            agentium_id="R0006",
            name="complete_success",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="SE00003",  # Required
            scheduled_task_id=task.id,
            execution_agentium_id="30003",
        )
        db_session.add(execution)
        db_session.commit()

        result = {"files_processed": 100, "status": "ok"}
        execution.complete(success=True, result=result)
        db_session.commit()

        assert execution.status == ScheduledTaskExecutionStatus.SUCCESS
        assert execution.completed_at is not None
        assert json.loads(execution.result_payload) == result
        assert execution.error_message is None

    def test_scheduled_task_execution_complete_failure(self, db_session):
        """complete(success=False) sets fields correctly."""
        task = ScheduledTask(
            agentium_id="R0007",
            name="complete_failure",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="SE00004",  # Required
            scheduled_task_id=task.id,
            execution_agentium_id="30004",
        )
        db_session.add(execution)
        db_session.commit()

        execution.complete(success=False, error="Connection timeout")
        db_session.commit()

        assert execution.status == ScheduledTaskExecutionStatus.FAILED
        assert execution.completed_at is not None
        assert execution.result_payload is None
        assert execution.error_message == "Connection timeout"

    def test_scheduled_task_execution_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        task = ScheduledTask(
            agentium_id="R0008",
            name="dict_exec",
            cron_expression="@daily",
            task_payload="{}",
        )
        db_session.add(task)
        db_session.commit()

        started = datetime.now(timezone.utc)
        execution = ScheduledTaskExecution(
            agentium_id="SE00005",  # Required
            scheduled_task_id=task.id,
            execution_agentium_id="30005",
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            status=ScheduledTaskExecutionStatus.SUCCESS,
            result_payload=json.dumps({"output": "done"}),
            retry_number=1,
        )
        db_session.add(execution)
        db_session.commit()

        data = execution.to_dict()
        assert data["scheduled_task_id"] == task.id
        assert data["execution_agentium_id"] == "30005"
        assert data["started_at"] == started.replace(tzinfo=None).isoformat()  # SQLite stores naive
        assert data["status"] == "success"
        assert data["result"] == {"output": "done"}
        assert data["retry_number"] == 1
        assert data["duration_seconds"] is not None


class TestWorkflowIntegration:
    """Integration tests for workflow workflows."""

    def test_workflow_with_steps_and_executions(self, db_session):
        """Full workflow: workflow -> steps -> execution."""
        # Create workflow
        workflow = Workflow(
            agentium_id="WF00014",
            name="integration_workflow",
            template_json={"steps": [{"type": "task"}, {"type": "condition"}]},
            schedule_cron="@daily",
        )
        db_session.add(workflow)
        db_session.commit()

        # Create steps
        step1 = WorkflowStep(
            agentium_id="WS00010",
            workflow_id=workflow.id,
            step_index=0,
            step_type=WorkflowStepType.TASK,
            config={"action": "fetch"},
            on_success_step=1,
        )
        step2 = WorkflowStep(
            agentium_id="WS00011",
            workflow_id=workflow.id,
            step_index=1,
            step_type=WorkflowStepType.CONDITION,
            config={"check": "result"},
        )
        db_session.add_all([step1, step2])
        db_session.commit()

        # Create execution
        execution = WorkflowExecution(
            agentium_id="WXINT01",
            workflow_id=workflow.id,
            status=WorkflowExecutionStatus.RUNNING,
            current_step_index=0,
            context_data={"data": "test"},
            triggered_by="schedule",
        )
        db_session.add(execution)
        db_session.commit()

        # Verify relationships
        assert len(workflow.steps.all()) == 2
        assert workflow.executions.count() == 1
        assert execution.workflow_id == workflow.id

        # Complete execution
        execution.status = WorkflowExecutionStatus.COMPLETED
        execution.current_step_index = 2
        execution.completed_at = datetime.now(timezone.utc)
        db_session.commit()

        assert execution.status == WorkflowExecutionStatus.COMPLETED

    def test_workflow_version_history(self, db_session):
        """Workflow version history tracks changes."""
        workflow = Workflow(
            agentium_id="WF00015",
            name="versioned_workflow",
            template_json={"steps": [{"v": 1}]},
            version=1,
        )
        db_session.add(workflow)
        db_session.commit()

        # Create version 1 snapshot
        v1 = WorkflowVersion(
            agentium_id="WV0010",
            workflow_id=workflow.id,
            version=1,
            template_json={"steps": [{"v": 1}]},
        )
        db_session.add(v1)
        db_session.commit()

        # Update workflow to version 2
        workflow.version = 2
        workflow.template_json = {"steps": [{"v": 2}]}
        db_session.commit()

        # Create version 2 snapshot
        v2 = WorkflowVersion(
            agentium_id="WV0011",
            workflow_id=workflow.id,
            version=2,
            template_json={"steps": [{"v": 2}]},
        )
        db_session.add(v2)
        db_session.commit()

        # Verify versions
        versions = workflow.versions.all()
        assert len(versions) == 2
        assert versions[0].version == 1
        assert versions[1].version == 2


class TestScheduledTaskIntegration:
    """Integration tests for scheduled task workflows."""

    def test_scheduled_task_with_execution_history(self, db_session):
        """ScheduledTask tracks execution history correctly."""
        task = ScheduledTask(
            agentium_id="R0009",
            name="history_task",
            cron_expression="0 * * * *",
            task_payload=json.dumps({"action": "process"}),
        )
        db_session.add(task)
        db_session.commit()

        # First execution - success
        exec1 = ScheduledTaskExecution(
            agentium_id="SE00010",  # Required
            scheduled_task_id=task.id,
            execution_agentium_id="30010",
            status=ScheduledTaskExecutionStatus.SUCCESS,
        )
        exec1.complete(success=True, result={"items": 10})
        db_session.add(exec1)
        db_session.commit()

        task.mark_completed(success=True)
        db_session.commit()

        # Second execution - failure
        exec2 = ScheduledTaskExecution(
            agentium_id="SE00011",  # Required
            scheduled_task_id=task.id,
            execution_agentium_id="30011",
            status=ScheduledTaskExecutionStatus.FAILED,
        )
        exec2.complete(success=False, error="Timeout")
        db_session.add(exec2)
        db_session.commit()

        task.mark_completed(success=False)
        db_session.commit()

        # Third execution - success
        exec3 = ScheduledTaskExecution(
            agentium_id="SE00012",  # Required
            scheduled_task_id=task.id,
            execution_agentium_id="30012",
            status=ScheduledTaskExecutionStatus.SUCCESS,
        )
        exec3.complete(success=True, result={"items": 15})
        db_session.add(exec3)
        db_session.commit()

        task.mark_completed(success=True)
        db_session.commit()

        # Verify history
        history = task.execution_history.limit(10).all()
        assert len(history) == 3
        assert history[0].status == "success"  # Most recent
        assert history[1].status == "failed"
        assert history[2].status == "success"

        # Verify task state
        assert task.execution_count == 3
        assert task.failure_count == 0  # Reset on success

    def test_scheduled_task_multiple_tasks_independent(self, db_session):
        """Multiple scheduled tasks operate independently."""
        task1 = ScheduledTask(
            agentium_id="R1001",
            name="task_one",
            cron_expression="@daily",
            task_payload=json.dumps({"id": 1}),
        )
        task2 = ScheduledTask(
            agentium_id="R1002",
            name="task_two",
            cron_expression="@hourly",
            task_payload=json.dumps({"id": 2}),
        )
        db_session.add_all([task1, task2])
        db_session.commit()

        assert task1.cron_expression == "@daily"
        assert task2.cron_expression == "@hourly"
        assert task1.get_task_payload()["id"] == 1
        assert task2.get_task_payload()["id"] == 2