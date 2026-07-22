import enum
from datetime import datetime
from typing import Dict, Any
from sqlalchemy import Column, String, Integer, Text, JSON, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship

from .base import BaseEntity

class WorkflowExecutionStatus(str, enum.Enum):
    """Lifecycle states for a workflow execution."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class WorkflowStepType(str, enum.Enum):
    """Types of steps a workflow can execute."""
    TASK           = "task"
    CONDITION      = "condition"
    PARALLEL       = "parallel"
    HUMAN_APPROVAL = "human_approval"
    DELAY          = "delay"
    WAIT_POLL      = "wait_poll"   # Phase 16: suspend until a WaitCondition resolves


class Workflow(BaseEntity):
    """
    Defines a repeatable automated workflow template.
    A workflow consists of multiple steps that can be run on a schedule,
    by an event, or manually.
    """
    __tablename__ = 'workflows'
    
    name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    template_json = Column(JSON, nullable=False, default=dict)
    version = Column(Integer, default=1, nullable=False)
    created_by_agent_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    schedule_cron = Column(String(100), nullable=True)
    
    # Relationships
    executions = relationship("WorkflowExecution", back_populates="workflow", lazy="dynamic", cascade="all, delete-orphan")
    steps = relationship("WorkflowStep", back_populates="workflow", lazy="dynamic", cascade="all, delete-orphan")
    versions = relationship("WorkflowVersion", back_populates="workflow", lazy="dynamic", cascade="all, delete-orphan")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = self._generate_workflow_id()

    def _generate_workflow_id(self) -> str:
        """Generate workflow ID: WF + 5-digit sequence."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM workflows 
                WHERE agentium_id ~ '^WF[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC 
                LIMIT 1
            """)).scalar()
            
            if result:
                last_num = int(result[2:])
                next_num = last_num + 1
            else:
                next_num = 1
                
            return f"WF{next_num:05d}"
            
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'name': self.name,
            'description': self.description,
            'template_json': self.template_json,
            'version': self.version,
            'schedule_cron': self.schedule_cron,
            'created_by_agent_id': self.created_by_agent_id
        })
        return base


class WorkflowExecution(BaseEntity):
    """
    Tracks a specific run (execution) of a workflow.
    """
    __tablename__ = 'workflow_executions'
    
    workflow_id = Column(String(36), ForeignKey('workflows.id'), nullable=False, index=True)
    status = Column(Enum(WorkflowExecutionStatus), default=WorkflowExecutionStatus.PENDING, nullable=False, index=True)
    current_step_index = Column(Integer, default=0, nullable=False)
    context_data = Column(JSON, default=dict)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    triggered_by = Column(String(100), nullable=True)
    
    # Relationships
    workflow = relationship("Workflow", back_populates="executions")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = self._generate_execution_id()

    def _generate_execution_id(self) -> str:
        """Generate execution ID: WX + 5-digit sequence."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM workflow_executions 
                WHERE agentium_id ~ '^WX[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC 
                LIMIT 1
            """)).scalar()
            
            if result:
                last_num = int(result[2:])
                next_num = last_num + 1
            else:
                next_num = 1
                
            return f"WX{next_num:05d}"
            
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'workflow_id': self.workflow_id,
            'status': self.status.value,
            'current_step_index': self.current_step_index,
            'context_data': self.context_data,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'triggered_by': self.triggered_by
        })
        return base


class WorkflowStep(BaseEntity):
    """
    Defines an individual step within a Workflow.
    """
    __tablename__ = 'workflow_steps'
    
    workflow_id = Column(String(36), ForeignKey('workflows.id'), nullable=False, index=True)
    step_index = Column(Integer, nullable=False)
    step_type = Column(Enum(WorkflowStepType), nullable=False)
    config = Column(JSON, default=dict, nullable=False)
    on_success_step = Column(Integer, nullable=True)
    on_failure_step = Column(Integer, nullable=True)
    
    # Relationships
    workflow = relationship("Workflow", back_populates="steps")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = self._generate_step_id()

    def _generate_step_id(self) -> str:
        """Generate step ID: WS + 5-digit sequence."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM workflow_steps 
                WHERE agentium_id ~ '^WS[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC 
                LIMIT 1
            """)).scalar()
            
            if result:
                last_num = int(result[2:])
                next_num = last_num + 1
            else:
                next_num = 1
                
            return f"WS{next_num:05d}"
            
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'workflow_id': self.workflow_id,
            'step_index': self.step_index,
            'step_type': self.step_type.value,
            'config': self.config,
            'on_success_step': self.on_success_step,
            'on_failure_step': self.on_failure_step
        })
        return base


class WorkflowVersion(BaseEntity):
    """
    An audit table to keep historical snapshots of Workflow definitions
    when they are edited.
    """
    __tablename__ = 'workflow_versions'
    
    workflow_id = Column(String(36), ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False, index=True)
    version = Column(Integer, nullable=False)
    template_json = Column(JSON, nullable=False)
    
    # Relationships
    workflow = relationship("Workflow", back_populates="versions")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = self._generate_version_id()

    def _generate_version_id(self) -> str:
        """Generate version ID: WV + 5-digit sequence."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM workflow_versions 
                WHERE agentium_id ~ '^WV[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC 
                LIMIT 1
            """)).scalar()
            
            if result:
                last_num = int(result[2:])
                next_num = last_num + 1
            else:
                next_num = 1
                
            return f"WV{next_num:05d}"
            
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'workflow_id': self.workflow_id,
            'version': self.version,
            'template_json': self.template_json
        })
        return base


# ── WorkflowSubTask ───────────────────────────────────────────────────────────
# New class required by the Phase 13 import in database.py.
# Maps to the workflow_subtasks table created by migration 011_fix_workflow.
# No existing code above this line has been changed.

class WorkflowSubTask(BaseEntity):
    """
    One atomic sub-task within a WorkflowExecution (Phase 13 DAG engine).
    FK workflow_id → workflows.id (matches WorkflowExecution's FK chain).
    """
    __tablename__ = 'workflow_subtasks'

    workflow_id          = Column(String(36), ForeignKey('workflows.id', ondelete='CASCADE'), nullable=False, index=True)
    step_index           = Column(Integer,    nullable=False, server_default='0')
    intent               = Column(String(128), nullable=False)
    params               = Column(JSON,        nullable=False, default=dict)
    depends_on           = Column(JSON,        nullable=False, default=list)
    status               = Column(String(32),  nullable=False, server_default='pending', index=True)
    result               = Column(JSON,        nullable=True)
    error                = Column(Text,        nullable=True)
    celery_task_id       = Column(String(256), nullable=True)
    schedule_offset_days = Column(Integer,     nullable=False, server_default='0')
    scheduled_for        = Column(DateTime,    nullable=True)
    completed_at         = Column(DateTime,    nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'workflow_id':          self.workflow_id,
            'step_index':           self.step_index,
            'intent':               self.intent,
            'params':               self.params,
            'depends_on':           self.depends_on,
            'status':               self.status,
            'result':               self.result,
            'error':                self.error,
            'celery_task_id':       self.celery_task_id,
            'schedule_offset_days': self.schedule_offset_days,
            'scheduled_for':        self.scheduled_for.isoformat() if self.scheduled_for else None,
            'completed_at':         self.completed_at.isoformat() if self.completed_at else None,
        })
        return base