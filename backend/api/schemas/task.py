"""
Pydantic schemas for Task API.
"""
from pydantic import BaseModel, Field, validator
from datetime import datetime
from typing import Optional, List, Any

from backend.models.entities.task import TaskStatus, TaskType, TaskPriority


class AssignedAgents(BaseModel):
    head: Optional[str] = None
    lead: Optional[str] = None
    task_agents: List[str] = []

    class Config:
        extra = "allow"


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    priority: str = Field(default="normal")
    task_type: str = Field(default="execution")

    @validator("priority")
    def validate_priority(cls, v):
        # Map frontend "urgent" -> "high" (entity has no "urgent")
        mapping = {"urgent": "high"}
        v = mapping.get(v, v)
        allowed = [p.value for p in TaskPriority]
        return v if v in allowed else "normal"

    @validator("task_type")
    def validate_task_type(cls, v):
        allowed = [t.value for t in TaskType]
        return v if v in allowed else "execution"


class TaskResponse(BaseModel):
    # id is a UUID string in BaseEntity, NOT an int
    id: str
    title: str
    description: str
    status: str
    priority: str
    task_type: str = "execution"
    progress: float = 0.0
    assigned_agents: AssignedAgents = AssignedAgents()
    created_at: Optional[str] = None   # ISO string — avoids datetime parsing issues
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True
        extra = "allow"   # ignore extra fields from _serialize()


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None