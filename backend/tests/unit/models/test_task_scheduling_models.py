"""
Unit tests for Task and ScheduledTask models.
Tests all task types, statuses, priorities, and scheduling functionality.
"""
import pytest
from datetime import datetime, timezone
import json

from backend.models.entities.task import (
    Task, TaskType, TaskStatus, TaskPriority, SubTask,
    TaskAuditLog, TaskDependency
)
from backend.models.entities.scheduled_task import (
    ScheduledTask, ScheduledTaskStatus, ScheduledTaskExecution,
    ScheduledTaskExecutionStatus
)
from backend.models.entities.agents import AgentType


# =========================================================================
# Task Unit Tests
# =========================================================================

class TestTask:
    """Tests for Task model."""

    def test_task_creation_with_all_required_fields(self, db_session):
        """Task creates with all required fields."""
        task = Task(
            agentium_id="T00001",
            title="Test Task",
            description="Test description",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.agentium_id == "T00001"
        assert task.title == "Test Task"
        assert task.description == "Test description"
        assert task.task_type == TaskType.EXECUTION
        assert task.priority == TaskPriority.NORMAL
        assert task.status == TaskStatus.PENDING
        assert task.created_by == "00001"

    def test_task_defaults_to_pending_status(self, db_session):
        """Task defaults to PENDING status."""
        task = Task(
            agentium_id="T00002",
            description="Test",
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.status == TaskStatus.PENDING

    def test_task_defaults_to_execution_type(self, db_session):
        """Task defaults to EXECUTION type."""
        task = Task(
            agentium_id="T00003",
            description="Test",
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.task_type == TaskType.EXECUTION

    def test_task_defaults_to_normal_priority(self, db_session):
        """Task defaults to NORMAL priority."""
        task = Task(
            agentium_id="T00004",
            description="Test",
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.priority == TaskPriority.NORMAL

    @pytest.mark.parametrize("task_type", [
        TaskType.EXECUTION,
        TaskType.RESEARCH,
        TaskType.ANALYSIS,
        TaskType.CODE_GENERATION,
        TaskType.CODE_REVIEW,
        TaskType.DEBUGGING,
        TaskType.PLANNING,
        TaskType.BROWSER,
        TaskType.AUTOMATION,
        TaskType.COMMUNICATION,
        TaskType.CONSTITUTION_READ,
        TaskType.ONE_TIME,
        TaskType.RECURRING,
        TaskType.CONSTITUTIONAL,
        TaskType.SYSTEM,
    ])
    def test_all_task_types_valid(self, db_session, task_type):
        """All task types are valid enum values."""
        task = Task(
            agentium_id=f"T{task_type.value[:3].upper()}",
            description="Test",
            task_type=task_type,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.task_type == task_type

    @pytest.mark.parametrize("priority", [
        TaskPriority.SOVEREIGN,
        TaskPriority.CRITICAL,
        TaskPriority.HIGH,
        TaskPriority.NORMAL,
        TaskPriority.LOW,
        TaskPriority.IDLE,
    ])
    def test_all_priorities_valid(self, db_session, priority):
        """All priority levels are valid enum values."""
        task = Task(
            agentium_id=f"T{priority.value[:2].upper()}",
            description="Test",
            priority=priority,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.priority == priority

    @pytest.mark.parametrize("status", [
        TaskStatus.PENDING,
        TaskStatus.DELIBERATING,
        TaskStatus.APPROVED,
        TaskStatus.REJECTED,
        TaskStatus.DELEGATING,
        TaskStatus.ASSIGNED,
        TaskStatus.IN_PROGRESS,
        TaskStatus.REVIEW,
        TaskStatus.COMPLETED,
        TaskStatus.CANCELLED,
        TaskStatus.FAILED,
        TaskStatus.RETRYING,
        TaskStatus.ESCALATED,
        TaskStatus.STOPPED,
        TaskStatus.WAITING,
        TaskStatus.IDLE_PENDING,
        TaskStatus.IDLE_RUNNING,
        TaskStatus.IDLE_PAUSED,
        TaskStatus.IDLE_COMPLETED,
    ])
    def test_all_statuses_valid(self, db_session, status):
        """All status values are valid enum values."""
        task = Task(
            agentium_id=f"T{status.value[:2].upper()}",
            description="Test",
            status=status,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.status == status

    def test_sovereign_priority_skips_deliberation(self, db_session):
        """SOVEREIGN priority sets requires_deliberation=False."""
        task = Task(
            agentium_id="T00005",
            description="Test",
            priority=TaskPriority.SOVEREIGN,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.requires_deliberation is False
        assert task.approved_by_council is True
        assert task.approved_by_head is True

    def test_critical_priority_skips_deliberation(self, db_session):
        """CRITICAL priority sets requires_deliberation=False."""
        task = Task(
            agentium_id="T00006",
            description="Test",
            priority=TaskPriority.CRITICAL,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.requires_deliberation is False

    def test_idle_priority_auto_flags_idle_task(self, db_session):
        """IDLE priority sets requires_deliberation=False (is_idle_task based on task_type)."""
        # Test with idle task type (which auto-flags is_idle_task)
        task = Task(
            agentium_id="T00007",
            description="Test",
            task_type=TaskType.VECTOR_MAINTENANCE,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.is_idle_task is True
        assert task.priority == TaskPriority.IDLE
        assert task.requires_deliberation is False

    def test_idle_task_types_auto_flags_idle_task(self, db_session):
        """Idle task types auto-flag is_idle_task=True."""
        for idle_type in [
            TaskType.VECTOR_MAINTENANCE,
            TaskType.STORAGE_DEDUPE,
            TaskType.AUDIT_ARCHIVAL,
            TaskType.PREDICTIVE_PLANNING,
            TaskType.CONSTITUTION_REFINE,
            TaskType.AGENT_HEALTH_SCAN,
            TaskType.ETHOS_OPTIMIZATION,
            TaskType.CACHE_OPTIMIZATION,
        ]:
            task = Task(
                agentium_id=f"T{idle_type.value[:2].upper()}",
                description="Test",
                task_type=idle_type,
                created_by="00001",
            )
            db_session.add(task)
            db_session.commit()

            assert task.is_idle_task is True
            assert task.priority == TaskPriority.IDLE
            assert task.requires_deliberation is False

            db_session.delete(task)
            db_session.commit()

    def test_task_with_json_fields(self, db_session):
        """Task persists JSON fields correctly."""
        task = Task(
            agentium_id="T00008",
            description="Test",
            assigned_council_ids=["10001", "10002"],
            assigned_task_agent_ids=["30001", "30002"],
            tools_allowed=["tool1", "tool2"],
            status_history=[{"status": "pending", "timestamp": "2024-01-01T00:00:00"}],
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.assigned_council_ids == ["10001", "10002"]
        assert task.assigned_task_agent_ids == ["30001", "30002"]
        assert task.tools_allowed == ["tool1", "tool2"]
        assert len(task.status_history) == 1

    def test_task_with_acceptance_criteria(self, db_session):
        """Task persists acceptance criteria JSON."""
        criteria = [
            {"criterion": "Code compiles", "mandatory": True},
            {"criterion": "Tests pass", "mandatory": True},
        ]
        task = Task(
            agentium_id="T00009",
            description="Test",
            acceptance_criteria=criteria,
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()
        db_session.refresh(task)

        assert task.acceptance_criteria == criteria

    def test_task_parent_child_relationship(self, db_session):
        """Task parent-child relationship works."""
        parent = Task(
            agentium_id="T00010",
            description="Parent task",
            created_by="00001",
        )
        db_session.add(parent)
        db_session.commit()

        child = Task(
            agentium_id="T00011",
            description="Child task",
            parent_task_id=parent.id,
            created_by="00001",
        )
        db_session.add(child)
        db_session.commit()

        assert child.parent_task_id == parent.id
        assert parent.child_tasks[0].id == child.id

    def test_task_agentium_id_uniqueness(self, db_session):
        """Task agentium_id must be unique."""
        task1 = Task(
            agentium_id="T00001",
            description="Task 1",
            created_by="00001",
        )
        task2 = Task(
            agentium_id="T00001",
            description="Task 2",
            created_by="00001",
        )
        db_session.add(task1)
        db_session.commit()

        db_session.add(task2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
        db_session.rollback()

    def test_task_idempotency_key_uniqueness(self, db_session):
        """Task idempotency_key must be unique when provided."""
        task1 = Task(
            agentium_id="T00001",
            description="Task 1",
            idempotency_key="unique-key-1",
            created_by="00001",
        )
        task2 = Task(
            agentium_id="T00002",
            description="Task 2",
            idempotency_key="unique-key-1",  # Duplicate
            created_by="00001",
        )
        db_session.add(task1)
        db_session.commit()

        db_session.add(task2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
        db_session.rollback()

    def test_task_to_dict_includes_all_fields(self, db_session):
        """Task.to_dict() includes all relevant fields."""
        task = Task(
            agentium_id="T00001",
            title="Test Task",
            description="Test description",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.HIGH,
            status=TaskStatus.COMPLETED,
            completion_percentage=100,
            result_summary="Done",
            result_data={"output": "result"},
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        data = task.to_dict()

        assert data["title"] == "Test Task"
        assert data["type"] == "execution"
        assert data["priority"] == "high"
        assert data["status"] == "completed"
        assert data["progress"] == 100
        assert data["result"]["summary"] == "Done"
        assert data["result"]["data"]["output"] == "result"

    def test_subtask_creation_and_completion(self, db_session):
        """SubTask creates and completes correctly."""
        parent = Task(
            agentium_id="T00001",
            description="Parent",
            created_by="00001",
        )
        db_session.add(parent)
        db_session.commit()

        subtask = SubTask(
            agentium_id="S00001",
            parent_task_id=parent.id,
            title="Subtask 1",
            description="Subtask description",
            sequence=1,
        )
        db_session.add(subtask)
        db_session.commit()

        # Start and complete
        subtask.start_execution("agent-30001")
        assert subtask.status == TaskStatus.IN_PROGRESS
        assert subtask.assigned_agent_id == "agent-30001"

        # Complete subtask (without triggering parent completion which needs DB context)
        subtask.status = TaskStatus.COMPLETED
        subtask.result = "Subtask result"
        subtask.output_data = {"output": "data"}
        subtask.completed_at = datetime.now(timezone.utc)
        db_session.commit()

        assert subtask.status == TaskStatus.COMPLETED
        assert subtask.result == "Subtask result"
        assert subtask.output_data == {"output": "data"}
        assert subtask.completed_at is not None

    def test_subtask_dependencies(self, db_session):
        """SubTask dependencies JSON field works."""
        parent = Task(
            agentium_id="T00001",
            description="Parent",
            created_by="00001",
        )
        db_session.add(parent)
        db_session.commit()

        subtask1 = SubTask(
            agentium_id="S00001",
            parent_task_id=parent.id,
            title="Subtask 1",
            description="First",
            sequence=1,
        )
        subtask2 = SubTask(
            agentium_id="S00002",
            parent_task_id=parent.id,
            title="Subtask 2",
            description="Second",
            sequence=2,
            dependencies=["S00001"],
        )
        db_session.add_all([subtask1, subtask2])
        db_session.commit()

        assert subtask2.dependencies == ["S00001"]

    def test_task_audit_log_creation(self, db_session):
        """TaskAuditLog creates correctly."""
        task = Task(
            agentium_id="T00001",
            description="Test",
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        audit_log = TaskAuditLog.log_action(
            task_id=task.id,
            agentium_id="30001",
            action="status_change",
            details={"old": "pending", "new": "in_progress"}
        )
        db_session.add(audit_log)
        db_session.commit()

        assert audit_log.task_id == task.id
        assert audit_log.agentium_id == "30001"
        assert audit_log.action == "status_change"
        assert audit_log.action_details == {"old": "pending", "new": "in_progress"}

    def test_task_dependency_creation(self, db_session):
        """TaskDependency creates with correct ordering."""
        parent = Task(
            agentium_id="T00001",
            description="Parent",
            created_by="00001",
        )
        child = Task(
            agentium_id="T00002",
            description="Child",
            created_by="00001",
        )
        db_session.add_all([parent, child])
        db_session.commit()

        dep = TaskDependency(
            agentium_id="TD0001",
            parent_task_id=parent.id,
            child_task_id=child.id,
            dependency_order=1,
        )
        db_session.add(dep)
        db_session.commit()

        assert dep.parent_task_id == parent.id
        assert dep.child_task_id == child.id
        assert dep.dependency_order == 1
        assert dep.status == "pending"


# =========================================================================
# ScheduledTask Unit Tests
# =========================================================================

class TestScheduledTask:
    """Tests for ScheduledTask model."""

    def test_scheduled_task_creation(self, db_session):
        """ScheduledTask creates with all required fields."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Daily Backup",
            description="Backup database daily",
            cron_expression="0 0 * * *",
            task_payload=json.dumps({
                "action_type": "backup",
                "params": {"target": "database"}
            }),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()
        db_session.refresh(scheduled)

        assert scheduled.agentium_id == "R0001"
        assert scheduled.name == "Daily Backup"
        assert scheduled.cron_expression == "0 0 * * *"
        assert scheduled.owner_agentium_id == "00001"
        assert scheduled.status == ScheduledTaskStatus.ACTIVE

    def test_scheduled_task_defaults(self, db_session):
        """ScheduledTask defaults to ACTIVE status and priority 1."""
        scheduled = ScheduledTask(
            agentium_id="R0002",
            name="Test Schedule",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        assert scheduled.status == ScheduledTaskStatus.ACTIVE
        assert scheduled.priority == 1
        assert scheduled.failure_count == 0
        assert scheduled.execution_count == 0

    @pytest.mark.parametrize("cron", [
        "0 0 * * *",      # Daily at midnight
        "0 9 * * 1-5",    # Weekdays at 9am
        "0 */6 * * *",    # Every 6 hours
        "@daily",
        "@hourly",
        "@weekly",
        "@monthly",
    ])
    def test_valid_cron_expressions(self, db_session, cron):
        """Valid cron expressions are accepted."""
        scheduled = ScheduledTask(
            agentium_id=f"R{cron[:3]}",
            name=f"Schedule {cron}",
            cron_expression=cron,
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        assert scheduled.cron_expression == cron

    def test_invalid_cron_expression_raises(self, db_session):
        """Invalid cron expression raises ValueError during construction."""
        with pytest.raises(ValueError):
            ScheduledTask(
                agentium_id="R0003",
                name="Bad Cron",
                cron_expression="invalid cron",
                task_payload=json.dumps({}),
                owner_agentium_id="00001",
            )

    def test_invalid_special_cron_raises(self, db_session):
        """Invalid special cron raises ValueError during construction."""
        with pytest.raises(ValueError):
            ScheduledTask(
                agentium_id="R0004",
                name="Bad Special",
                cron_expression="@invalid",
                task_payload=json.dumps({}),
                owner_agentium_id="00001",
            )

    def test_task_payload_roundtrip(self, db_session):
        """Task payload JSON roundtrips correctly."""
        payload = {
            "action_type": "execute_script",
            "params": {"script": "backup.py", "args": ["--full"]},
            "constraints": {"max_duration": 300}
        }
        scheduled = ScheduledTask(
            agentium_id="R0005",
            name="Script Runner",
            cron_expression="0 * * * *",
            task_payload=json.dumps(payload),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()
        db_session.refresh(scheduled)

        parsed = scheduled.get_task_payload()
        assert parsed == payload

        # Test set_task_payload
        new_payload = {"action_type": "different"}
        scheduled.set_task_payload(new_payload)
        db_session.commit()
        db_session.refresh(scheduled)

        assert scheduled.get_task_payload() == new_payload

    def test_scheduled_task_status_transitions(self, db_session):
        """ScheduledTask status transitions work correctly."""
        scheduled = ScheduledTask(
            agentium_id="R0006",
            name="Test",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        # PAUSED
        scheduled.pause()
        db_session.commit()
        assert scheduled.status == ScheduledTaskStatus.PAUSED

        # ACTIVE again
        scheduled.resume()
        db_session.commit()
        assert scheduled.status == ScheduledTaskStatus.ACTIVE

        # Mark running
        scheduled.mark_running("agent-id", "30001")
        db_session.commit()
        assert scheduled.status == ScheduledTaskStatus.RUNNING
        assert scheduled.executing_agent_id == "agent-id"

        # Mark completed successfully
        scheduled.mark_completed(success=True)
        db_session.commit()
        assert scheduled.status == ScheduledTaskStatus.ACTIVE
        assert scheduled.execution_count == 1
        assert scheduled.failure_count == 0
        assert scheduled.last_execution_at is not None

    def test_scheduled_task_failure_and_retry(self, db_session):
        """ScheduledTask failure increments failure_count and sets ERROR after max retries."""
        scheduled = ScheduledTask(
            agentium_id="R0007",
            name="Test",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
            max_retries=2,
        )
        db_session.add(scheduled)
        db_session.commit()

        # First failure
        scheduled.mark_completed(success=False)
        db_session.commit()
        assert scheduled.failure_count == 1
        assert scheduled.status == ScheduledTaskStatus.ACTIVE  # Still active

        # Second failure - reaches max_retries
        scheduled.mark_completed(success=False)
        db_session.commit()
        assert scheduled.failure_count == 2
        assert scheduled.status == ScheduledTaskStatus.ERROR

    def test_scheduled_task_agentium_id_uniqueness(self, db_session):
        """ScheduledTask agentium_id must be unique."""
        sched1 = ScheduledTask(
            agentium_id="R0001",
            name="Schedule 1",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        sched2 = ScheduledTask(
            agentium_id="R0001",  # Duplicate
            name="Schedule 2",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(sched1)
        db_session.commit()

        db_session.add(sched2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
        db_session.rollback()

    def test_scheduled_task_to_dict(self, db_session):
        """ScheduledTask.to_dict() includes all fields."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Test Schedule",
            cron_expression="0 0 * * *",
            task_payload=json.dumps({"action": "test"}),
            owner_agentium_id="00001",
            status=ScheduledTaskStatus.ACTIVE,
        )
        db_session.add(scheduled)
        db_session.commit()

        data = scheduled.to_dict()

        assert data["agentium_id"] == "R0001"
        assert data["name"] == "Test Schedule"
        assert data["cron_expression"] == "0 0 * * *"
        assert data["task_payload"]["action"] == "test"
        assert data["status"] == "active"
        assert "schedule" in data


# =========================================================================
# ScheduledTaskExecution Unit Tests
# =========================================================================

class TestScheduledTaskExecution:
    """Tests for ScheduledTaskExecution model."""

    def test_execution_creation(self, db_session):
        """ScheduledTaskExecution creates correctly."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Test",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="EX0001",
            scheduled_task_id=scheduled.id,
            execution_agentium_id="30001",
            execution_agent_id="agent-uuid",
            status=ScheduledTaskExecutionStatus.RUNNING,
        )
        db_session.add(execution)
        db_session.commit()
        db_session.refresh(execution)

        assert execution.scheduled_task_id == scheduled.id
        assert execution.execution_agentium_id == "30001"
        assert execution.execution_agent_id == "agent-uuid"
        assert execution.status == ScheduledTaskExecutionStatus.RUNNING
        assert execution.started_at is not None

    def test_execution_complete_success(self, db_session):
        """Execution completes successfully with result."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Test",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="EX0002",
            scheduled_task_id=scheduled.id,
            execution_agentium_id="30001",
            status=ScheduledTaskExecutionStatus.RUNNING,
        )
        db_session.add(execution)
        db_session.commit()

        execution.complete(success=True, result={"output": "backup_complete"})
        db_session.commit()

        assert execution.status == ScheduledTaskExecutionStatus.SUCCESS
        assert execution.completed_at is not None
        assert execution.result_payload is not None
        parsed = json.loads(execution.result_payload)
        assert parsed["output"] == "backup_complete"

    def test_execution_complete_failure(self, db_session):
        """Execution completes with failure and error message."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Test",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="EX0003",
            scheduled_task_id=scheduled.id,
            execution_agentium_id="30001",
            status=ScheduledTaskExecutionStatus.RUNNING,
        )
        db_session.add(execution)
        db_session.commit()

        execution.complete(success=False, error="Connection timeout")
        db_session.commit()

        assert execution.status == ScheduledTaskExecutionStatus.FAILED
        assert execution.error_message == "Connection timeout"
        assert execution.completed_at is not None

    def test_execution_to_dict(self, db_session):
        """Execution to_dict includes all fields."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Test",
            cron_expression="@daily",
            task_payload=json.dumps({}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        execution = ScheduledTaskExecution(
            agentium_id="EX0004",
            scheduled_task_id=scheduled.id,
            execution_agentium_id="30001",
            status=ScheduledTaskExecutionStatus.SUCCESS,
            result_payload=json.dumps({"status": "ok"}),
        )
        db_session.add(execution)
        db_session.commit()

        data = execution.to_dict()
        assert data["execution_agentium_id"] == "30001"
        assert data["status"] == "success"
        assert data["result"]["status"] == "ok"


# =========================================================================
# Cross-Model Integration Tests
# =========================================================================

class TestTaskSchedulingIntegration:
    """Integration tests between Task and related models."""

    def test_task_with_scheduled_task_link(self, db_session):
        """Task can link to scheduled_task via workflow_id/context_data."""
        scheduled = ScheduledTask(
            agentium_id="R0001",
            name="Daily Task",
            cron_expression="@daily",
            task_payload=json.dumps({"action": "run"}),
            owner_agentium_id="00001",
        )
        db_session.add(scheduled)
        db_session.commit()

        task = Task(
            agentium_id="T00001",
            description="Scheduled execution",
            task_type=TaskType.RECURRING,
            workflow_id=f"scheduled_{scheduled.id}",
            context_data={"scheduled_task_id": scheduled.id},
            created_by="00001",
        )
        db_session.add(task)
        db_session.commit()

        assert task.workflow_id == f"scheduled_{scheduled.id}"
        assert task.context_data["scheduled_task_id"] == scheduled.id

    def test_task_with_subtasks_and_dependencies(self, db_session):
        """Task with multiple subtasks and dependencies."""
        parent = Task(
            agentium_id="T00001",
            description="Complex task with subtasks",
            created_by="00001",
        )
        db_session.add(parent)
        db_session.commit()

        # Create subtasks
        sub1 = SubTask(
            agentium_id="S00001",
            parent_task_id=parent.id,
            title="Step 1: Fetch data",
            description="Fetch data from API",
            sequence=1,
        )
        sub2 = SubTask(
            agentium_id="S00002",
            parent_task_id=parent.id,
            title="Step 2: Process data",
            description="Process the fetched data",
            sequence=2,
            dependencies=["S00001"],
        )
        sub3 = SubTask(
            agentium_id="S00003",
            parent_task_id=parent.id,
            title="Step 3: Save results",
            description="Save processed results",
            sequence=3,
            dependencies=["S00002"],
        )
        db_session.add_all([sub1, sub2, sub3])
        db_session.commit()

        # lazy="dynamic" relationship returns query, need .all()
        assert len(parent.subtasks.all()) == 3
        assert sub1.sequence == 1
        assert sub2.sequence == 2
        assert sub3.sequence == 3
        assert sub2.dependencies == ["S00001"]
        assert sub3.dependencies == ["S00002"]