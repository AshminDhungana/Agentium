from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from backend.models.database import get_db
from backend.api.schemas.task import TaskCreate, TaskResponse, TaskUpdate
from backend.services.tasks.task_service import TaskService
from backend.api.middleware.auth import get_current_user
from backend.models.entities.user import User

router = APIRouter(prefix="/tasks", tags=["tasks"])

@router.post("/", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
async def create_task(
    task_data: TaskCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = TaskService(db)
    task = await service.create_task(current_user.id, task_data)
    return task

@router.get("/", response_model=List[TaskResponse])
async def list_tasks(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = TaskService(db)
    # Convert status string to Enum if provided
    task_status = None
    if status:
        # TODO: Handle string to enum conversion properly
        pass

    tasks = await service.list_tasks(
        user_id=current_user.id,
        # status=task_status, # Skipping for flexibility for now
        skip=skip,
        limit=limit
    )
    return tasks

@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(
    task_id: int,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = TaskService(db)
    task = await service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.user_id != current_user.id and not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Not authorized")
    return task

@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    task_id: int,
    task_data: TaskUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    service = TaskService(db)
    task = await service.update_task(task_id, task_data, current_user.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
