"""
Tasks API routes for Agentium.
"""
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, noload
from typing import List, Optional

from backend.models.database import get_db
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.api.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from backend.core.auth import get_current_active_user

router = APIRouter(prefix="/tasks", tags=["tasks"])


def _serialize(task: Task) -> dict:
    """
    Safely convert Task ORM → dict the frontend expects.
    Does NOT call task.to_dict() to avoid triggering lazy-loaded
    relationships (head_of_council, deliberation, subtasks, audit_logs)
    that can crash with DetachedInstanceError or bad JOINs.
    """
    # assigned_task_agent_ids is a JSON column - may be None on old rows
    task_agents = task.assigned_task_agent_ids
    if not isinstance(task_agents, list):
        task_agents = []

    return {
        "id":          str(task.id),
        "title":       task.title or "",
        "description": task.description or "",
        "status":      task.status.value  if task.status   else "pending",
        "priority":    task.priority.value if task.priority else "normal",
        "task_type":   task.task_type.value if task.task_type else "execution",
        "progress":    task.completion_percentage or 0,
        "assigned_agents": {
            "head":        task.head_of_council_id,
            "lead":        task.lead_agent_id,
            "task_agents": task_agents,
        },
        # Return ISO strings directly — avoids Pydantic datetime parsing surprises
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": None,   # BaseEntity may not have updated_at
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

    # created_by is String(10) — truncate to be safe
    creator = str(current_user.get("sub", "user"))[:10]

    task = Task(
        title=task_data.title,
        description=task_data.description,
        priority=priority_enum,
        task_type=type_enum,
        status=TaskStatus.PENDING,
        created_by=creator,
    )

    db.add(task)
    db.commit()
    db.refresh(task)

    return _serialize(task)


@router.get("/")
async def list_tasks(
    status: Optional[str] = Query(None),
    agent_id: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    """List tasks. Returns array of task objects."""
    # Use noload to prevent the lazy="joined" on head_of_council
    # from triggering extra queries / crashes on orphaned FKs
    query = db.query(Task).options(
        noload(Task.head_of_council),
        noload(Task.lead_agent),
        noload(Task.deliberation),
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

    tasks = query.order_by(Task.created_at.desc()).offset(skip).limit(limit).all()
    return [_serialize(t) for t in tasks]


@router.get("/{task_id}")
async def get_task(
    task_id: str,        # UUID string, not int
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(Task).options(
        noload(Task.head_of_council),
        noload(Task.lead_agent),
        noload(Task.deliberation),
    ).filter(Task.id == task_id).first()

    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _serialize(task)


@router.patch("/{task_id}")
async def update_task(
    task_id: str,
    task_data: TaskUpdate,
    current_user: dict = Depends(get_current_active_user),
    db: Session = Depends(get_db)
):
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    if task_data.title is not None:
        task.title = task_data.title
    if task_data.description is not None:
        task.description = task_data.description
    if task_data.status is not None:
        try:
            task.status = TaskStatus(task_data.status)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid status: {task_data.status}")
    if task_data.priority is not None:
        try:
            task.priority = TaskPriority(task_data.priority)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {task_data.priority}")

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
    task = db.query(Task).filter(Task.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")

    agents = task.assigned_task_agent_ids or []
    if not isinstance(agents, list):
        agents = []
    if agent_id not in agents:
        agents.append(agent_id)
        task.assigned_task_agent_ids = agents

    task.status = TaskStatus.IN_PROGRESS
    db.commit()
    db.refresh(task)

    return {"status": "success", "task": _serialize(task)}