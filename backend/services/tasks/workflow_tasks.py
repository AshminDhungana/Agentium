"""
Celery tasks for the workflow engine.

  fire_reminder            — surface a deferred reminder notification
  execute_deferred_subtask — run a scheduled workflow sub-task after its countdown

Both tasks create their own DB sessions (NullPool) so they work safely inside
the Celery worker process, independent of FastAPI's request-scoped sessions.
"""
import asyncio
import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from backend.celery_app import celery_app

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared helper — build a throw-away DB session inside a worker
# ---------------------------------------------------------------------------

def _make_session():
    """Make session."""

    url = os.getenv(
        "DATABASE_URL",
        "postgresql://agentium:agentium@postgres:5432/agentium",
    )
    engine = create_engine(url, poolclass=NullPool, pool_pre_ping=True)
    return sessionmaker(bind=engine)()


# ---------------------------------------------------------------------------
# Task: fire_reminder
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="agentium.tasks.workflow_tasks.fire_reminder",
)
def fire_reminder(self, message: str, workflow_id: str = None):
    """
    Surface a reminder by injecting an ExternalMessage into the first active
    channel.  If no channel is available the reminder is logged only — the
    task still succeeds so the workflow record is not left in a failed state.
    """
    db = _make_session()
    try:
        from backend.models.entities.channels import (
            ExternalChannel, ExternalMessage, ChannelStatus,
        )

        channel = (
            db.query(ExternalChannel)
            .filter(ExternalChannel.status == ChannelStatus.ACTIVE)
            .first()
        )

        if channel:
            notif = ExternalMessage(
                channel_id=channel.id,
                sender_id="system",
                sender_name="Agentium Scheduler",
                content=f"🔔 Reminder: {message}",
                status="received",
            )
            db.add(notif)
            db.commit()
            logger.info(
                f"[fire_reminder] Delivered via channel {channel.id}: "
                f"{message[:60]}"
            )
        else:
            logger.warning(
                f"[fire_reminder] No active channel — reminder logged only: "
                f"{message[:60]}"
            )

        return {"fired": True, "message": message, "workflow_id": workflow_id}

    except Exception as exc:
        db.rollback()
        logger.error(f"[fire_reminder] Error: {exc}")
        raise self.retry(exc=exc)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Task: execute_deferred_subtask
# ---------------------------------------------------------------------------

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=120,
    name="agentium.tasks.workflow_tasks.execute_deferred_subtask",
)
def execute_deferred_subtask(
    self, workflow_id: str, intent: str, params: dict
):
    """
    Execute a workflow sub-task that was deferred (e.g. 2-week follow-up).
    Runs the tool synchronously in a fresh event loop inside the worker,
    then updates the WorkflowSubTask record.
    """
    from datetime import datetime
    import backend.services.workflow_tools as workflow_tools

    logger.info(
        f"[execute_deferred_subtask] Running '{intent}' "
        f"for workflow {workflow_id}"
    )

    # Run the async tool in a dedicated event loop
    loop = asyncio.new_event_loop()
    try:
        result = loop.run_until_complete(
            workflow_tools.execute(intent, params, context={})
        )
    except Exception as exc:
        logger.error(f"[execute_deferred_subtask] Tool '{intent}' failed: {exc}")
        raise self.retry(exc=exc)
    finally:
        loop.close()

    # Persist result
    db = _make_session()
    try:
        from backend.models.entities.workflow import WorkflowSubTask, WorkflowExecution

        sub = db.query(WorkflowSubTask).filter_by(
            workflow_id=workflow_id, intent=intent
        ).first()
        if sub:
            sub.status = "completed"
            sub.result = result
            sub.completed_at = datetime.utcnow()
            db.commit()

        # Refresh workflow context_data
        wf = db.query(WorkflowExecution).filter_by(
            workflow_id=workflow_id
        ).first()
        if wf:
            ctx = dict(wf.context_data or {})
            ctx[intent] = result
            wf.context_data = ctx
            db.commit()

        logger.info(
            f"[execute_deferred_subtask] Completed '{intent}': {result}"
        )
        return result

    except Exception as exc:
        db.rollback()
        logger.error(
            f"[execute_deferred_subtask] DB update failed for '{intent}': {exc}"
        )
        raise self.retry(exc=exc)
    finally:
        db.close()