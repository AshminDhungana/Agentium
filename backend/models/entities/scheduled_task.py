"""
Scheduled Task entity for Agentium.
Recurring tasks that survive agent termination/reincarnation.
Owned by Head 00001, executed by ephemeral Task Agents (3xxxx).
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Index
from sqlalchemy.orm import relationship, validates
from .base import BaseEntity
import enum
import json

class ScheduledTaskStatus(str, enum.Enum):
    """Status of a scheduled task."""
    ACTIVE = "active"       # Running normally
    PAUSED = "paused"       # Temporarily stopped
    RUNNING = "running"     # Currently executing
    ERROR = "error"         # Failed multiple times
    COMPLETED = "completed" # One-time schedule finished

class ScheduledTaskExecutionStatus(str, enum.Enum):
    """Status of individual execution."""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    RETRYING = "retrying"

class ScheduledTask(BaseEntity):
    """
    Recurring automation task owned by Head 00001.
    Survives agent termination - ephemeral Task Agents (3xxxx) execute it,
    but the schedule itself persists forever unless deleted.
    """
    
    __tablename__ = 'scheduled_tasks'
    
    __table_args__ = (
        Index('idx_scheduled_next_run', 'next_execution_at'),  # For scheduler queries
        Index('idx_scheduled_owner', 'owner_agentium_id'),     # Head 00001 lookup
        Index('idx_scheduled_status', 'status'),               # Active/paused filtering
    )
    
    # Identification (R0001 format for "Recurring")
    agentium_id = Column(String(10), unique=True, nullable=False)
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Schedule configuration
    cron_expression = Column(String(100), nullable=False)  # "0 9 * * *" or "@daily"
    timezone = Column(String(50), default='UTC')
    
    # Task definition (what to do)
    task_payload = Column(Text, nullable=False)  # JSON: {action_type, params, constraints}
    
    # Ownership - ALWAYS Head 00001 (persistent)
    # This ensures schedule survives even if Council/Leads/Task Agents die
    owner_agentium_id = Column(String(10), nullable=False, default='00001')
    
    # Current execution (nullable - only populated when running)
    executing_agent_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    executing_agent = relationship("Agent", foreign_keys=[executing_agent_id])
    
    # Status
    status = Column(Enum(ScheduledTaskStatus), default=ScheduledTaskStatus.ACTIVE)
    priority = Column(Integer, default=1)  # 1-5, higher = more important
    
    # Execution tracking
    last_execution_at = Column(DateTime, nullable=True)
    next_execution_at = Column(DateTime, nullable=True)  # Calculated from cron
    execution_count = Column(Integer, default=0)
    failure_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Relationships
    execution_history = relationship("ScheduledTaskExecution", 
                                   back_populates="scheduled_task", 
                                   lazy="dynamic",
                                   order_by="ScheduledTaskExecution.started_at.desc()")
    
    def __init__(self, **kwargs):
        if 'agentium_id' not in kwargs:
            # Generate Rxxxx ID
            kwargs['agentium_id'] = self._generate_recurring_id()
        super().__init__(**kwargs)
    
    def _generate_recurring_id(self) -> str:
        """Generate Rxxxx ID for recurring tasks."""
        # Service layer will handle actual ID generation with counter
        import uuid
        return f"R{str(uuid.uuid4().int)[:4]}"
    
    @validates('cron_expression')
    def validate_cron(self, key, cron):
        """Basic cron validation."""
        if cron.startswith('@'):
            valid_special = ['@yearly', '@annually', '@monthly', '@weekly', 
                           '@daily', '@hourly', '@reboot']
            if cron not in valid_special:
                raise ValueError(f"Invalid special cron: {cron}")
        else:
            parts = cron.split()
            if len(parts) != 5:
                raise ValueError("Cron expression must have 5 parts: min hour day month weekday")
        return cron
    
    def get_task_payload(self) -> Dict[str, Any]:
        """Parse task payload JSON."""
        try:
            return json.loads(self.task_payload) if self.task_payload else {}
        except json.JSONDecodeError:
            return {}
    
    def set_task_payload(self, payload: Dict[str, Any]):
        """Set task payload as JSON."""
        self.task_payload = json.dumps(payload)
    
    def calculate_next_run(self) -> Optional[datetime]:
        """Calculate next execution time from cron expression."""
        try:
            from croniter import croniter
            if self.last_execution_at:
                base = self.last_execution_at
            else:
                base = datetime.utcnow()
            itr = croniter(self.cron_expression, base)
            return itr.get_next(datetime)
        except ImportError:
            # Fallback if croniter not installed
            return None
    
    def mark_running(self, agent_id: str, agentium_id: str):
        """Mark as currently executing by a Task Agent."""
        self.status = ScheduledTaskStatus.RUNNING
        self.executing_agent_id = agent_id
    
    def mark_completed(self, success: bool = True):
        """Mark execution complete."""
        now = datetime.utcnow()
        self.last_execution_at = now
        self.execution_count += 1
        self.executing_agent_id = None
        
        if success:
            self.failure_count = 0
            self.status = ScheduledTaskStatus.ACTIVE
            self.next_execution_at = self.calculate_next_run()
        else:
            self.failure_count += 1
            if self.failure_count >= self.max_retries:
                self.status = ScheduledTaskStatus.ERROR
    
    def pause(self):
        """Pause the schedule."""
        self.status = ScheduledTaskStatus.PAUSED
    
    def resume(self):
        """Resume the schedule."""
        if self.status == ScheduledTaskStatus.PAUSED:
            self.status = ScheduledTaskStatus.ACTIVE
            self.next_execution_at = self.calculate_next_run()
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'agentium_id': self.agentium_id,
            'name': self.name,
            'cron_expression': self.cron_expression,
            'timezone': self.timezone,
            'task_payload': self.get_task_payload(),
            'owner_agentium_id': self.owner_agentium_id,
            'status': self.status.value,
            'priority': self.priority,
            'schedule': {
                'last_run': self.last_execution_at.isoformat() if self.last_execution_at else None,
                'next_run': self.next_execution_at.isoformat() if self.next_execution_at else None,
                'execution_count': self.execution_count,
                'failure_count': self.failure_count
            },
            'currently_executing': self.executing_agent.agentium_id if self.executing_agent else None,
            'recent_executions': [ex.to_dict() for ex in self.execution_history.limit(5)]
        })
        return base


class ScheduledTaskExecution(BaseEntity):
    """
    Record of a single execution of a scheduled task.
    Links to the specific Task Agent (3xxxx) that ran it.
    """
    
    __tablename__ = 'scheduled_task_executions'
    
    __table_args__ = (
        Index('idx_sched_exec_task', 'scheduled_task_id'),
        Index('idx_sched_exec_time', 'started_at'),
    )
    
    # Links
    scheduled_task_id = Column(String(36), ForeignKey('scheduled_tasks.id'), nullable=False)
    scheduled_task = relationship("ScheduledTask", back_populates="execution_history")
    
    # Executing agent (ephemeral 3xxxx)
    execution_agentium_id = Column(String(10), nullable=False)
    execution_agent_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    execution_agent = relationship("Agent", foreign_keys=[execution_agent_id])
    
    # Execution details
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    status = Column(Enum(ScheduledTaskExecutionStatus), default=ScheduledTaskExecutionStatus.RUNNING)
    
    # Results
    result_payload = Column(Text, nullable=True)  # JSON result
    error_message = Column(Text, nullable=True)
    retry_number = Column(Integer, default=0)
    
    def complete(self, success: bool, result: Dict[str, Any] = None, error: str = None):
        """Mark execution complete."""
        self.completed_at = datetime.utcnow()
        if success:
            self.status = ScheduledTaskExecutionStatus.SUCCESS
            self.result_payload = json.dumps(result) if result else None
        else:
            self.status = ScheduledTaskExecutionStatus.FAILED
            self.error_message = error
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'scheduled_task_id': self.scheduled_task_id,
            'execution_agentium_id': self.execution_agentium_id,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'duration_seconds': (self.completed_at - self.started_at).total_seconds() if self.completed_at else None,
            'status': self.status.value,
            'result': json.loads(self.result_payload) if self.result_payload else None,
            'error': self.error_message
        })
        return base