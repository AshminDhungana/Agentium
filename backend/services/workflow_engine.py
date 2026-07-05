"""<module>."""

import json
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging
from sqlalchemy.orm import Session
from celery import shared_task

from backend.models.entities.workflow import (
    Workflow,
    WorkflowExecution,
    WorkflowStep,
    WorkflowVersion,
    WorkflowExecutionStatus,
    WorkflowStepType
)
from backend.models.entities.task import Task, TaskPriority, TaskType
from backend.models.database import get_db_context

logger = logging.getLogger(__name__)

class WorkflowEngine:
    """
    Core orchestration engine for the Workflow Automation Pipeline.
    Responsible for interpreting workflow templates, transitioning states,
    spawning tasks, and evaluating conditions.
    """
    
    @staticmethod
    def create_workflow(db: Session, name: str, template_json: Dict[str, Any], agent_id: str, cron: str = None) -> Workflow:
        """Create a new workflow and its initial version."""
        workflow = Workflow(
            name=name,
            template_json=template_json,
            version=1,
            created_by_agent_id=agent_id,
            schedule_cron=cron
        )
        db.add(workflow)
        db.flush()
        
        # Parse template_json to steps
        WorkflowEngine._sync_steps_from_template(db, workflow, template_json)
        
        # Create version 1
        WorkflowEngine.create_version(db, workflow.id)
        
        if cron:
            WorkflowEngine.register_cron_schedules()
            
        return workflow

    @staticmethod
    def _sync_steps_from_template(db: Session, workflow: Workflow, template: Dict[str, Any]):
        """Convert JSON definition to WorkflowStep rows."""
        db.query(WorkflowStep).filter(WorkflowStep.workflow_id == workflow.id).delete()
        steps_data = template.get("steps", [])

        # Determine the starting step ID within this session so that
        # multiple steps created in the same transaction get unique IDs.
        from sqlalchemy import text
        result = db.execute(text("""
            SELECT agentium_id FROM workflow_steps
            WHERE agentium_id ~ '^WS[0-9]+$'
            ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC
            LIMIT 1
        """)).scalar()
        next_num = (int(result[2:]) + 1) if result else 1

        for step_data in steps_data:
            agentium_id = f"WS{next_num:05d}"
            next_num += 1
            step = WorkflowStep(
                agentium_id=agentium_id,
                workflow_id=workflow.id,
                step_index=step_data.get("step_index"),
                step_type=WorkflowStepType(step_data.get("type")),
                config=step_data.get("config", {}),
                on_success_step=step_data.get("on_success_step"),
                on_failure_step=step_data.get("on_failure_step")
            )
            db.add(step)
    
    @staticmethod
    def update_workflow(db: Session, workflow_id: str, new_template: Dict[str, Any]) -> Workflow:
        """Update workflow template, bumps version to keep history."""
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError("Workflow not found")

        # Snapshot current version BEFORE updating
        WorkflowEngine.create_version(db, workflow.id)

        workflow.template_json = new_template
        workflow.version += 1

        WorkflowEngine._sync_steps_from_template(db, workflow, new_template)
        return workflow

    @staticmethod
    def create_version(db: Session, workflow_id: str):
        """Versioning logic to save a snapshot of the workflow."""
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if workflow:
            # Determine the next version ID within this session
            from sqlalchemy import text
            result = db.execute(text("""
                SELECT agentium_id FROM workflow_versions
                WHERE agentium_id ~ '^WV[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC
                LIMIT 1
            """)).scalar()
            next_num = (int(result[2:]) + 1) if result else 1
            agentium_id = f"WV{next_num:05d}"

            version_record = WorkflowVersion(
                agentium_id=agentium_id,
                workflow_id=workflow.id,
                version=workflow.version,
                template_json=workflow.template_json
            )
            db.add(version_record)

    @staticmethod
    def trigger_execution(db: Session, workflow_id: str, trigger: str = "manual", context: Dict[str, Any] = None) -> WorkflowExecution:
        """Start a new workflow execution."""
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            raise ValueError("Workflow not found")
            
        execution = WorkflowExecution(
            workflow_id=workflow_id,
            status=WorkflowExecutionStatus.RUNNING,
            current_step_index=0,
            context_data=context or {},
            triggered_by=trigger,
            started_at=datetime.utcnow()
        )
        db.add(execution)
        db.commit()
        db.refresh(execution)
        
        # Enqueue first step asynchronously
        workflow_step_runner.delay(execution.id)
        return execution

    @staticmethod
    def execute_current_step(db: Session, execution_id: str):
        """Execute the current step of the workflow."""
        execution = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
        if not execution or execution.status != WorkflowExecutionStatus.RUNNING:
            return

        step = db.query(WorkflowStep).filter(
            WorkflowStep.workflow_id == execution.workflow_id,
            WorkflowStep.step_index == execution.current_step_index
        ).first()

        if not step:
            # Reached end naturally
            execution.status = WorkflowExecutionStatus.COMPLETED
            execution.completed_at = datetime.utcnow()
            db.commit()
            return

        try:
            success = False
            if step.step_type == WorkflowStepType.TASK:
                success = WorkflowEngine._execute_task_step(db, execution, step)
            elif step.step_type == WorkflowStepType.CONDITION:
                success = WorkflowEngine._execute_condition_step(execution, step)
            elif step.step_type == WorkflowStepType.PARALLEL:
                success = WorkflowEngine._execute_parallel_step(db, execution, step)
            elif step.step_type == WorkflowStepType.WAIT_POLL:
                # Suspend; WaitPollService will re-enqueue this execution on resolution
                WorkflowEngine._execute_wait_step(db, execution, step)
                return  # break loop — resumed by WaitPollService callback
            elif step.step_type == WorkflowStepType.DELAY:
                # Delay is handled by enqueuing a celery task with countdown
                delay_sec = step.config.get("delay_seconds", 60)
                WorkflowEngine._advance_step(db, execution, step.on_success_step)
                workflow_step_runner.apply_async(args=[execution.id], countdown=delay_sec)
                return  # break loop here, let celery resume it
            elif step.step_type == WorkflowStepType.HUMAN_APPROVAL:
                execution.status = WorkflowExecutionStatus.PAUSED
                db.commit()
                return  # awaits manual resume
            
            # Transition
            next_step_idx = step.on_success_step if success else step.on_failure_step
            if next_step_idx is not None:
                WorkflowEngine._advance_step(db, execution, next_step_idx)
                # Recurse or queue next iteration
                workflow_step_runner.delay(execution.id)
            else:
                # Terminate flow
                execution.status = WorkflowExecutionStatus.COMPLETED if success else WorkflowExecutionStatus.FAILED
                execution.completed_at = datetime.utcnow()
                db.commit()

        except Exception as e:
            logger.error(f"Error in step {step.step_index} execution: {e}")
            execution.status = WorkflowExecutionStatus.FAILED
            execution.completed_at = datetime.utcnow()
            execution.context_data["error"] = str(e)
            db.commit()

    @staticmethod
    def _advance_step(db: Session, execution: WorkflowExecution, next_idx: int):
        """Advance step."""

        execution.current_step_index = next_idx
        db.commit()

    @staticmethod
    def _execute_task_step(db: Session, execution: WorkflowExecution, step: WorkflowStep) -> bool:
        """Spawn a regular Agentium Task for this step."""
        task = Task(
            title=step.config.get("task_title", f"Workflow {execution.workflow_id} Step {step.step_index}"),
            description=step.config.get("prompt", "Execute workflow step"),
            task_type=TaskType.AUTOMATION,
            priority=TaskPriority.NORMAL,
            workflow_id=execution.workflow_id,
            context_data=execution.context_data,
            created_by="workflow"
        )
        db.add(task)
        db.flush()
        
        # Dispatch the task to the agent pool asynchronously.
        # Workflow pauses until the task completion hook resumes it.
        execution.status = WorkflowExecutionStatus.PAUSED
        execution.context_data[f"step_{step.step_index}_task_id"] = task.id
        execution.context_data[f"step_{step.step_index}_task_status"] = "dispatched"
        db.commit()

        # Enqueue the task via Celery as the agent dispatch trigger.
        from backend.services.tasks.task_executor import execute_task_async
        try:
            execute_task_async.delay(task.agentium_id, None)
        except Exception:
            logger.warning("Task dispatch failed for %s, workflow will wait", task.agentium_id, exc_info=True)
        return True

    @staticmethod
    def _execute_condition_step(execution: WorkflowExecution, step: WorkflowStep) -> bool:
        """Evaluate a logical condition based on context."""
        cond = step.config.get("condition", {})
        key = cond.get("key")
        expected = cond.get("expected")
        actual = execution.context_data.get(key)
        
        if cond.get("operator") == "==":
            return str(actual) == str(expected)
        if cond.get("operator") == "exists":
            return key in execution.context_data
        return False

    @staticmethod
    def _execute_parallel_step(db: Session, execution: WorkflowExecution, step: WorkflowStep) -> bool:
        """Spawn multiple sub-workflows or tasks in parallel via Celery group."""
        from celery import group
        from backend.services.tasks.task_executor import execute_task_async

        parallel_tasks = step.config.get("tasks", [])
        if not parallel_tasks:
            execution.context_data[f"step_{step.step_index}_parallel"] = "no_tasks"
            return True

        task_ids = []
        for task_spec in parallel_tasks:
            task = Task(
                title=task_spec.get("title", "Parallel workflow task"),
                description=task_spec.get("description", ""),
                priority=TaskPriority.NORMAL,
                workflow_id=execution.workflow_id,
                context_data=execution.context_data,
                created_by="workflow_parallel"
            )
            db.add(task)
            task_ids.append(str(task.id))
        db.commit()

        group(execute_task_async.s(tid, None) for tid in task_ids).apply_async()

        execution.context_data[f"step_{step.step_index}_parallel"] = "dispatched"
        execution.context_data[f"step_{step.step_index}_parallel_task_ids"] = task_ids
        return True

    @staticmethod
    def _execute_wait_step(
        db: Session,
        execution: WorkflowExecution,
        step: WorkflowStep,
    ) -> None:
        """
        Phase 16 — Suspend a WorkflowExecution until a WaitCondition resolves.

        Pauses the execution and creates a WaitCondition on the linked task
        (stored in ``execution.context_data["current_task_id"]`` if available,
        otherwise uses a synthetic task lookup).  When the condition resolves,
        ``WaitPollService`` calls ``workflow_step_runner.delay(execution.id)``
        to resume the workflow from the next step.

        Step config keys
        ----------------
        strategy               : WaitStrategy value (required)
        wait_config            : dict forwarded verbatim to WaitPollService
        max_attempts           : int  (default 60)
        poll_interval_seconds  : int  (default 30)
        timeout_seconds        : int  (optional)
        """
        from backend.services.wait_poll_service import WaitPollService
        from backend.models.entities.wait_condition import WaitStrategy
        from backend.models.entities.task import Task, TaskStatus

        cfg              = step.config or {}
        strategy_value   = cfg.get("strategy", WaitStrategy.TIMEOUT.value)
        wait_config      = cfg.get("wait_config", {})
        max_attempts     = int(cfg.get("max_attempts", 60))
        poll_interval    = int(cfg.get("poll_interval_seconds", 30))
        timeout_seconds  = cfg.get("timeout_seconds")

        try:
            wait_strategy = WaitStrategy(strategy_value)
        except ValueError:
            logger.error(
                "WorkflowEngine._execute_wait_step: unknown strategy '%s' — "
                "defaulting to TIMEOUT (60 s)", strategy_value
            )
            wait_strategy   = WaitStrategy.TIMEOUT
            timeout_seconds = timeout_seconds or 60

        # Resolve the task to attach the WaitCondition to
        task_id = execution.context_data.get("current_task_id") if execution.context_data else None
        if not task_id:
            # Fallback: find the most recent IN_PROGRESS task for this workflow
            task = (
                db.query(Task)
                .filter(
                    Task.workflow_id == execution.workflow_id,
                    Task.status == TaskStatus.IN_PROGRESS,
                )
                .order_by(Task.created_at.desc())
                .first()
            )
            if not task:
                logger.warning(
                    "WorkflowEngine._execute_wait_step: no IN_PROGRESS task found "
                    "for workflow %s — pausing execution without WaitCondition",
                    execution.workflow_id,
                )
                execution.status = WorkflowExecutionStatus.PAUSED
                db.commit()
                return
            task_id = task.id

        condition = WaitPollService.create_condition(
            db=db,
            task_id=task_id,
            strategy=wait_strategy,
            config=wait_config,
            max_attempts=max_attempts,
            poll_interval_seconds=poll_interval,
            timeout_seconds=int(timeout_seconds) if timeout_seconds else None,
            created_by_agent_id="workflow_engine",
        )

        # Store condition ID and next step so the poller can resume correctly
        ctx = execution.context_data or {}
        ctx[f"step_{step.step_index}_wait_condition_id"] = str(condition.id)
        ctx[f"step_{step.step_index}_on_success_step"]   = step.on_success_step
        execution.context_data = ctx

        execution.status = WorkflowExecutionStatus.PAUSED
        db.commit()

        logger.info(
            "WorkflowEngine: execution %s paused at step %s "
            "(WaitCondition %s, strategy=%s)",
            execution.id, step.step_index, condition.agentium_id, strategy_value,
        )

    @staticmethod
    def resume_after_wait(db: Session, execution_id: str, step_index: int) -> None:
        """
        Called by WaitPollService (or a webhook handler) once a WAIT_POLL step
        condition has resolved.  Advances to on_success_step and re-enqueues
        the workflow runner.
        """
        execution = db.query(WorkflowExecution).filter(
            WorkflowExecution.id == execution_id
        ).first()
        if not execution:
            logger.warning("resume_after_wait: execution %s not found", execution_id)
            return

        ctx            = execution.context_data or {}
        next_step_idx  = ctx.get(f"step_{step_index}_on_success_step")

        if next_step_idx is not None:
            execution.status = WorkflowExecutionStatus.RUNNING
            WorkflowEngine._advance_step(db, execution, next_step_idx)
            workflow_step_runner.delay(execution.id)
        else:
            execution.status       = WorkflowExecutionStatus.COMPLETED
            execution.completed_at = datetime.utcnow()
            db.commit()

    @staticmethod
    def register_cron_schedules():
        """
        Dynamically reload Celery Beat schedules based on Workflow.schedule_cron.
        Queries active workflows with a cron expression and syncs them to the
        Celery Beat periodic task registry.
        """
        from backend.celery_app import celery_app
        from celery.schedules import crontab

        try:
            with get_db_context() as db:
                workflows = db.query(Workflow).filter(
                    Workflow.is_active == True,
                    Workflow.schedule_cron.isnot(None)
                ).all()

                for wf in workflows:
                    try:
                        parts = wf.schedule_cron.split()
                        schedule_entry = crontab(minute=parts[0], hour=parts[1], day_of_month=parts[2], month_of_year=parts[3], day_of_week=parts[4])
                        celery_app.conf.beat_schedule[f"workflow-{wf.id}"] = {
                            "task": "agentium.services.workflow_engine.workflow_step_runner",
                            "schedule": schedule_entry,
                            "args": (str(wf.id),),
                        }
                        logger.info("Registered cron schedule for workflow %s", wf.id)
                    except (ValueError, IndexError) as e:
                        logger.error("Failed to register cron for workflow %s: %s", wf.id, e)
        except Exception as e:
            logger.error("Error syncing workflow cron schedules: %s", e)

    @staticmethod
    def calculate_eta(db: Session, workflow_id: str) -> dict:
        """Calculate historical ETA based on past executions."""
        executions = db.query(WorkflowExecution).filter(
            WorkflowExecution.workflow_id == workflow_id,
            WorkflowExecution.status == WorkflowExecutionStatus.COMPLETED,
            WorkflowExecution.completed_at != None,
            WorkflowExecution.started_at != None
        ).limit(10).all()
        
        if not executions:
            return {"eta_seconds": None, "confidence": "none"}
            
        durations = [(e.completed_at - e.started_at).total_seconds() for e in executions]
        avg = sum(durations) / len(durations)
        return {"eta_seconds": int(avg), "confidence": "high" if len(durations) >= 5 else "low"}

    @staticmethod
    def auto_document(db: Session, workflow_id: str) -> str:
        """Integrate with task_learnings to generate auto-documentation."""
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if not workflow:
            return ""
        
        doc = f"# Workflow: {workflow.name}\n"
        doc += f"Description: {workflow.description}\n"
        doc += f"Version: {workflow.version}\n"
        doc += "## Steps:\n"
        
        steps = db.query(WorkflowStep).filter(WorkflowStep.workflow_id == workflow.id).order_by(WorkflowStep.step_index).all()
        for s in steps:
            doc += f"- Step {s.step_index}: {s.step_type.value} -> On success go to {s.on_success_step}\n"
            
        return doc


@shared_task(name="agentium.services.workflow_engine.workflow_step_runner")
def workflow_step_runner(execution_id: str):
    """Celery worker task to resume workflow asynchronous steps."""
    with get_db_context() as db:
        WorkflowEngine.execute_current_step(db, execution_id)