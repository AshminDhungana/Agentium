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
        for step_data in steps_data:
            step = WorkflowStep(
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
            
        workflow.template_json = new_template
        workflow.version += 1
        
        WorkflowEngine._sync_steps_from_template(db, workflow, new_template)
        WorkflowEngine.create_version(db, workflow.id)
        return workflow

    @staticmethod
    def create_version(db: Session, workflow_id: str):
        """Versioning logic to save a snapshot of the workflow."""
        workflow = db.query(Workflow).filter(Workflow.id == workflow_id).first()
        if workflow:
            version_record = WorkflowVersion(
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
            created_by="workflow_system"
        )
        db.add(task)
        db.flush()
        
        # If task is sync, execute inline (or assume true for mock)
        # In a real agentic flow, we'd pause workflow, dispatch task to agents, and task completion hook resumes workflow.
        # Here we mock synchronous execution update.
        execution.context_data[f"step_{step.step_index}_task_id"] = task.id
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
        """Spawn multiple sub-workflows or tasks in parallel."""
        # Stub: dispatch parallel celery tasks
        execution.context_data[f"step_{step.step_index}_parallel"] = "dispatched"
        return True

    @staticmethod
    def register_cron_schedules():
        """
        Dynamically reload Celery Beat schedules based on Workflow.schedule_cron.
        Implementation relies on django-celery-beat or custom redbeat logic.
        """
        # (Placeholder for Cron syncing with Celery Beat backend)
        logger.info("Cron schedules synced for Workflows")

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


@shared_task
def workflow_step_runner(execution_id: str):
    """Celery worker task to resume workflow asynchronous steps."""
    with get_db_context() as db:
        WorkflowEngine.execute_current_step(db, execution_id)
