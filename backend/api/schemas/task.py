from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from backend.models.entities.task import TaskStatus

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field(..., min_length=1)
    priority: int = Field(default=5, ge=1, le=10)

class TaskResponse(BaseModel):
    id: int
    title: str
    description: str
    status: TaskStatus
    priority: int
    created_at: datetime
    updated_at: Optional[datetime]
    
    class Config:
        from_attributes = True

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[TaskStatus] = None
    priority: Optional[int] = None
