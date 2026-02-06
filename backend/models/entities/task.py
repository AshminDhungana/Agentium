"""
Task management for Agentium.
Includes IDLE TASK support for continuous background optimization.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, JSON
from sqlalchemy.orm import relationship, validates
from backend.models.entities.base import BaseEntity
from backend.models.entities.agents import Agent  
import enum

class TaskPriority(str, enum.Enum):
    """Task priority levels."""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    IDLE = "idle"  # NEW: Background optimization priority (lowest)

class TaskStatus(str, enum.Enum):
    """Task lifecycle states."""
    PENDING = "pending"
    DELIBERATING = "deliberating"
    APPROVED = "approved"
    REJECTED = "rejected"
    DELEGATING = "delegating"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # IDLE-specific states
    IDLE_PENDING = "idle_pending"      # Waiting for idle time
    IDLE_RUNNING = "idle_running"      # Being processed by persistent agent
    IDLE_PAUSED = "idle_paused"        # Interrupted by user task
    IDLE_COMPLETED = "idle_completed"  # Successfully finished in idle mode

class TaskType(str, enum.Enum):
    """Categories of tasks."""
    CONSTITUTIONAL = "constitutional"
    SYSTEM = "system"
    EXECUTION = "execution"
    RESEARCH = "research"
    AUTOMATION = "automation"
    ANALYSIS = "analysis"
    COMMUNICATION = "communication"
    CONSTITUTION_READ = "constitution_read" 
    # IDLE OPTIMIZATION TASKS (NEW)
    VECTOR_MAINTENANCE = "vector_maintenance"      # ChromaDB optimization
    STORAGE_DEDUPE = "storage_dedupe"              # Database deduplication
    AUDIT_ARCHIVAL = "audit_archival"              # Log compression/archival
    PREDICTIVE_PLANNING = "predictive_planning"    # Future task prediction
    CONSTITUTION_REFINE = "constitution_refine"    # Constitutional amendments
    AGENT_HEALTH_SCAN = "agent_health_scan"        # Proactive health checks
    ETHOS_OPTIMIZATION = "ethos_optimization"      # Ethos refinement
    CACHE_OPTIMIZATION = "cache_optimization"      # Redis/vector cache tuning


class Task(BaseEntity):
    """Central task entity with IDLE GOVERNANCE support."""
    
    __tablename__ = 'tasks'
    
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    task_type = Column(Enum(TaskType), default=TaskType.EXECUTION, nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.NORMAL, nullable=False)
    
    # IDLE-specific flag (NEW)
    is_idle_task = Column(Boolean, default=False, nullable=False, index=True)
    idle_task_category = Column(String(50), nullable=True)  # e.g., "storage", "planning", "maintenance"
    estimated_tokens = Column(Integer, default=0)  # For token budget management
    tokens_used = Column(Integer, default=0)  # Actual tokens consumed
    
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    status_history = Column(JSON, default=list)
    
    created_by = Column(String(10), nullable=False)
    head_of_council_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    assigned_council_ids = Column(JSON, default=list)
    lead_agent_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    assigned_task_agent_ids = Column(JSON, default=list)
    
    requires_deliberation = Column(Boolean, default=True)
    deliberation_id = Column(String(36), ForeignKey('task_deliberations.id'), nullable=True)
    approved_by_council = Column(Boolean, default=False)
    approved_by_head = Column(Boolean, default=False)
    
    execution_plan = Column(Text, nullable=True)
    execution_context = Column(Text, nullable=True)
    tools_allowed = Column(JSON, default=list)
    sandbox_mode = Column(Boolean, default=True)
    
    result_summary = Column(Text, nullable=True)
    result_data = Column(JSON, nullable=True)
    result_files = Column(JSON, nullable=True)
    completion_percentage = Column(Integer, default=0)
    
    due_date = Column(DateTime, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    time_estimated = Column(Integer, default=0)
    time_actual = Column(Integer, default=0)
    
    error_count = Column(Integer, default=0)
    last_error = Column(Text, nullable=True)
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    head_of_council = relationship("Agent", foreign_keys=[head_of_council_id], lazy="joined")
    lead_agent = relationship("Agent", foreign_keys=[lead_agent_id])
    deliberation = relationship(
    "TaskDeliberation",
    primaryjoin="Task.deliberation_id == TaskDeliberation.id",
    foreign_keys=[deliberation_id],
    back_populates="task",
    uselist=False
    )
    subtasks = relationship("SubTask", back_populates="parent_task", lazy="dynamic")
    audit_logs = relationship("TaskAuditLog", back_populates="task", lazy="dynamic")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Auto-generate ID
        if not kwargs.get('agentium_id'):
            self.agentium_id = self._generate_task_id()
        
        # Auto-flag idle tasks based on type
        idle_types = [
            TaskType.VECTOR_MAINTENANCE,
            TaskType.STORAGE_DEDUPE,
            TaskType.AUDIT_ARCHIVAL,
            TaskType.PREDICTIVE_PLANNING,
            TaskType.CONSTITUTION_REFINE,
            TaskType.AGENT_HEALTH_SCAN,
            TaskType.ETHOS_OPTIMIZATION,
            TaskType.CACHE_OPTIMIZATION
        ]
        if self.task_type in idle_types:
            self.is_idle_task = True
            self.priority = TaskPriority.IDLE
            self.requires_deliberation = False  # Idle tasks skip deliberation
    
    def _generate_task_id(self) -> str:
        """Generate task ID: T + timestamp + random."""
        timestamp = datetime.utcnow().strftime('%Y%m%d%H%M')
        random_suffix = str(hash(self.description))[-4:]
        return f"T{timestamp}{random_suffix}"
    
    @validates('priority')
    def validate_priority(self, key, priority):
        """Critical tasks skip deliberation. Idle tasks skip deliberation."""
        if priority in [TaskPriority.CRITICAL, TaskPriority.IDLE]:
            self.requires_deliberation = False
        return priority
    
    def start_idle_execution(self, agent_id: str):
        """Mark task for idle execution."""
        if not self.is_idle_task:
            raise ValueError("Not an idle task")
        
        self.status = TaskStatus.IDLE_RUNNING
        self.started_at = datetime.utcnow()
        self._log_status_change("idle_started", agent_id)
    
    def pause_for_user_task(self):
        """Pause idle task when user task arrives."""
        if self.status == TaskStatus.IDLE_RUNNING:
            self.status = TaskStatus.IDLE_PAUSED
            self._log_status_change("idle_paused", "System", "User task priority")
    
    def resume_idle_task(self):
        """Resume paused idle task."""
        if self.status == TaskStatus.IDLE_PAUSED:
            self.status = TaskStatus.IDLE_RUNNING
            self._log_status_change("idle_resumed", "System")
    
    def complete_idle(self, result_summary: str, tokens_used: int = 0):
        """Complete idle task."""
        self.status = TaskStatus.IDLE_COMPLETED
        self.result_summary = result_summary
        self.completed_at = datetime.utcnow()
        self.tokens_used = tokens_used
        
        if self.started_at:
            self.time_actual = int((self.completed_at - self.started_at).total_seconds())
        
        self._log_status_change("idle_completed", self.assigned_task_agent_ids[0] if self.assigned_task_agent_ids else "System")
    
    def start_deliberation(self, council_member_ids: List[str]) -> 'TaskDeliberation':
        """Start council deliberation."""
        if self.is_idle_task:
            raise ValueError("Idle tasks do not require deliberation")
        
        if not self.requires_deliberation:
            raise ValueError("This task does not require deliberation")
        
        from backend.models.entities.voting import TaskDeliberation
        
        self.status = TaskStatus.DELIBERATING
        self.assigned_council_ids = council_member_ids
        self._log_status_change("deliberation_started", "System")
        
        deliberation = TaskDeliberation(
            task_id=self.id,
            agentium_id=f"D{self.agentium_id[1:]}",
            participating_members=council_member_ids,
            required_approvals=max(2, len(council_member_ids) // 2 + 1)
        )
        
        return deliberation
    
    def approve_by_council(self, votes_for: int, votes_against: int):
        """Mark task as council-approved."""
        if votes_for > votes_against:
            self.approved_by_council = True
            self.status = TaskStatus.APPROVED
            self._log_status_change("council_approved", "Council")
        else:
            self.status = TaskStatus.REJECTED
            self._log_status_change("council_rejected", "Council")
    
    def approve_by_head(self, head_agentium_id: str):
        """Final Head of Council approval."""
        self.approved_by_head = True
        self.head_of_council_id = head_agentium_id
        self.status = TaskStatus.DELEGATING
        self._log_status_change("head_approved", head_agentium_id)
    
    def delegate_to_lead(self, lead_agent_id: str):
        """Assign task to Lead Agent."""
        self.lead_agent_id = lead_agent_id
        self.status = TaskStatus.ASSIGNED
        self._log_status_change("delegated_to_lead", lead_agent_id)
        self._auto_generate_subtasks()
    
    def _auto_generate_subtasks(self):
        """Auto-break task into subtasks."""
        subtask = SubTask(
            parent_task_id=self.id,
            title=f"Execute: {self.title}",
            description=self.description,
            agentium_id=f"S{self.agentium_id[1:]}01",
            sequence=1
        )
        return [subtask]
    
    def assign_to_task_agents(self, task_agent_ids: List[str]):
        """
        Assign subtasks to Task Agents - IMMEDIATE assignment.
        Pre-task ritual is FAST (Constitution awareness only).
        """
        # Assign immediately - no blocking operations
        self.assigned_task_agent_ids = task_agent_ids
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
        
        # Quick pre-task check (non-blocking)
        from backend.models.database import get_db_context
        with get_db_context() as db:
            for agent_id in task_agent_ids:
                agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
                if agent:
                    # FAST: Only Constitution awareness, no ethos execution
                    ritual = agent.pre_task_ritual(db)
                    if ritual["constitution_refreshed"]:
                        print(f"📖 Agent {agent_id} refreshed Constitution awareness (v{ritual['constitution_version']})")
        
        self._log_status_change("execution_started", self.lead_agent_id)

    def complete(self, result_summary: str, result_data: Dict = None):
        """Mark task as completed - Ethos execution happens here (post-task)."""
        from backend.models.database import get_db_context
        
        self.status = TaskStatus.COMPLETED
        self.result_summary = result_summary
        self.result_data = result_data or {}
        self.completion_percentage = 100
        self.completed_at = datetime.utcnow()
        
        if self.started_at:
            self.time_actual = int((self.completed_at - self.started_at).total_seconds())
        
        # Update agents and trigger post-task rituals (ethos execution)
        with get_db_context() as db:
            if self.assigned_task_agent_ids:
                for agent_id in self.assigned_task_agent_ids:
                    agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
                    if agent:
                        # Mark task complete on agent
                        agent.complete_task(success=True)
                        
                        # POST-TASK: Execute ethos updates (self-improvement)
                        # This doesn't block next assignment since task is already done
                        post_results = agent.post_task_ritual(db)
                        
                        if post_results["ethos_executed"]:
                            print(f"✨ Agent {agent_id} completed {post_results['ethos_tasks_completed']} ethos improvements")
                        if post_results["constitution_refreshed"]:
                            print(f"📖 Agent {agent_id} refreshed Constitution (post-task)")
        
        self._log_status_change("completed", self.assigned_task_agent_ids[0] if self.assigned_task_agent_ids else "System")
        self._update_agent_stats(success=True)
    
    def update_progress(self, percentage: int, note: str = None):
        """Update task completion percentage."""
        self.completion_percentage = min(100, max(0, percentage))
        if note:
            self._log_status_change(f"progress_{percentage}%", "System", note)
    
    def complete(self, result_summary: str, result_data: Dict = None):
        """Mark task as completed."""
        self.status = TaskStatus.COMPLETED
        self.result_summary = result_summary
        self.result_data = result_data or {}
        self.completion_percentage = 100
        self.completed_at = datetime.utcnow()
        
        if self.started_at:
            self.time_actual = int((self.completed_at - self.started_at).total_seconds())
        
        self._log_status_change("completed", self.assigned_task_agent_ids[0] if self.assigned_task_agent_ids else "System")
        self._update_agent_stats(success=True)
    
    def fail(self, error_message: str, can_retry: bool = True):
        """Mark task as failed."""
        self.error_count += 1
        self.last_error = error_message
        
        if can_retry and self.retry_count < self.max_retries:
            self.retry_count += 1
            self.status = TaskStatus.ASSIGNED
            self._log_status_change("retrying", "System", f"Retry {self.retry_count}/{self.max_retries}: {error_message}")
        else:
            self.status = TaskStatus.FAILED
            self._log_status_change("failed", "System", error_message)
            self._update_agent_stats(success=False)
    
    def _update_agent_stats(self, success: bool):
        """Update statistics for assigned agents."""
        pass
    
    def _log_status_change(self, new_status: str, agent_id: str, note: str = None):
        """Append to status history."""
        history = self.status_history or []
        history.append({
            'status': new_status,
            'timestamp': datetime.utcnow().isoformat(),
            'agent_id': agent_id,
            'note': note
        })
        self.status_history = history
    
    def cancel(self, reason: str, cancelled_by: str):
        """Cancel task."""
        if self.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]:
            raise ValueError("Cannot cancel completed or failed task")
        
        self.status = TaskStatus.CANCELLED
        self._log_status_change("cancelled", cancelled_by, reason)
        self.is_active = 'N'
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'title': self.title,
            'description': self.description,
            'type': self.task_type.value,
            'priority': self.priority.value,
            'status': self.status.value,
            'progress': self.completion_percentage,
            'created_by': self.created_by,
            'is_idle_task': self.is_idle_task,
            'idle_category': self.idle_task_category,
            'token_usage': {
                'estimated': self.estimated_tokens,
                'used': self.tokens_used
            },
            'assigned_agents': {
                'head': self.head_of_council_id,
                'lead': self.lead_agent_id,
                'task_agents': self.assigned_task_agent_ids
            },
            'deliberation': {
                'required': self.requires_deliberation,
                'council_approved': self.approved_by_council,
                'head_approved': self.approved_by_head
            },
            'timing': {
                'created': self.created_at.isoformat() if self.created_at else None,
                'started': self.started_at.isoformat() if self.started_at else None,
                'due': self.due_date.isoformat() if self.due_date else None,
                'completed': self.completed_at.isoformat() if self.completed_at else None
            },
            'result': {
                'summary': self.result_summary,
                'data': self.result_data,
                'files': self.result_files
            } if self.status == TaskStatus.COMPLETED else None,
            'history': self.status_history
        })
        return base


class SubTask(BaseEntity):
    """Atomic unit of work."""
    
    __tablename__ = 'subtasks'
    
    parent_task_id = Column(String(36), ForeignKey('tasks.id'), nullable=False)
    assigned_agent_id = Column(String(36), ForeignKey('agents.id'), nullable=True)
    
    sequence = Column(Integer, nullable=False)
    dependencies = Column(JSON, default=list)
    
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    expected_output = Column(Text, nullable=True)
    
    status = Column(Enum(TaskStatus), default=TaskStatus.PENDING, nullable=False)
    tools_allowed = Column(JSON, default=list)
    
    result = Column(Text, nullable=True)
    output_data = Column(JSON, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    max_duration = Column(Integer, default=300)
    started_at = Column(DateTime, nullable=True)
    
    parent_task = relationship("Task", back_populates="subtasks")
    assigned_agent = relationship("Agent")
    
    def can_start(self) -> bool:
        """Check if dependencies are satisfied."""
        return True
    
    def start_execution(self, agent_id: str):
        """Mark subtask as started."""
        self.assigned_agent_id = agent_id
        self.status = TaskStatus.IN_PROGRESS
        self.started_at = datetime.utcnow()
    
    def complete(self, result: str, output_data: Dict = None):
        """Complete subtask."""
        self.status = TaskStatus.COMPLETED
        self.result = result
        self.output_data = output_data
        self.completed_at = datetime.utcnow()
        self._check_parent_completion()
    
    def _check_parent_completion(self):
        """Check if all sibling subtasks are done."""
        siblings = self.parent_task.subtasks.all()
        all_completed = all(s.status == TaskStatus.COMPLETED for s in siblings)
        
        if all_completed:
            combined_result = "\\n".join([s.result for s in siblings if s.result])
            self.parent_task.complete(
                result_summary=combined_result,
                result_data={s.agentium_id: s.output_data for s in siblings}
            )
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'parent_task': self.parent_task.agentium_id if self.parent_task else None,
            'sequence': self.sequence,
            'title': self.title,
            'status': self.status.value,
            'assigned_to': self.assigned_agent.agentium_id if self.assigned_agent else None,
            'result': self.result
        })
        return base


class TaskAuditLog(BaseEntity):
    """Detailed audit trail for task execution."""
    
    __tablename__ = 'task_audit_logs'
    
    task_id = Column(String(36), ForeignKey('tasks.id'), nullable=False)
    agentium_id = Column(String(10), nullable=False)
    
    action = Column(String(50), nullable=False)
    action_details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    user_agent = Column(String(200), nullable=True)
    
    task = relationship("Task", back_populates="audit_logs")
    
    @classmethod
    def log_action(cls, task_id: str, agentium_id: str, action: str, details: Dict = None):
        """Factory method to create audit log entry."""
        return cls(
            task_id=task_id,
            agentium_id=agentium_id,
            action=action,
            action_details=details or {}
        )
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'task_id': self.task_id,
            'agent': self.agentium_id,
            'action': self.action,
            'details': self.action_details,
            'timestamp': self.created_at.isoformat()
        })
        return base
