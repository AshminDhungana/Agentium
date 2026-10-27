"""
WorkflowExecutor — runs a WorkflowPlan as a directed acyclic graph (DAG).

Execution rules
---------------
1. Sub-tasks whose ``depends_on`` list is empty (or all resolved) run first.
   Multiple independent tasks execute concurrently via asyncio.gather.
2. Each completed task's output dict is stored in a shared ``context`` dict
   keyed by intent name, then merged into the params of every downstream task.
3. Deferred sub-tasks (``schedule_offset_days > 0``) are never run directly;
   they are handed to Celery with the appropriate countdown.
4. The WorkflowExecution DB record is updated after every state transition so
   the API can return live status at any point.
5. Tasks with ``max_retries > 0`` will be retried with exponential backoff
   (0.5s × 2^attempt) before being marked as failed.
"""
import asyncio

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from backend.models.database import get_db_context
from backend.models.entities.workflow import WorkflowExecution, WorkflowSubTask
from backend.services.workflow_planner import WorkflowPlan, SubTaskSpec
import backend.services.workflow_tools as workflow_tools   # avoids circular import

from backend.services.structured_logging import get_structured_logger, get_request_id, timed_step, structured_log_context
logger = get_structured_logger(__name__)


class WorkflowExecutor:
    """Execute a WorkflowPlan as a DAG with concurrent sub-tasks and deferred scheduling."""

    # Default backoff base for retries (seconds)
    _RETRY_BACKOFF_BASE = 0.5

    async def execute(
        self, plan: WorkflowPlan, created_by: str = None, db_session=None
    ) -> WorkflowExecution:
        """
        Persist *plan* to the database and execute all sub-tasks.
        Returns the final WorkflowExecution record (status may be
        'completed', 'completed_with_errors', or 'failed').

        Args:
            plan: The WorkflowPlan to execute
            created_by: User/agent ID that created this execution
            db_session: Optional SQLAlchemy session to use. If provided, all
                       database operations will use this session for transaction
                       isolation compatibility (e.g., in tests).
        """
        request_id = get_request_id() or f"workflow_{plan.workflow_id}"
        with structured_log_context(request_id=request_id, workflow_id=plan.workflow_id):
            with timed_step(logger, "workflow_execute", workflow_id=plan.workflow_id, created_by=created_by):
                execution = self._persist_plan(plan, created_by, db_session)
                await self._run_dag(plan, db_session)

                # Reload from DB to pick up all status updates
                if db_session is not None:
                    fresh = db_session.query(WorkflowExecution).filter_by(
                        workflow_id=plan.workflow_id
                    ).first()
                else:
                    with get_db_context() as db:
                        fresh = db.query(WorkflowExecution).filter_by(
                            workflow_id=plan.workflow_id
                        ).first()
                return fresh

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _persist_plan(self, plan: WorkflowPlan, created_by: str, db_session=None) -> WorkflowExecution:
        """Write the WorkflowExecution and all WorkflowSubTask rows.

        Args:
            plan: The WorkflowPlan to persist
            created_by: User/agent ID that created this execution
            db_session: Optional SQLAlchemy session to use. If not provided,
                       creates a new one via get_db_context().  This allows
                       tests to pass a seeded_db session for transaction
                       isolation compatibility.
        """
        with timed_step(logger, "workflow_persist_plan", workflow_id=plan.workflow_id, created_by=created_by):
            if db_session is not None:
                return self._persist_plan_inner(db_session, plan, created_by, flush_only=True)
            else:
                with get_db_context() as db:
                    return self._persist_plan_inner(db, plan, created_by, flush_only=False)

    def _persist_plan_inner(
        self, db, plan: WorkflowPlan, created_by: str, flush_only: bool
    ) -> WorkflowExecution:
        """Inner implementation of _persist_plan (no session ownership logic)."""
        with timed_step(logger, "workflow_persist_plan_inner", workflow_id=plan.workflow_id, subtask_count=len(plan.subtasks)):
            from backend.models.entities.workflow import Workflow

            result = db.query(Workflow).filter_by(id=plan.workflow_id).first()
            if not result:
                raise ValueError(f"Workflow {plan.workflow_id} not found in database session")

            execution = WorkflowExecution(
                workflow_id=plan.workflow_id,
                original_message=plan.original_message,
                status="running",
                context_data={},
                created_by=created_by,
            )
            db.add(execution)

            for spec in plan.subtasks:
                sub = WorkflowSubTask(
                    workflow_id=plan.workflow_id,
                    step_index=spec.step_index,
                    intent=spec.intent,
                    params=spec.params,
                    depends_on=spec.depends_on,
                    status="pending",
                    schedule_offset_days=spec.schedule_offset_days,
                )
                db.add(sub)

            if flush_only:
                db.flush()
            else:
                db.commit()

            logger.info(
                "[WorkflowExecutor] Persisted plan for workflow %s "
                "(%d subtasks, execution_id=%s)",
                plan.workflow_id, len(plan.subtasks), execution.id,
            )
            return execution

    async def _run_dag(self, plan: WorkflowPlan, db_session=None):
        """Topological execution loop.

        Immediate tasks are executed in rounds: each round gathers all tasks
        whose dependencies have resolved to ``"completed"`` and runs them
        concurrently via ``asyncio.gather``.  Deferred tasks (with
        ``schedule_offset_days > 0``) are enqueued to Celery with the
        appropriate countdown and are *not* included in the dependency graph
        for immediate tasks (the ``if dep in status_map`` guard at the
        readiness check intentionally skips references to deferred intents).
        """
        with timed_step(logger, "workflow_run_dag", workflow_id=plan.workflow_id, total_subtasks=len(plan.subtasks)):
            # status_map tracks local (in-memory) status for dependency resolution
            status_map: Dict[str, str] = {
                st.intent: "pending" for st in plan.subtasks
            }
            # Shared context: intent → result dict from that tool
            context: Dict[str, dict] = {}

            # Separate immediate from deferred tasks
            immediate = [st for st in plan.subtasks if st.schedule_offset_days == 0]
            deferred  = [st for st in plan.subtasks if st.schedule_offset_days > 0]

            max_rounds = len(immediate) + 1
            for round_num in range(max_rounds):
                # Tasks that are ready to run right now
                ready: List[SubTaskSpec] = [
                    st for st in immediate
                    if status_map[st.intent] == "pending"
                    and all(
                        status_map.get(dep) == "completed"
                        for dep in st.depends_on
                        if dep in status_map   # ignore deferred deps
                    )
                ]

                if not ready:
                    # Check whether we're stuck (all pending have a failed dep)
                    still_pending = [
                        st for st in immediate
                        if status_map[st.intent] == "pending"
                    ]
                    if not still_pending:
                        break  # All immediate tasks settled
                    for st in still_pending:
                        if any(
                            status_map.get(dep) == "failed"
                            for dep in st.depends_on
                        ):
                            status_map[st.intent] = "failed"
                            self._update_subtask(
                                plan.workflow_id, st.intent, "failed",
                                error="Skipped: a dependency failed.", db_session=db_session
                            )
                    break

                # Execute ready tasks concurrently
                with timed_step(logger, "workflow_dag_round", workflow_id=plan.workflow_id, round=round_num, ready_count=len(ready)):
                    results = await asyncio.gather(
                        *[self._execute_one(plan.workflow_id, st, context, db_session)
                          for st in ready],
                        return_exceptions=True,
                    )

                for st, result in zip(ready, results):
                    if isinstance(result, Exception):
                        status_map[st.intent] = "failed"
                        logger.error(
                            "[WorkflowExecutor] '%s' failed: %s", st.intent, result
                        )
                    else:
                        status_map[st.intent] = "completed"
                        context[st.intent] = result  # make available to downstream tasks

            # Enqueue deferred tasks with Celery countdown
            for st in deferred:
                self._enqueue_deferred(plan.workflow_id, st, context, db_session)
                status_map[st.intent] = "scheduled"

            # Determine and persist final workflow status
            failed = [k for k, v in status_map.items() if v == "failed"]
            if len(failed) == len(plan.subtasks):
                final_status = "failed"
            elif failed:
                final_status = "completed_with_errors"
            else:
                final_status = "completed"

            self._finalize_workflow(plan.workflow_id, final_status, context, db_session)

    async def _execute_one(
        self,
        workflow_id: str,
        spec: SubTaskSpec,
        context: dict,
        db_session=None,
    ) -> dict:
        """Execute a single sub-task with optional retries.

        Retries up to ``spec.max_retries`` times with exponential backoff
        (``_RETRY_BACKOFF_BASE`` × 2^attempt).  On final failure the
        exception is re-raised so the caller marks the task as failed.
        """
        with timed_step(logger, "workflow_execute_one", workflow_id=workflow_id, intent=spec.intent, max_retries=spec.max_retries):
            self._update_subtask(workflow_id, spec.intent, "running", db_session=db_session)

            last_exc: Optional[Exception] = None
            attempts = 1 + spec.max_retries  # 1 initial attempt + retries

            for attempt in range(attempts):
                with timed_step(logger, "workflow_subtask_attempt", workflow_id=workflow_id, intent=spec.intent, attempt=attempt + 1):
                    try:
                        result = await workflow_tools.execute(spec.intent, spec.params, context)
                        self._update_subtask(
                            workflow_id, spec.intent, "completed",
                            result=result, db_session=db_session,
                        )
                        if attempt > 0:
                            logger.info(
                                "[WorkflowExecutor] '%s' succeeded on retry %d/%d",
                                spec.intent, attempt, spec.max_retries,
                            )
                        return result
                    except Exception as exc:
                        last_exc = exc
                        if attempt < attempts - 1:
                            backoff = self._RETRY_BACKOFF_BASE * (2 ** attempt)
                            logger.warning(
                                "[WorkflowExecutor] '%s' attempt %d failed (%s), "
                                "retrying in %.1fs (%d retries left)",
                                spec.intent, attempt + 1, exc, backoff,
                                attempts - attempt - 1,
                            )
                            await asyncio.sleep(backoff)

            # All attempts exhausted
            self._update_subtask(
                workflow_id, spec.intent, "failed",
                error=str(last_exc), db_session=db_session,
            )
            raise last_exc

    # ------------------------------------------------------------------
    # DB helpers — each has an outer (session-routing) + inner (logic)
    # ------------------------------------------------------------------

    def _update_subtask(
        self,
        workflow_id: str,
        intent: str,
        status: str,
        result: dict = None,
        error: str = None,
        db_session=None,
    ):
        """Update a single WorkflowSubTask row in the database."""
        with timed_step(logger, "workflow_update_subtask", workflow_id=workflow_id, intent=intent, status=status):
            if db_session is not None:
                self._update_subtask_inner(
                    db_session, workflow_id, intent, status, result, error, flush_only=True,
                )
            else:
                with get_db_context() as db:
                    self._update_subtask_inner(
                        db, workflow_id, intent, status, result, error, flush_only=False,
                    )

    def _update_subtask_inner(
        self, db, workflow_id, intent, status, result, error, flush_only,
    ):
        """Inner implementation of _update_subtask."""
        with timed_step(logger, "workflow_update_subtask_inner", workflow_id=workflow_id, intent=intent, status=status):
            sub = db.query(WorkflowSubTask).filter_by(
                workflow_id=workflow_id, intent=intent
            ).first()
            if not sub:
                return
            sub.status = status
            if result is not None:
                sub.result = result
            if error:
                sub.error = error
            if status in ("completed", "failed", "scheduled"):
                sub.completed_at = datetime.utcnow()
            if flush_only:
                db.flush()
            else:
                db.commit()

    def _enqueue_deferred(
        self,
        workflow_id: str,
        spec: SubTaskSpec,
        context: dict,
        db_session=None,
    ):
        """Hand a deferred sub-task to Celery and record the task ID."""
        with timed_step(logger, "workflow_enqueue_deferred", workflow_id=workflow_id, intent=spec.intent, delay_seconds=spec.schedule_offset_days * 24 * 3600):
            from backend.services.tasks.workflow_tasks import execute_deferred_subtask

            delay = spec.schedule_offset_days * 24 * 3600
            # Merge upstream context into params so the deferred task has full data
            merged_params = {**{k: v for k, v in context.items()}, **spec.params}

            async_result = execute_deferred_subtask.apply_async(
                kwargs={
                    "workflow_id": workflow_id,
                    "intent": spec.intent,
                    "params": merged_params,
                    "_request_id": get_request_id(),
                },
                countdown=delay,
            )

            if db_session is not None:
                self._record_deferred_inner(
                    db_session, workflow_id, spec, async_result, delay, flush_only=True,
                )
            else:
                with get_db_context() as db:
                    self._record_deferred_inner(
                        db, workflow_id, spec, async_result, delay, flush_only=False,
                    )

            logger.info(
                "[WorkflowExecutor] Deferred '%s' enqueued in %ds (celery_id=%s)",
                spec.intent, delay, async_result.id,
            )

    def _record_deferred_inner(self, db, workflow_id, spec, async_result, delay, flush_only):
        """Record the Celery task ID for a deferred subtask."""
        with timed_step(logger, "workflow_record_deferred_inner", workflow_id=workflow_id, intent=spec.intent, celery_task_id=async_result.id):
            sub = db.query(WorkflowSubTask).filter_by(
                workflow_id=workflow_id, intent=spec.intent
            ).first()
            if sub:
                sub.celery_task_id = async_result.id
                sub.status = "scheduled"
                sub.scheduled_for = datetime.utcnow() + timedelta(seconds=delay)
            if flush_only:
                db.flush()
            else:
                db.commit()

    def _finalize_workflow(
        self,
        workflow_id: str,
        status: str,
        context: dict,
        db_session=None,
    ):
        """Write the final workflow status and merged context to the database."""
        with timed_step(logger, "workflow_finalize", workflow_id=workflow_id, final_status=status, context_keys=list(context.keys())):
            if db_session is not None:
                self._finalize_inner(db_session, workflow_id, status, context, flush_only=True)
            else:
                with get_db_context() as db:
                    self._finalize_inner(db, workflow_id, status, context, flush_only=False)
            logger.info("[WorkflowExecutor] Workflow %s → %s", workflow_id, status)

    def _finalize_inner(self, db, workflow_id, status, context, flush_only):
        """Inner implementation of _finalize_workflow."""
        with timed_step(logger, "workflow_finalize_inner", workflow_id=workflow_id, final_status=status):
            wf = db.query(WorkflowExecution).filter_by(
                workflow_id=workflow_id
            ).first()
            if wf:
                wf.status = status
                wf.context_data = context
                wf.completed_at = datetime.utcnow()
            if flush_only:
                db.flush()
            else:
                db.commit()