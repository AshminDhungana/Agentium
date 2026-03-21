from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from typing import List, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime

from backend.models.database import get_db_context
from backend.models.entities.workflow import Workflow, WorkflowExecution
from backend.services.workflow_engine import WorkflowEngine

router = APIRouter(prefix="/workflows", tags=["Workflows"])

# Dependency
def get_db():
    with get_db_context() as db:
        yield db

@router.post("/", response_model=Dict[str, Any])
def create_workflow(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Create a new automation workflow."""
    name = payload.get("name")
    template = payload.get("template_json")
    agent_id = payload.get("agent_id", "A0001")
    cron = payload.get("schedule_cron")
    
    if not name or not template:
        raise HTTPException(status_code=400, detail="name and template_json required")
        
    wf = WorkflowEngine.create_workflow(db, name, template, agent_id, cron)
    db.commit()
    return wf.to_dict()

@router.get("/", response_model=List[Dict[str, Any]])
def list_workflows(db: Session = Depends(get_db)):
    """List all workflows."""
    workflows = db.query(Workflow).filter(Workflow.is_active == True).all()
    return [wf.to_dict() for wf in workflows]

@router.get("/{workflow_id}", response_model=Dict[str, Any])
def get_workflow(workflow_id: str, db: Session = Depends(get_db)):
    """Get workflow definition."""
    wf = db.query(Workflow).filter(Workflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf.to_dict()

@router.put("/{workflow_id}", response_model=Dict[str, Any])
def update_workflow(workflow_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Update workflow template."""
    template = payload.get("template_json")
    if not template:
        raise HTTPException(status_code=400, detail="template_json required")
    try:
        wf = WorkflowEngine.update_workflow(db, workflow_id, template)
        db.commit()
        return wf.to_dict()
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{workflow_id}/execute", response_model=Dict[str, Any])
def execute_workflow(workflow_id: str, payload: Dict[str, Any], db: Session = Depends(get_db)):
    """Trigger a workflow execution."""
    context = payload.get("context", {})
    try:
        execution = WorkflowEngine.trigger_execution(db, workflow_id, trigger="api", context=context)
        return execution.to_dict()
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/executions/{execution_id}", response_model=Dict[str, Any])
def get_execution_status(execution_id: str, db: Session = Depends(get_db)):
    """Get status of an execution."""
    execution = db.query(WorkflowExecution).filter(WorkflowExecution.id == execution_id).first()
    if not execution:
        raise HTTPException(status_code=404, detail="Execution not found")
    return execution.to_dict()

@router.get("/{workflow_id}/eta", response_model=Dict[str, Any])
def get_workflow_eta(workflow_id: str, db: Session = Depends(get_db)):
    """Calculate ETA based on historical data."""
    return WorkflowEngine.calculate_eta(db, workflow_id)

@router.get("/{workflow_id}/docs", response_model=Dict[str, str])
def get_workflow_docs(workflow_id: str, db: Session = Depends(get_db)):
    """Auto-generate documentation for a workflow."""
    doc = WorkflowEngine.auto_document(db, workflow_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return {"documentation": doc}