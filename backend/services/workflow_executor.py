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
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, List

from backend.models.database import get_db_context
from backend.models.entities.workflow import WorkflowExecution, WorkflowSubTask
from backend.services.workflow_planner import WorkflowPlan, SubTaskSpec
import backend.services.workflow_tools as workflow_tools   # avoids circular import

logger = logging.getLogger(__name__)


class WorkflowExecutor:
    """Execute a WorkflowPlan as a DAG with concurrent sub-tasks and deferred scheduling."""

    async def execute(
        self, plan: WorkflowPlan, created_by: str = None
    ) -> WorkflowExecution:
        """
        Persist *plan* to the database and execute all sub-tasks.
        Returns the final WorkflowExecution record (status may be
        'completed', 'completed_with_errors', or 'failed').
        """
        execution = self._persist_plan(plan, created_by)
        await self._run_dag(plan)
        # Reload from DB to pick up all status updates
        with get_db_context() as db:
            fresh = db.query(WorkflowExecution).filter_by(
                workflow_id=plan.workflow_id
            ).first()
        return fresh

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _persist_plan(self, plan: WorkflowPlan, created_by: str) -> WorkflowExecution:
        """Write the WorkflowExecution and all WorkflowSubTask rows."""
        with get_db_context() as db:
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

            db.commit()
        return execution

    async def _run_dag(self, plan: WorkflowPlan):
        """Topological execution loop."""
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
        for _ in range(max_rounds):
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
                            error="Skipped: a dependency failed."
                        )
                break

            # Execute ready tasks concurrently
            results = await asyncio.gather(
                *[self._execute_one(plan.workflow_id, st, context)
                  for st in ready],
                return_exceptions=True,
            )

            for st, result in zip(ready, results):
                if isinstance(result, Exception):
                    status_map[st.intent] = "failed"
                    logger.error(
                        f"[WorkflowExecutor] '{st.intent}' failed: {result}"
                    )
                else:
                    status_map[st.intent] = "completed"
                    context[st.intent] = result  # make available to downstream tasks

        # Enqueue deferred tasks with Celery countdown
        for st in deferred:
            self._enqueue_deferred(plan.workflow_id, st, context)
            status_map[st.intent] = "scheduled"

        # Determine and persist final workflow status
        failed = [k for k, v in status_map.items() if v == "failed"]
        if len(failed) == len(plan.subtasks):
            final_status = "failed"
        elif failed:
            final_status = "completed_with_errors"
        else:
            final_status = "completed"

        self._finalize_workflow(plan.workflow_id, final_status, context)

    async def _execute_one(
        self,
        workflow_id: str,
        spec: SubTaskSpec,
        context: dict,
    ) -> dict:
        """Execute a single sub-task, update DB, return result."""
        self._update_subtask(workflow_id, spec.intent, "running")
        try:
            result = await workflow_tools.execute(spec.intent, spec.params, context)
            self._update_subtask(workflow_id, spec.intent, "completed", result=result)
            return result
        except Exception as exc:
            self._update_subtask(workflow_id, spec.intent, "failed", error=str(exc))
            raise

    def _update_subtask(
        self,
        workflow_id: str,
        intent: str,
        status: str,
        result: dict = None,
        error: str = None,
    ):
        """Update a single WorkflowSubTask row in the database."""
        with get_db_context() as db:
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
            db.commit()

    def _enqueue_deferred(
        self,
        workflow_id: str,
        spec: SubTaskSpec,
        context: dict,
    ):
        """Hand a deferred sub-task to Celery and record the task ID."""
        from backend.services.tasks.workflow_tasks import execute_deferred_subtask

        delay = spec.schedule_offset_days * 24 * 3600
        # Merge upstream context into params so the deferred task has full data
        merged_params = {**{k: v for k, v in context.items()}, **spec.params}

        async_result = execute_deferred_subtask.apply_async(
            kwargs={
                "workflow_id": workflow_id,
                "intent": spec.intent,
                "params": merged_params,
            },
            countdown=delay,
        )

        with get_db_context() as db:
            sub = db.query(WorkflowSubTask).filter_by(
                workflow_id=workflow_id, intent=spec.intent
            ).first()
            if sub:
                sub.celery_task_id = async_result.id
                sub.status = "scheduled"
                sub.scheduled_for = datetime.utcnow() + timedelta(seconds=delay)
                db.commit()

        logger.info(
            f"[WorkflowExecutor] Deferred '{spec.intent}' enqueued "
            f"in {delay}s (celery_id={async_result.id})"
        )

    def _finalize_workflow(
        self,
        workflow_id: str,
        status: str,
        context: dict,
    ):
        """Write the final workflow status and merged context to the database."""
        with get_db_context() as db:
            wf = db.query(WorkflowExecution).filter_by(
                workflow_id=workflow_id
            ).first()
            if wf:
                wf.status = status
                wf.context_data = context
                wf.completed_at = datetime.utcnow()
                db.commit()
        logger.info(f"[WorkflowExecutor] Workflow {workflow_id} → {status}")