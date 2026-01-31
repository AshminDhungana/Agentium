from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
import enum
from backend.models.database import Base

class TaskStatus(str, enum.Enum):
    PENDING = "pending"
    VOTING = "voting"
    APPROVED = "approved"
    REJECTED = "rejected"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

class Task(Base):
    __tablename__ = "tasks"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    title = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING)
    priority = Column(Integer, default=5)
    assigned_agent_id = Column(Integer, nullable=True) # Check foreign key later
    result = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    completed_at = Column(DateTime(timezone=True), nullable=True)
    
    # Relationships will be added as we create other models
    # user = relationship("User", back_populates="tasks")
