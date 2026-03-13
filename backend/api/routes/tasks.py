"""
Tasks API routes for Agentium.
Updated for Task Execution Architecture: Governance Alignment
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, noload
from typing import List, Optional

from backend.models.database import get_db
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.task_events import TaskEvent, TaskEventType
from backend.api.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from backend.core.auth import get_current_active_user
from backend.services.task_state_machine import TaskStateMachine, IllegalStateTransition
from backend.services.acceptance_criteria import AcceptanceCriteriaService  # Phase 6.3

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _serialize(task: Task) -> dict:
    """
    Safely convert Task ORM → dict the frontend expects.
    """
    task_agents = task.assigned_task_agent_ids
    if not isinstance(task_agents, list):
        task_agents = []

    return {
        "id": str(task.id),
        "agentium_id": task.agentium_id,
        "title": task.title or "",
        "description": task.description or "",
        "status": task.status.value if task.status else "pending",
        "priority": task.priority.value if task.priority else "normal",
        "task_type": task.task_type.value if task.task_type else "execution",
        "progress": task.completion_percentage or 0,
        "assigned_agents": {
            "head": task.head_of_council_id,
            "lead": task.lead_agent_id,
            "task_agents": task_agents,
        },
        # NEW: Governance fields
        "governance": {
            "constitutional_basis": task.constitutional_basis,
            "hierarchical_id": task.hierarchical_id,
            "parent_task_id": task.parent_task_id,
            "execution_plan_id": task.execution_plan_id,
            "recurrence_pattern": task.recurrence_pattern,
            "requires_deliberation": task.requires_deliberation,
            "council_approved": task.approved_by_council,
            "head_approved": task.approved_by_head,
            # Phase 6.3
            "acceptance_criteria": task.acceptance_criteria,
            "veto_authority": task.veto_authority,
        },
        # NEW: Error info
        "error_info": {
            "error_count": task.error_count,
            "retry_count": task.retry_count,
            "max_retries": task.max_retries,
            "last_error": task.last_error
        } if task.error_count > 0 else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if hasattr(task, 'updated_at') and task.updated_at else None,
        "event_count": task.events.count() if hasattr(task, 'events') else 0
    }


@router.post("/", status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Create a new task."""
    try:
        priority_enum = TaskPriority(task_data.priority)
    except ValueError:
        priority_enum = TaskPriority.NORMAL

    try:
        type_enum = TaskType(task_data.task_type)
    except ValueError:
        type_enum = TaskType.EXECUTION

    creator = str(current_user.get("sub", "user"))[:10]

    task = Task(
        title=task_data.title,
        description=task_data.description,
        priority=priority_enum,
        task_type=type_enum,
        status=TaskStatus.PENDING,
        created_by=creator,
        # NEW: Set governance fields if provided
        constitutional_basis=task_data.constitutional_basis,
        hierarchical_id=task_data.hierarchical_id,
        parent_task_id=task_data.parent_task_id,
        execution_plan_id=task_data.execution_plan_id,
        recurrence_pattern=task_data.recurrence_pattern,
    )

    # Phase 6.3: Validate and store acceptance_criteria + veto_authority
    if task_data.acceptance_criteria:
        try:
            parsed_criteria = AcceptanceCriteriaService.parse_and_validate(
                task_data.acceptance_criteria
            )
            task.acceptance_criteria = AcceptanceCriteriaService.to_json(parsed_criteria)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))

    if task_data.veto_authority:
        valid_veto = {"code", "output", "plan"}
        if task_data.veto_authority not in valid_veto:
            raise HTTPException(
                status_code=422,
                detail=f"veto_authority must be one of: {sorted(valid_veto)}"
            )
        task.veto_authority = task_data.veto_authority

    db.add(task)
    db.commit()
    db.refresh(task)

    # Emit creation event
    event = TaskEvent(
        task_id=task.id,
        event_type=TaskEventType.TASK_CREATED,
        actor_id=creator,
        actor_type="user",
        data={
            "title": task.title,
            "description": task.description,
            "priority": task.priority.value,
            "task_type": task.task_type.value,
            "created_by": creator
        }
    )
    db.add(event)
    db.commit()

    return _serialize(task)


@router.get("/")
async def list_tasks(
    status: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    parent_task_id: Optional[str] = Query(None),  # Filter by parent
    my_tasks: bool = Query(False),                 # Scope to current user's tasks only
    hide_system: bool = Query(True),               # Hide idle/system tasks (on by default)
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List tasks. Returns array of task objects."""
    query = db.query(Task).options(
        noload(Task.head_of_council),
        noload(Task.lead_agent),
        noload(Task.deliberation),
        noload(Task.events)
    )

    if status:
        try:
            task_status = TaskStatus(status.lower())
            query = query.filter(Task.status == task_status)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status '{status}'. Valid: {[s.value for s in TaskStatus]}"
            )

    if agent_id:
        query = query.filter(
            Task.assigned_task_agent_ids.contains([agent_id])
        )
    
    # Filter by parent task
    if parent_task_id:
        query = query.filter(Task.parent_task_id == parent_task_id)

    # User isolation: restrict to tasks created by the current user
    if my_tasks:
        user_id = str(current_user.get("sub", ""))
        query = query.filter(Task.created_by == user_id)

    # System task filter: exclude idle/agent-generated tasks unless explicitly requested
    if hide_system:
        query = query.filter(Task.is_idle_task != True)  # noqa: E712

    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize(t) for t in tasks]

@router.get("/active")
async def get_active_tasks(
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all active tasks (excludes system/idle tasks)."""
    tasks = db.query(Task).filter(
        Task.status.in_([TaskStatus.PENDING, TaskStatus.IN_PROGRESS, TaskStatus.DELIBERATING]),
        Task.is_idle_task != True,  # noqa: E712
    ).order_by(Task.created_at.desc()).all()
    return {"tasks": [_serialize(t) for t in tasks], "total": len(tasks)}

@router.get("/{task_id}")
async def get_task(
    task_id: str,
    include_events: bool = Query(False),  # NEW: Optional event inclusion
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get specific task by ID."""
    task = db.query(Task).options(
        noload(Task.head_of_council),
        noload(Task.lead_agent),
        noload(Task.deliberation),
    ).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    result = _serialize(task)
    
    # NEW: Include events if requested
    if include_events:
        events = db.query(TaskEvent).filter_by(task_id=task_id).order_by(TaskEvent.created_at).all()
        result["events"] = [e.to_dict() for e in events]
    
    # NEW: Include subtasks if any
    if task.child_tasks:
        result["subtasks"] = [{"id": t.id, "agentium_id": t.agentium_id, "title": t.title, "status": t.status.value} for t in task.child_tasks]
    
    return result


@router.patch("/{task_id}")
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Update task. Status changes go through state machine validation."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    # Handle status change with state machine validation
    if task_data.status is not None:
        try:
            new_status = TaskStatus(task_data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {task_data.status}")
        
        try:
            # Use task's set_status method which includes state machine validation
            task.set_status(new_status, str(current_user.get("sub", "user")), task_data.status_note)
        except IllegalStateTransition as e:
            raise HTTPException(status_code=400, detail=str(e))
    
    # Update other fields
    if task_data.title is not None:
        task.title = task_data.title
    if task_data.description is not None:
        task.description = task_data.description
    if task_data.priority is not None:
        try:
            task.priority = TaskPriority(task_data.priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data.priority}")
    
    # NEW: Update governance fields
    if task_data.constitutional_basis is not None:
        task.constitutional_basis = task_data.constitutional_basis
    if task_data.hierarchical_id is not None:
        task.hierarchical_id = task_data.hierarchical_id
    if task_data.parent_task_id is not None:
        task.parent_task_id = task_data.parent_task_id
    if task_data.execution_plan_id is not None:
        task.execution_plan_id = task_data.execution_plan_id

    # Phase 6.3: Update acceptance_criteria and veto_authority
    if task_data.acceptance_criteria is not None:
        try:
            raw = [c.dict() for c in task_data.acceptance_criteria]
            parsed = AcceptanceCriteriaService.parse_and_validate(raw)
            task.acceptance_criteria = AcceptanceCriteriaService.to_json(parsed)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc))
    if task_data.veto_authority is not None:
        task.veto_authority = task_data.veto_authority

    db.commit()
    db.refresh(task)
    return _serialize(task)


@router.post("/{task_id}/execute")
async def execute_task(
    task_id: str,
    agent_id: str = Query(...),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Execute a task by assigning it to an agent."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    agents = task.assigned_task_agent_ids or []
    if not isinstance(agents, list):
        agents = []
    if agent_id not in agents:
        agents.append(agent_id)
        task.assigned_task_agent_ids = agents

    try:
        task.set_status(TaskStatus.IN_PROGRESS, agent_id)
    except IllegalStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    db.commit()
    db.refresh(task)

    return {"status": "success", "task": _serialize(task)}


# ═══════════════════════════════════════════════════════════
# NEW ENDPOINTS: Task Execution Architecture
# ═══════════════════════════════════════════════════════════

@router.post("/{task_id}/escalate")
async def escalate_task(
    task_id: str,
    reason: str = Query(..., description="Reason for escalation"),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Manually escalate a task to Council.
    Task must be in a state that allows escalation.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    try:
        task.escalate_to_council(reason, str(current_user.get("sub", "user")))
        db.commit()
        db.refresh(task)
    except IllegalStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "status": "success",
        "message": f"Task {task.agentium_id} escalated to Council",
        "task": _serialize(task)
    }


@router.get("/{task_id}/subtasks")
async def get_subtasks(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get all subtasks (child tasks) for a parent task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Get child tasks
    children = db.query(Task).filter(Task.parent_task_id == task_id).all()
    
    return {
        "parent_task": {
            "id": task.id,
            "agentium_id": task.agentium_id,
            "title": task.title
        },
        "subtasks": [_serialize(t) for t in children],
        "count": len(children)
    }


@router.get("/{task_id}/events")
async def get_task_events(
    task_id: str,
    event_type: Optional[str] = Query(None, description="Filter by event type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Get event history for a task (Event Sourcing).
    Returns immutable event log for complete audit trail.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    query = db.query(TaskEvent).filter(TaskEvent.task_id == task_id)
    
    if event_type:
        try:
            et = TaskEventType(event_type)
            query = query.filter(TaskEvent.event_type == et)
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event type. Valid: {[e.value for e in TaskEventType]}"
            )
    
    events = query.order_by(TaskEvent.created_at.desc()).offset(skip).limit(limit).all()
    
    return {
        "task_id": task_id,
        "agentium_id": task.agentium_id,
        "total_events": query.count(),
        "events": [e.to_dict() for e in events]
    }


@router.post("/{task_id}/retry")
async def retry_task(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """
    Manually retry a failed or escalated task.
    Resets retry count and puts task back in progress.
    """
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    if task.status not in [TaskStatus.FAILED, TaskStatus.ESCALATED, TaskStatus.STOPPED]:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry task in status {task.status.value}. Must be failed, escalated, or stopped."
        )
    
    # Reset counters
    task.retry_count = 0
    task.error_count = 0
    
    try:
        task.set_status(TaskStatus.IN_PROGRESS, str(current_user.get("sub", "user")), "Manual retry initiated")
        db.commit()
        db.refresh(task)
    except IllegalStateTransition as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "status": "success",
        "message": f"Task {task.agentium_id} queued for retry",
        "task": _serialize(task)
    }


@router.get("/{task_id}/allowed-transitions")
async def get_allowed_transitions(
    task_id: str,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """Get list of allowed status transitions for a task."""
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    
    allowed = TaskStateMachine.get_allowed_transitions(task.status)
    
    return {
        "task_id": task_id,
        "current_status": task.status.value,
        "allowed_transitions": [s.value for s in allowed],
        "is_terminal": TaskStateMachine.is_terminal_state(task.status)
    }