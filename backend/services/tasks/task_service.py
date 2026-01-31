from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.models.entities.task import Task, TaskStatus
from backend.api.schemas.task import TaskCreate, TaskUpdate
from backend.services.audit.audit_service import AuditService

class TaskService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.audit = AuditService(db)
    
    async def create_task(self, user_id: int, task_data: TaskCreate) -> Task:
        task = Task(
            user_id=user_id,
            title=task_data.title,
            description=task_data.description,
            priority=task_data.priority,
            status=TaskStatus.PENDING
        )
        self.db.add(task)
        await self.db.commit()
        await self.db.refresh(task)
        
        await self.audit.log_action(
            user_id=user_id,
            action="task_created",
            entity_type="task",
            entity_id=task.id
        )
        
        return task
    
    async def get_task(self, task_id: int) -> Optional[Task]:
        # Using execute() for async query
        result = await self.db.execute(
            select(Task).where(Task.id == task_id)
        )
        return result.scalar_one_or_none()
    
    async def list_tasks(
        self, 
        user_id: Optional[int] = None,
        status: Optional[TaskStatus] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[Task]:
        query = select(Task)
        
        if user_id:
            query = query.where(Task.user_id == user_id)
        if status:
            query = query.where(Task.status == status)
        
        query = query.offset(skip).limit(limit).order_by(Task.created_at.desc())
        
        result = await self.db.execute(query)
        return result.scalars().all()
    
    async def update_task(
        self, 
        task_id: int, 
        task_data: TaskUpdate,
        user_id: int
    ) -> Optional[Task]:
        task = await self.get_task(task_id)
        if not task:
            return None
        
        update_data = task_data.dict(exclude_unset=True)
        for field, value in update_data.items():
            setattr(task, field, value)
        
        await self.db.commit()
        await self.db.refresh(task)
        
        await self.audit.log_action(
            user_id=user_id,
            action="task_updated",
            entity_type="task",
            entity_id=task.id
        )
        
        return task
