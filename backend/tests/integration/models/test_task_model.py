"""
Integration tests for Task model (3.3.2).
Verifies all task types, priorities, statuses, auto-flagging logic, and parent-child hierarchy.
"""
import pytest
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority


def test_task_all_statuses_persist(db_session):
    """Verify all TaskStatus values round-trip through DB."""
    for idx, status in enumerate(TaskStatus):
        task = Task(
            agentium_id=f"T100{idx:02d}",
            title=f"Task Status {status.value}",
            description="Testing task status persistence",
            task_type=TaskType.EXECUTION,
            status=status,
            created_by="00001",
        )
        db_session.add(task)
    db_session.commit()

    for idx, status in enumerate(TaskStatus):
        fetched = db_session.query(Task).filter_by(agentium_id=f"T100{idx:02d}").first()
        assert fetched is not None
        assert fetched.status == status


def test_task_all_types_persist(db_session):
    """Verify key TaskType values round-trip through DB."""
    sample_types = [
        TaskType.CONSTITUTIONAL,
        TaskType.SYSTEM,
        TaskType.ONE_TIME,
        TaskType.RECURRING,
        TaskType.EXECUTION,
        TaskType.RESEARCH,
        TaskType.AUTOMATION,
        TaskType.BROWSER,
        TaskType.ANALYSIS,
        TaskType.CODE_GENERATION,
        TaskType.VECTOR_MAINTENANCE,
        TaskType.STORAGE_DEDUPE,
    ]
    for idx, task_type in enumerate(sample_types):
        task = Task(
            agentium_id=f"T200{idx:02d}",
            title=f"Task Type {task_type.value}",
            description="Testing task type persistence",
            task_type=task_type,
            created_by="00001",
        )
        db_session.add(task)
    db_session.commit()

    for idx, task_type in enumerate(sample_types):
        fetched = db_session.query(Task).filter_by(agentium_id=f"T200{idx:02d}").first()
        assert fetched is not None
        assert fetched.task_type == task_type


def test_task_priorities_persist(db_session):
    """Verify all TaskPriority levels round-trip through DB."""
    for idx, priority in enumerate(TaskPriority):
        task = Task(
            agentium_id=f"T300{idx:02d}",
            title=f"Task Priority {priority.value}",
            description="Testing task priority persistence",
            task_type=TaskType.EXECUTION,
            priority=priority,
            created_by="00001",
        )
        db_session.add(task)
    db_session.commit()

    for idx, priority in enumerate(TaskPriority):
        fetched = db_session.query(Task).filter_by(agentium_id=f"T300{idx:02d}").first()
        assert fetched is not None
        assert fetched.priority == priority


def test_task_idle_auto_flagging(db_session):
    """Verify idle task types automatically set is_idle_task=True, priority=IDLE, and requires_deliberation=False."""
    task = Task(
        agentium_id="T40001",
        description="Run vector maintenance",
        task_type=TaskType.VECTOR_MAINTENANCE,
        created_by="00001",
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(Task).filter_by(agentium_id="T40001").first()
    assert fetched.is_idle_task is True
    assert fetched.priority == TaskPriority.IDLE
    assert fetched.requires_deliberation is False


def test_task_sovereign_priority_skips_governance(db_session):
    """Verify SOVEREIGN priority task automatically sets requires_deliberation=False."""
    task = Task(
        agentium_id="T50001",
        title="Emergency Sovereign Task",
        description="Direct sovereign command",
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.SOVEREIGN,
        created_by="sovereign",
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(Task).filter_by(agentium_id="T50001").first()
    assert fetched.priority == TaskPriority.SOVEREIGN
    assert fetched.requires_deliberation is False


def test_task_parent_child_structure(db_session):
    """Verify parent_task_id FK and child_tasks / subtasks backrefs work."""
    parent = Task(
        agentium_id="T60001",
        title="Parent Goal",
        description="High level goal",
        task_type=TaskType.PLANNING,
        created_by="00001",
    )
    db_session.add(parent)
    db_session.commit()

    child1 = Task(
        agentium_id="T60002",
        title="Subgoal 1",
        description="First subtask",
        task_type=TaskType.EXECUTION,
        parent_task_id=parent.id,
        created_by="00001",
    )
    child2 = Task(
        agentium_id="T60003",
        title="Subgoal 2",
        description="Second subtask",
        task_type=TaskType.RESEARCH,
        parent_task_id=parent.id,
        created_by="00001",
    )
    db_session.add_all([child1, child2])
    db_session.commit()

    db_session.refresh(parent)
    assert len(parent.child_tasks) == 2
    assert child1.parent_task.id == parent.id
    assert child2.parent_task.id == parent.id


def test_task_status_history_appended(db_session):
    """Verify JSON status_history field stores state transitions."""
    task = Task(
        agentium_id="T70001",
        title="Status History Task",
        description="Testing status history updates",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.PENDING,
        status_history=[{"from": None, "to": "pending", "reason": "created"}],
        created_by="00001",
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(Task).filter_by(agentium_id="T70001").first()
    assert len(fetched.status_history) == 1

    # Update status and append history entry
    history = list(fetched.status_history)
    history.append({"from": "pending", "to": "in_progress", "reason": "assigned to worker"})
    fetched.status = TaskStatus.IN_PROGRESS
    fetched.status_history = history
    db_session.commit()

    refetched = db_session.query(Task).filter_by(agentium_id="T70001").first()
    assert refetched.status == TaskStatus.IN_PROGRESS
    assert len(refetched.status_history) == 2
    assert refetched.status_history[1]["to"] == "in_progress"
