"""Celery beat dispatcher for ScheduledTask rows.

Fires exactly-once per due, status-ACTIVE row every beat tick:

  1. Claim the row (optimistic CAS status ACTIVE -> RUNNING) so a second
     worker in a fleet cannot double-fire it.
  2. Build and enqueue exactly one regular Task via the shared
     ``create_and_dispatch_task`` helper (routes PENDING->APPROVED->
     IN_PROGRESS, then ``execute_task_async.delay``).
  3. ``mark_completed(True)`` on successful enqueue -> advances the cron
     schedule, or sets a one-time task to COMPLETED (retained done-record).
     ``mark_completed(False)`` on a build/enqueue failure -> ERROR after
     max_retries.

Ownership boundary: this module decides WHEN a scheduled task fires (exactly
once). The dispatched Task's eventual success/failure/retry is owned entirely
by the reused 10.1-10.3 TaskExecutor pipeline.
"""
import json
import logging
from datetime import datetime

from sqlalchemy import and_, or_, update

from backend.celery_app import celery_app
from backend.models.entities.audit import AuditCategory, AuditLevel, AuditLog
from backend.models.entities.scheduled_task import (
    ScheduledTask,
    ScheduledTaskExecution,
    ScheduledTaskExecutionStatus,
    ScheduledTaskStatus,
)
from backend.models.entities.task import Task, TaskPriority, TaskStatus, TaskType
from backend.services.scheduling.cron_due import utc_now

logger = logging.getLogger(__name__)


def _claim(row, db) -> bool:
    """Optimistic CAS claim: only the worker whose conditional UPDATE matches
    (rowcount == 1) wins the row; an already-RUNNING row is never double-fired."""
    stmt = (
        update(ScheduledTask)
        .where(
            ScheduledTask.id == row.id,
            ScheduledTask.status == ScheduledTaskStatus.ACTIVE,
        )
        .values(status=ScheduledTaskStatus.RUNNING)
    )
    return db.execute(stmt).rowcount == 1


def _allocate_task_id(db) -> str:
    """Allocate the next T##### id using the PASSED session (Postgres regex).
    Tests monkeypatch this to a fixed id so no second DB connection is opened."""
    from sqlalchemy import text

    row = db.execute(text(
        "SELECT agentium_id FROM tasks WHERE agentium_id ~ '^T[0-9]+$' "
        "ORDER BY CAST(SUBSTRING(agentium_id FROM 2) AS INTEGER) DESC LIMIT 1"
    )).scalar()
    return f"T{int(row[1:]) + 1:05d}" if row else "T00001"


def _submit_execution(task_id: str, agent_id: str) -> None:
    """Enqueue the task for the TaskExecutor worker. Monkeypatchable in tests."""
    from backend.services.tasks.task_executor import execute_task_async

    execute_task_async.delay(task_id, agent_id)


def create_and_dispatch_task(
    db,
    *,
    description: str,
    title: str = None,
    task_type=None,
    priority=None,
    execution_context=None,
    note_fragment: str = "scheduled",
    agent_id: str = "",
) -> Task:
    """Build a Task, route it through the legal state machine, enqueue it."""
    task_type = task_type or TaskType.EXECUTION
    priority = priority or TaskPriority.NORMAL
    # execution_context is a Text column; the codebase-wide convention is to
    # store a JSON string (see federation_service / e2e task tests), never a
    # Python dict — a raw dict fails to bind on both Postgres and SQLite.
    encoded_context = json.dumps(execution_context) if execution_context is not None else None
    task = Task(
        agentium_id=_allocate_task_id(db),
        title=title or description[:200],
        description=description,
        task_type=task_type,
        priority=priority,
        execution_context=encoded_context,
        created_by="SCHEDULER",
        sandbox_mode=True,
    )
    task.is_active = True
    db.add(task)
    db.flush()
    # Legal transition path (mirrors process_dependency_graph).
    task.set_status(TaskStatus.APPROVED, note=f"{note_fragment}: pre-dispatch approval")
    task.set_status(TaskStatus.IN_PROGRESS, note=f"{note_fragment}: advancing to executing")
    if task.started_at is None:
        task.started_at = datetime.utcnow()
    db.commit()
    _submit_execution(task.agentium_id, agent_id)
    return task


def _record_execution(db, row, success: bool, task_id: str = None, error: str = None) -> None:
    import uuid

    record = ScheduledTaskExecution(
        # agentium_id is NOT NULL on BaseEntity and not auto-populated here.
        agentium_id=f"SE{uuid.uuid4().int & 0xFFFFFF:06X}",
        scheduled_task_id=row.id,
        execution_agentium_id=row.executing_agent_id or row.owner_agentium_id,
        status=ScheduledTaskExecutionStatus.SUCCESS if success else ScheduledTaskExecutionStatus.FAILED,
    )
    record.complete(
        success=success,
        result={"task_id": task_id} if task_id else None,
        error=error,
    )
    db.add(record)


def _audit(db, row, *, action: str, level, description: str, after_state: dict) -> None:
    entry = AuditLog.log(
        level=level,
        category=AuditCategory.TASK,
        actor_type="system",
        actor_id="SCHEDULER",
        action=action,
        target_type="scheduled_task",
        target_id=row.id,
        description=description,
        after_state=after_state,
    )
    db.add(entry)


def _dispatch_one(db, row) -> None:
    """Claim-and-dispatch a single due row. Raises RuntimeError on enqueue failure."""
    if not _claim(row, db):
        return

    payload = row.get_task_payload() or {}
    task_type_raw = payload.get("task_type", "execution")
    try:
        task_type = TaskType(task_type_raw)
    except ValueError:
        task_type = TaskType.EXECUTION

    title = payload.get("title") or row.name
    description = payload.get("description") or f"Scheduled task: {row.name}"
    execution_context = {"scheduled_task_id": row.id, "params": payload.get("params", {})}

    try:
        new_task = create_and_dispatch_task(
            db,
            description=description,
            title=title,
            task_type=task_type,
            execution_context=execution_context,
            note_fragment=row.name,
            agent_id=row.executing_agent_id or "",
        )
    except RuntimeError as exc:
        row.mark_completed(success=False)
        _record_execution(db, row, success=False, error=str(exc))
        _audit(
            db, row,
            action="scheduled_task_failed",
            level=AuditLevel.CRITICAL,
            description=f"Scheduled task {row.agentium_id} failed to dispatch: {exc}",
            after_state={"task_id": row.agentium_id, "error": str(exc)},
        )
        db.commit()
        logger.error("dispatch failed for scheduled task %s: %s", row.agentium_id, exc)
        return

    row.mark_completed(success=True)
    _record_execution(db, row, success=True, task_id=new_task.agentium_id)
    _audit(
        db, row,
        action="scheduled_task_dispatched",
        level=AuditLevel.INFO,
        description=f"Scheduled task {row.agentium_id} dispatched task {new_task.agentium_id}",
        after_state={"scheduled_task_id": row.agentium_id, "task_id": new_task.agentium_id},
    )
    db.commit()


def _sweep(db) -> dict:
    """Sweep all due ACTIVE rows and dispatch each. Callable from tests without a broker."""
    now = utc_now()
    cron_due = and_(
        ScheduledTask.run_once.is_(False),
        ScheduledTask.next_execution_at.isnot(None),
        ScheduledTask.next_execution_at <= now,
    )
    once_due = and_(
        ScheduledTask.run_once.is_(True),
        ScheduledTask.run_at.isnot(None),
        ScheduledTask.run_at <= now,
    )
    due = (
        db.query(ScheduledTask)
        .filter(ScheduledTask.status == ScheduledTaskStatus.ACTIVE, or_(cron_due, once_due))
        .all()
    )
    results = {"checked": len(due), "dispatched": 0, "skipped": 0, "errors": 0}

    for row in due:
        try:
            _dispatch_one(db, row)
            results["dispatched"] += 1
        except Exception as exc:  # one bad row never aborts the sweep
            results["errors"] += 1
            logger.error("sweep error for %s: %s", row.agentium_id, exc, exc_info=True)

    db.commit()
    return results


@celery_app.task(name="agentium.tasks.task_executor.dispatch_due_scheduled_tasks")
def dispatch_due_scheduled_tasks():
    """Beat entry (every 15s): dispatch all due scheduled tasks exactly once."""
    from backend.services.tasks.task_executor import get_task_db

    with get_task_db() as db:
        try:
            return _sweep(db)
        except Exception as exc:
            logger.error("dispatch_due_scheduled_tasks failed: %s", exc)
            return {"error": str(exc)}