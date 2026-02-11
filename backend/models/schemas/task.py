"""
Pydantic schemas for Task API.
Maps to/from backend.models.entities.task (Task entity).
"""
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List, Any, Dict

# Import the real enums from the entity so validation stays in sync
from backend.models.entities.task import TaskStatus, TaskType, TaskPriority


class AssignedAgents(BaseModel):
    """Matches the assigned_agents dict in Task.to_dict()"""
    head: Optional[str] = None
    lead: Optional[str] = None
    task_agents: List[str] = []   # ← TaskCard reads .task_agents.length


class TaskCreate(BaseModel):
    """
    Fields the frontend sends when creating a task (CreateTaskModal.tsx).
    priority and task_type come in as strings like "normal", "execution".
    """
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    priority: str = Field(default="normal")   # "low"|"normal"|"urgent"|"critical"
    task_type: str = Field(default="execution")  # "execution"|"research"|"creative"

    @validator("priority")
    def validate_priority(cls, v):
        allowed = [p.value for p in TaskPriority]
        # frontend sends "urgent" but entity only has "critical","high","normal","low","idle"
        # map "urgent" → "high" so it doesn't blow up
        mapping = {"urgent": "high"}
        v = mapping.get(v, v)
        if v not in allowed:
            raise ValueError(f"priority must be one of {allowed}")
        return v

    @validator("task_type")
    def validate_task_type(cls, v):
        allowed = [t.value for t in TaskType]
        if v not in allowed:
            # default to execution for unknown types (e.g. "creative")
            return "execution"
        return v


class TaskResponse(BaseModel):
    """
    Shape returned to the frontend.
    Field names match what Task.to_dict() produces so the
    inline main.py routes and the router both work correctly.
    """
    id: int
    title: str
    description: str
    status: str                              # TaskStatus.value (string)
    priority: str                            # TaskPriority.value (string)
    task_type: str = "execution"             # mapped from to_dict()'s "type" key
    progress: float = 0.0                    # completion_percentage
    assigned_agents: AssignedAgents = AssignedAgents()  # ← TaskCard crash fix
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True              # works with SQLAlchemy ORM objects


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None