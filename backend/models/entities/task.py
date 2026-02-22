"""
Task management for Agentium.
Includes IDLE TASK support for continuous background optimization.
Updated for Task Execution Architecture: Governance Alignment
"""

from datetime import datetime
from typing import List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, JSON
from sqlalchemy.orm import relationship, validates
from backend.models.entities.base import BaseEntity
from backend.models.entities.agents import Agent  
import enum

class TaskPriority(str, enum.Enum):
    """Task priority levels."""
    SOVEREIGN = "sovereign"    # Highest priority - skips all governance
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"
    IDLE = "idle"  # Background optimization priority (lowest)

class TaskStatus(str, enum.Enum):
    """Task lifecycle states - Governance Architecture Aligned."""
    # Initial states
    PENDING = "pending"
    DELIBERATING = "deliberating"
    APPROVED = "approved"
    REJECTED = "rejected"
    
    # Delegation states
    DELEGATING = "delegating"
    ASSIGNED = "assigned"
    
    # Execution states
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    
    # Completion states
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    
    # Failure & Recovery states (NEW)
    FAILED = "failed"
    RETRYING = "retrying"      # NEW: Task is being retried after failure
    ESCALATED = "escalated"    # NEW: Max retries exceeded, escalated to Council
    STOPPED = "stopped"        # NEW: Task manually stopped or liquidated
    
    # IDLE-specific states
    IDLE_PENDING = "idle_pending"
    IDLE_RUNNING = "idle_running"
    IDLE_PAUSED = "idle_paused"
    IDLE_COMPLETED = "idle_completed"

class TaskType(str, enum.Enum):
    """Categories of tasks."""
    # Governance types
    CONSTITUTIONAL = "constitutional"
    SYSTEM = "system"
    
    # User task types (NEW)
    ONE_TIME = "one_time"      # NEW: Single execution task
    RECURRING = "recurring"    # NEW: Recurring scheduled task
    
    # Execution types
    EXECUTION = "execution"
    RESEARCH = "research"
    AUTOMATION = "automation"
    ANALYSIS = "analysis"
    COMMUNICATION = "communication"
    CONSTITUTION_READ = "constitution_read"
    
    # IDLE optimization tasks
    VECTOR_MAINTENANCE = "vector_maintenance"
    STORAGE_DEDUPE = "storage_dedupe"
    AUDIT_ARCHIVAL = "audit_archival"
    PREDICTIVE_PLANNING = "predictive_planning"
    CONSTITUTION_REFINE = "constitution_refine"
    AGENT_HEALTH_SCAN = "agent_health_scan"
    ETHOS_OPTIMIZATION = "ethos_optimization"
    CACHE_OPTIMIZATION = "cache_optimization"
    IDLE_COMPLETED = "idle_completed"
    IDLE_PAUSED = "idle_paused"


class Task(BaseEntity):
    """Central task entity with IDLE GOVERNANCE support and Governance Architecture."""
    
    __tablename__ = 'tasks'
    
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=False)
    task_type = Column(Enum(TaskType), default=TaskType.EXECUTION, nullable=False)
    priority = Column(Enum(TaskPriority), default=TaskPriority.NORMAL, nullable=False)
    
    # NEW: Constitutional governance fields
    constitutional_basis = Column(Text, nullable=True)  # Reason task is constitutionally valid
    hierarchical_id = Column(String(100), nullable=True)  # NEW: Dot-notated ID for tracking
    recurrence_pattern = Column(String(100), nullable=True)  # Cron expression for recurring tasks
    
    # Hierarchical task structure (NEW)
    parent_task_id = Column(String(36), ForeignKey('tasks.id'), nullable=True)
    execution_plan_id = Column(String(36), nullable=True)  # Link to execution plan
    
    # IDLE-specific flag
    is_idle_task = Column(Boolean, default=False, nullable=False, index=True)
    idle_task_category = Column(String(50), nullable=True)
    estimated_tokens = Column(Integer, default=0)
    tokens_used = Column(Integer, default=0)
    
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
    max_retries = Column(Integer, default=5)  # UPDATED: from 3 to 5

    # ── Phase 6.3: Pre-Declared Acceptance Criteria ──────────────────────────
    # Stored as a JSON array of AcceptanceCriterion dicts.
    # Populated at task-creation time; validated by critic agents on review.
    acceptance_criteria = Column(JSON, nullable=True)

    # Which critic type has veto authority over this task's output.
    # Values: "code" | "output" | "plan"  (maps to CriticType enum)
    veto_authority = Column(String(20), nullable=True)
    
    # Relationships
    head_of_council = relationship("Agent", foreign_keys=[head_of_council_id], lazy="joined")
    lead_agent = relationship("Agent", foreign_keys=[lead_agent_id])
    deliberation = relationship(
        "TaskDeliberation",
        primaryjoin="Task.deliberation_id == TaskDeliberation.id",
        foreign_keys=[deliberation_id],
        back_populates="task",
        uselist=False
    )
    # NEW: Parent-child relationship
    parent_task = relationship("Task", remote_side="Task.id", backref="child_tasks")
    subtasks = relationship("SubTask", back_populates="parent_task", lazy="dynamic")
    audit_logs = relationship("TaskAuditLog", back_populates="task", lazy="dynamic")
    # NEW: Event sourcing relationship
    events = relationship("TaskEvent", back_populates="task", lazy="dynamic", order_by="TaskEvent.created_at")
    # Phase 6.6: Remote code executions
    remote_executions = relationship("RemoteExecutionRecord", back_populates="task", lazy="dynamic")
    
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
        
        # Sovereign priority skips all governance
        if self.priority == TaskPriority.SOVEREIGN:
            self.requires_deliberation = False
            self.approved_by_council = True
            self.approved_by_head = True
    
    def _generate_task_id(self) -> str:
        """Generate task ID: T + 5-digit sequence number."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM tasks 
                WHERE agentium_id ~ '^T[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 2) AS INTEGER) DESC 
                LIMIT 1
            """)).scalar()
            
            if result:
                last_num = int(result[1:])  # Remove 'T' prefix
                next_num = last_num + 1
            else:
                next_num = 1
                
            return f"T{next_num:05d}"
    
    @validates('priority')
    def validate_priority(self, _, priority):
        """Critical and Sovereign tasks skip deliberation. Idle tasks skip deliberation."""
        if priority in [TaskPriority.CRITICAL, TaskPriority.SOVEREIGN, TaskPriority.IDLE]:
            self.requires_deliberation = False
        return priority
    
    def set_status(self, new_status: TaskStatus, actor_id: str = "system", note: str = None):
        """
        Set task status with state machine validation.
        This is the ONLY way to change status - enforces legal transitions.
        """
        from backend.services.task_state_machine import TaskStateMachine
        
        # Validate transition
        TaskStateMachine.validate_transition(self.status, new_status)
        
        # Update status
        old_status = self.status
        self.status = new_status
        
        # Log the change
        self._log_status_change(new_status.value, actor_id, note)
        
        # Emit event for event sourcing
        self._emit_status_event(old_status, new_status, actor_id, note)
        
        # Phase 6.5: Automated Checkpoint hook
        self._trigger_checkpoint_if_needed(new_status, actor_id)
        
        return True
        
    def _trigger_checkpoint_if_needed(self, new_status: TaskStatus, actor_id: str):
        """Creates a system state checkpoint at key phase boundaries."""
        from sqlalchemy.orm import object_session
        from backend.services.checkpoint_service import CheckpointService
        from backend.models.entities.checkpoint import CheckpointPhase

        session = object_session(self)
        if not session:
            return  # Cannot create checkpoint if detached
            
        phase = None
        if new_status == TaskStatus.IN_PROGRESS:
            phase = CheckpointPhase.PLAN_APPROVED
        elif new_status == TaskStatus.REVIEW:
            phase = CheckpointPhase.EXECUTION_COMPLETE
        elif new_status == TaskStatus.COMPLETED:
            phase = CheckpointPhase.CRITIQUE_PASSED
            
        if phase:
            try:
                CheckpointService.create_checkpoint(
                    db=session,
                    task_id=self.id,
                    phase=phase,
                    actor_id=actor_id
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).error(f"Failed to create checkpoint for task {self.id}: {e}")
    
    def _emit_status_event(self, old_status: TaskStatus, new_status: TaskStatus, actor_id: str, note: str = None):
        """Emit event for event sourcing."""
        from backend.models.entities.task_events import TaskEvent, TaskEventType
        
        event = TaskEvent(
            task_id=self.id,
            event_type=TaskEventType.STATUS_CHANGED,
            actor_id=actor_id,
            data={
                "old_status": old_status.value if old_status else None,
                "new_status": new_status.value,
                "note": note
            }
        )
        # Add to events relationship so it's persisted
        self.events.append(event)
    
    def start_idle_execution(self, agent_id: str):
        """Mark task for idle execution."""
        if not self.is_idle_task:
            raise ValueError("Not an idle task")
        
        self.set_status(TaskStatus.IDLE_RUNNING, agent_id)
        self.started_at = datetime.utcnow()
    
    def pause_for_user_task(self):
        """Pause idle task when user task arrives."""
        if self.status == TaskStatus.IDLE_RUNNING:
            self.set_status(TaskStatus.IDLE_PAUSED, "System", "User task priority")
    
    def resume_idle_task(self):
        """Resume paused idle task."""
        if self.status == TaskStatus.IDLE_PAUSED:
            self.set_status(TaskStatus.IDLE_RUNNING, "System")
    
    def complete_idle(self, result_summary: str, tokens_used: int = 0):
        """Complete idle task."""
        self.set_status(TaskStatus.IDLE_COMPLETED, self.assigned_task_agent_ids[0] if self.assigned_task_agent_ids else "System")
        self.result_summary = result_summary
        self.completed_at = datetime.utcnow()
        self.tokens_used = tokens_used
        
        if self.started_at:
            self.time_actual = int((self.completed_at - self.started_at).total_seconds())
    
    def start_deliberation(self, council_member_ids: List[str]) -> 'TaskDeliberation':
        """Start council deliberation."""
        if self.is_idle_task:
            raise ValueError("Idle tasks do not require deliberation")
        
        if not self.requires_deliberation:
            raise ValueError("This task does not require deliberation")
        
        from backend.models.entities.voting import TaskDeliberation
        
        self.set_status(TaskStatus.DELIBERATING, "System", f"Council members: {', '.join(council_member_ids)}")
        self.assigned_council_ids = council_member_ids
        
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
            self.set_status(TaskStatus.APPROVED, "Council", f"Votes: {votes_for} for, {votes_against} against")
        else:
            self.set_status(TaskStatus.REJECTED, "Council", f"Votes: {votes_for} for, {votes_against} against")
    
    def approve_by_head(self, head_agentium_id: str):
        """Final Head of Council approval."""
        self.approved_by_head = True
        self.head_of_council_id = head_agentium_id
        self.set_status(TaskStatus.DELEGATING, head_agentium_id)
    
    def delegate_to_lead(self, lead_agent_id: str):
        """Assign task to Lead Agent."""
        self.lead_agent_id = lead_agent_id
        self.set_status(TaskStatus.ASSIGNED, lead_agent_id)
        self._auto_generate_subtasks()
    
    def _auto_generate_subtasks(self):
        """Auto-break task into subtasks."""
        subtask = SubTask(
            parent_task_id=self.id,
            title=f"Execute: {self.title}",
            description=self.description,
            agentium_id=f"S{self.agentium_id[1:]}",
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
        self.set_status(TaskStatus.IN_PROGRESS, self.lead_agent_id or "System")
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

    def complete(self, result_summary: str, result_data: Dict = None):
        """Mark task as completed - Ethos execution happens here (post-task)."""
        from backend.models.database import get_db_context
        
        self.set_status(TaskStatus.COMPLETED, self.assigned_task_agent_ids[0] if self.assigned_task_agent_ids else "System")
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
                        post_results = agent.post_task_ritual(db)
                        
                        if post_results["ethos_executed"]:
                            print(f"✨ Agent {agent_id} completed {post_results['ethos_tasks_completed']} ethos improvements")
                        if post_results["constitution_refreshed"]:
                            print(f"📖 Agent {agent_id} refreshed Constitution (post-task)")
        
        self._update_agent_stats(success=True)
    
    def update_progress(self, percentage: int, note: str = None):
        """Update task completion percentage."""
        self.completion_percentage = min(100, max(0, percentage))
        if note:
            self._log_status_change(f"progress_{percentage}%", "System", note)
    
    def fail(self, error_message: str, can_retry: bool = True):
        """
        Mark task as failed with structured failure reason storage.
        Implements self-healing: retry → escalate to Council.
        """
        import json
        
        self.error_count += 1
        # Structured failure reason (NEW)
        self.last_error = json.dumps({
            "message": error_message,
            "retry_number": self.retry_count,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        if can_retry and self.retry_count < self.max_retries:
            self.retry_count += 1
            # UPDATED: Use RETRYING status instead of ASSIGNED
            self.set_status(TaskStatus.RETRYING, "System", f"Retry {self.retry_count}/{self.max_retries}: {error_message}")
        else:
            # UPDATED: Escalate to Council after max retries
            self.set_status(TaskStatus.ESCALATED, "System", f"Max retries ({self.max_retries}) exceeded: {error_message}")
    
    def escalate_to_council(self, reason: str, escalated_by: str = "system"):
        """
        Manually escalate task to Council for deliberation.
        Used by self-healing loop or manual escalation.
        """
        self.set_status(TaskStatus.ESCALATED, escalated_by, reason)
    
    def _update_agent_stats(self, success: bool):
        """Update statistics for assigned agents (Placeholder)."""
        # Future implementation for agent performance tracking
    
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
        
        self.set_status(TaskStatus.CANCELLED, cancelled_by, reason)
        self.is_active = False
    
    def stop(self, reason: str, stopped_by: str):
        """Stop task (manual intervention)."""
        if self.status in [TaskStatus.COMPLETED, TaskStatus.FAILED, TaskStatus.CANCELLED]:
            raise ValueError("Cannot stop already terminal task")
        
        self.set_status(TaskStatus.STOPPED, stopped_by, reason)
        self.is_active = False
    
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
            'governance': {
                'constitutional_basis': self.constitutional_basis,
                'hierarchical_id': self.hierarchical_id,
                'parent_task_id': self.parent_task_id,
                'execution_plan_id': self.execution_plan_id,
                'recurrence_pattern': self.recurrence_pattern,
                'acceptance_criteria': self.acceptance_criteria,
                'veto_authority': self.veto_authority,
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
            'history': self.status_history,
            'error_info': {
                'error_count': self.error_count,
                'retry_count': self.retry_count,
                'max_retries': self.max_retries,
                'last_error': self.last_error
            } if self.error_count > 0 else None
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
            combined_result = "\n".join([s.result for s in siblings if s.result])
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
    agentium_id = Column(String(20), nullable=False)
    
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