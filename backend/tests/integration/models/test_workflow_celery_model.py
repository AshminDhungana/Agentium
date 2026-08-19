"""
Integration tests for Workflow, WorkflowExecution, ScheduledTask, and Celery integration models (3.3.7).
Verifies workflow templates, step execution lifecycle, scheduled tasks, and cron expressions.
"""
import pytest
import json
from datetime import datetime, timezone
from backend.models.entities.workflow import (
    Workflow, WorkflowExecution, WorkflowStep, WorkflowStepType, WorkflowExecutionStatus, WorkflowVersion
)
from backend.models.entities.scheduled_task import (
    ScheduledTask, ScheduledTaskExecution, ScheduledTaskStatus, ScheduledTaskExecutionStatus
)
from backend.models.entities.task import Task, TaskType, TaskStatus


def test_workflow_persist_with_template(db_session):
    """Verify Workflow model persists template_json, version, and cron schedule."""
    template = {
        "steps": [
            {"step_index": 0, "type": "task", "intent": "scrape_data"},
            {"step_index": 1, "type": "condition", "intent": "check_status"},
        ]
    }
    workflow = Workflow(
        agentium_id="WF10001",
        name="Data Scraper Pipeline",
        description="Automated scraping pipeline",
        template_json=template,
        version=1,
        schedule_cron="0 */4 * * *",
    )
    db_session.add(workflow)
    db_session.commit()

    fetched = db_session.query(Workflow).filter_by(agentium_id="WF10001").first()
    assert fetched is not None
    assert fetched.name == "Data Scraper Pipeline"
    assert fetched.template_json == template
    assert fetched.schedule_cron == "0 */4 * * *"

    d = fetched.to_dict()
    assert d["version"] == 1
    assert d["schedule_cron"] == "0 */4 * * *"


def test_workflow_execution_lifecycle(db_session, sample_workflow):
    """Verify WorkflowExecution status transitions and step tracking."""
    execution = WorkflowExecution(
        workflow_id=sample_workflow.id,
        status=WorkflowExecutionStatus.PENDING,
        context_data={"input_url": "https://example.com"},
        current_step_index=0,
    )
    db_session.add(execution)
    db_session.commit()

    assert execution.status == WorkflowExecutionStatus.PENDING

    # Transition to RUNNING
    execution.status = WorkflowExecutionStatus.RUNNING
    execution.started_at = datetime.utcnow()
    db_session.commit()

    fetched = db_session.query(WorkflowExecution).filter_by(id=execution.id).first()
    assert fetched.status == WorkflowExecutionStatus.RUNNING

    # Complete execution
    execution.status = WorkflowExecutionStatus.COMPLETED
    execution.completed_at = datetime.utcnow()
    execution.context_data = {"input_url": "https://example.com", "scraped_count": 42}
    db_session.commit()

    refetched = db_session.query(WorkflowExecution).filter_by(id=execution.id).first()
    assert refetched.status == WorkflowExecutionStatus.COMPLETED
    assert refetched.context_data["scraped_count"] == 42


def test_workflow_step_types(db_session, sample_workflow):
    """Verify all WorkflowStepType values round-trip."""
    for idx, step_type in enumerate(WorkflowStepType):
        step = WorkflowStep(
            agentium_id=f"WS{idx:05d}",
            workflow_id=sample_workflow.id,
            step_index=idx,
            step_type=step_type,
            config={"detail": f"config for {step_type.value}"},
        )
        db_session.add(step)
    db_session.commit()

    steps = db_session.query(WorkflowStep).filter_by(workflow_id=sample_workflow.id).all()
    assert len(steps) == len(WorkflowStepType)


def test_scheduled_task_persist_with_cron(db_session):
    """Verify ScheduledTask persists cron expression and calculates next run time."""
    st = ScheduledTask(
        agentium_id="R1001",
        name="Hourly Health Scan",
        cron_expression="0 * * * *",
        task_payload=json.dumps({"action": "health_scan"}),
        owner_agentium_id="00001",
        status=ScheduledTaskStatus.ACTIVE,
    )
    db_session.add(st)
    db_session.commit()

    fetched = db_session.query(ScheduledTask).filter_by(agentium_id="R1001").first()
    assert fetched is not None
    assert fetched.cron_expression == "0 * * * *"
    assert fetched.status == ScheduledTaskStatus.ACTIVE

    next_run = fetched.calculate_next_run()
    assert next_run is not None


def test_scheduled_task_cron_validation():
    """Verify cron_expression validator rejects invalid format."""
    st = ScheduledTask()

    with pytest.raises(ValueError, match="Cron expression must have 5 parts"):
        st.validate_cron("cron_expression", "0 * * *")  # 4 parts

    with pytest.raises(ValueError, match="Invalid special cron"):
        st.validate_cron("cron_expression", "@invalid_special")


def test_scheduled_task_execution_history(db_session, sample_scheduled_task, sample_task_agent):
    """Verify ScheduledTaskExecution records link via FK and relationship."""
    exec_record = ScheduledTaskExecution(
        agentium_id="SX10001",
        scheduled_task_id=sample_scheduled_task.id,
        execution_agentium_id=sample_task_agent.agentium_id,
        execution_agent_id=sample_task_agent.id,
        status=ScheduledTaskExecutionStatus.RUNNING,
        started_at=datetime.utcnow(),
    )
    db_session.add(exec_record)
    db_session.commit()

    exec_record.complete(success=True, result={"scanned_agents": 5})
    sample_scheduled_task.mark_completed(success=True)
    db_session.commit()

    db_session.refresh(sample_scheduled_task)
    assert sample_scheduled_task.execution_count == 1
    assert sample_scheduled_task.failure_count == 0
    assert sample_scheduled_task.status == ScheduledTaskStatus.ACTIVE

    history = sample_scheduled_task.execution_history.all()
    assert len(history) == 1
    assert history[0].status == ScheduledTaskExecutionStatus.SUCCESS
    assert history[0].result_payload == json.dumps({"scanned_agents": 5})


def test_workflow_celery_task_id_link(db_session, sample_workflow):
    """Verify Task model celery_task_id column links Celery async task IDs to Task entity."""
    task = Task(
        agentium_id="T80001",
        title="Celery Executed Task",
        description="Executing via Celery worker",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.IN_PROGRESS,
        celery_task_id="celery-task-uuid-999-888-777",
        workflow_id=sample_workflow.id,
        created_by="00001",
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(Task).filter_by(agentium_id="T80001").first()
    assert fetched is not None
    assert fetched.celery_task_id == "celery-task-uuid-999-888-777"
    assert fetched.workflow_id == sample_workflow.id
