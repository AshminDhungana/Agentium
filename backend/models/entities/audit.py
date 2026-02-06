"""
Comprehensive audit system for Agentium.
Records all actions for transparency, accountability, and debugging.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, JSON, Index, Boolean, Float
from sqlalchemy.orm import relationship
from backend.models.entities.base import BaseEntity
import enum
import json

class AuditLevel(str, enum.Enum):
    """Severity/Importance levels for audit events."""
    DEBUG = "debug"           # Development only
    INFO = "info"             # Normal operations
    NOTICE = "notice"         # Significant but expected
    WARNING = "warning"       # Potentially problematic
    CRITICAL = "critical"     # Serious issues
    EMERGENCY = "emergency"   # System-compromising

class AuditCategory(str, enum.Enum):
    """Categories of audit events."""
    SYSTEM = "system"                 # system startup/shutdown
    AGENT_LIFECYCLE = "agent_lifecycle"  # spawn, terminate, status change
    CONSTITUTION = "constitution"     # amendments, ethos updates
    TASK = "task"                     # task creation, assignment, completion
    VOTING = "voting"                 # deliberation, votes cast
    AUTHENTICATION = "authentication" # login, logout, permission checks
    AUTHORIZATION = "authorization"   # permission checks, access denials
    COMMUNICATION = "communication"   # messages between agents
    EXECUTION = "execution"           # code execution, tool usage
    DATA_ACCESS = "data_access"       # database queries, file access
    EXTERNAL_API = "external_api"     # calls to external services
    SECURITY = "security"             # violations, suspicious activity
    GOVERNANCE = "governance"

class AuditLog(BaseEntity):
    """
    Central audit log for all Agentium activities.
    Immutable record of who did what, when, and with what result.
    """
    
    __tablename__ = 'audit_logs'
    
    # Classification
    level = Column(Enum(AuditLevel), default=AuditLevel.INFO, nullable=False, index=True)
    category = Column(Enum(AuditCategory), nullable=False, index=True)
    
    # Actor identification
    actor_type = Column(String(20), nullable=False)  # agent, sovereign, system
    actor_id = Column(String(10), nullable=False, index=True)  # agentium_id or user_id
    
    # Action details
    action = Column(String(100), nullable=False)  # e.g., "task_assigned", "constitution_amended"
    action_description = Column(Text, nullable=True)  # Human-readable description
    
    # Target (what was acted upon)
    target_type = Column(String(50), nullable=True)  # task, agent, constitution, etc.
    target_id = Column(String(36), nullable=True, index=True)  # UUID of target
    
    # Context
    session_id = Column(String(100), nullable=True, index=True)  # WebSocket/HTTP session
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(200), nullable=True)
    
    # Detailed data
    before_state = Column(JSON, nullable=True)  # State before action
    after_state = Column(JSON, nullable=True)   # State after action
    meta_data = Column(JSON, nullable=True)      # ✅ FIXED: Changed from 'metadata' to 'meta_data'
    request_payload = Column(Text, nullable=True)  # Raw request data
    
    # Result
    success = Column(String(1), default='Y', nullable=False)  # Y/N
    result_message = Column(Text, nullable=True)
    error_code = Column(String(50), nullable=True)
    error_details = Column(Text, nullable=True)
    
    # Chain of custody
    parent_audit_id = Column(String(36), ForeignKey('audit_logs.id'), nullable=True)
    correlation_id = Column(String(36), nullable=True, index=True)  # Groups related events
    
    # Performance
    duration_ms = Column(Integer, nullable=True)  # Action duration in milliseconds
    memory_delta_mb = Column(Integer, nullable=True)  # Memory impact
    
    # Relationships
    parent = relationship("AuditLog", remote_side="AuditLog.id", backref="children")
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_audit_timestamp', 'created_at'),
        Index('idx_audit_actor_action', 'actor_id', 'action'),
        Index('idx_audit_level_category', 'level', 'category'),
        Index('idx_audit_correlation', 'correlation_id'),
    )
    
    @classmethod
    def log(cls, 
            level: AuditLevel,
            category: AuditCategory,
            actor_type: str,
            actor_id: str,
            action: str,
            target_type: str = None,
            target_id: str = None,
            description: str = None,
            success: bool = True,
            before_state: Dict = None,
            after_state: Dict = None,
            meta_data: Dict = None,  # ✅ FIXED: Changed parameter name
            **kwargs) -> 'AuditLog':
        """
        Factory method to create audit log entry.
        """
        entry = cls(
            agentium_id=f"A{datetime.utcnow().strftime('%Y%m%d%H%M%S')}{actor_id}",
            level=level,
            category=category,
            actor_type=actor_type,
            actor_id=actor_id,
            action=action,
            action_description=description,
            target_type=target_type,
            target_id=target_id,
            success='Y' if success else 'N',
            before_state=before_state,
            after_state=after_state,
            meta_data=meta_data,  # ✅ FIXED: Changed parameter name
            **kwargs
        )
        return entry
    
    @classmethod
    def system_log(cls, action: str, description: str, level: AuditLevel = AuditLevel.INFO):
        """Shortcut for system-level events."""
        return cls.log(
            level=level,
            category=AuditCategory.SYSTEM,
            actor_type='system',
            actor_id='SYSTEM',
            action=action,
            description=description
        )
    
    @classmethod
    def security_log(cls, action: str, actor_id: str, description: str, success: bool = False):
        """Shortcut for security events."""
        return cls.log(
            level=AuditLevel.CRITICAL if not success else AuditLevel.WARNING,
            category=AuditCategory.SECURITY,
            actor_type='agent',
            actor_id=actor_id,
            action=action,
            description=description,
            success=success
        )
    
    def add_child_event(self, child_event: 'AuditLog'):
        """Link a related event as child."""
        child_event.parent_audit_id = self.id
        child_event.correlation_id = self.correlation_id or self.id
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'level': self.level.value,
            'category': self.category.value,
            'actor': {
                'type': self.actor_type,
                'id': self.actor_id
            },
            'action': self.action,
            'description': self.action_description,
            'target': {
                'type': self.target_type,
                'id': self.target_id
            } if self.target_type else None,
            'result': {
                'success': self.success == 'Y',
                'message': self.result_message,
                'error': self.error_code
            },
            'timestamp': self.created_at.isoformat(),
            'duration_ms': self.duration_ms,
            'metadata': self.meta_data  # ✅ FIXED: Using meta_data attribute
        })
        return base


class ConstitutionViolation(BaseEntity):
    """
    Special audit table for constitution violations.
    Tracks when agents attempt or succeed in violating the supreme law.
    """
    
    __tablename__ = 'constitution_violations'
    
    # Violator
    agentium_id = Column(String(10), ForeignKey('agents.agentium_id'), nullable=False)
    
    # Violation details
    violation_type = Column(String(50), nullable=False)  # e.g., "unauthorized_action"
    violated_article = Column(String(50), nullable=True)  # Which constitution article
    description = Column(Text, nullable=False)
    severity = Column(Enum(AuditLevel), default=AuditLevel.WARNING, nullable=False)
    
    # The action attempted
    attempted_action = Column(Text, nullable=False)
    context = Column(JSON, nullable=True)  # Full context of the situation
    
    # Detection
    detected_by = Column(String(10), nullable=False)  # Agent or system that caught it
    detection_method = Column(String(50), nullable=True)  # e.g., "pre_execution_check"
    
    # Resolution
    blocked = Column(Boolean, default=True)  # Whether the action was prevented
    auto_terminated = Column(Boolean, default=False)  # Agent was auto-terminated
    escalated_to = Column(String(10), nullable=True)  # Head of Council alerted
    
    # Human review
    reviewed_by_sovereign = Column(Boolean, default=False)
    sovereign_decision = Column(String(20), nullable=True)  # override, confirm, pardon
    review_notes = Column(Text, nullable=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = f"X{kwargs.get('agentium_id', '00000')}{datetime.utcnow().strftime('%H%M%S')}"
    
    def mark_reviewed(self, decision: str, notes: str = None):
        """Mark violation as reviewed by Sovereign."""
        self.reviewed_by_sovereign = True
        self.sovereign_decision = decision
        self.review_notes = notes
    
    def escalate(self, head_agentium_id: str):
        """Alert Head of Council about violation."""
        self.escalated_to = head_agentium_id
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'violator': self.agentium_id,
            'type': self.violation_type,
            'article': self.violated_article,
            'severity': self.severity.value,
            'action_attempted': self.attempted_action,
            'blocked': self.blocked,
            'auto_terminated': self.auto_terminated,
            'escalated': self.escalated_to is not None,
            'reviewed': self.reviewed_by_sovereign,
            'decision': self.sovereign_decision
        })
        return base


class SessionLog(BaseEntity):
    """
    Tracks user/agent sessions for activity analysis.
    Helps reconstruct what happened during a specific interaction.
    """
    
    __tablename__ = 'session_logs'
    
    session_id = Column(String(100), nullable=False, unique=True, index=True)
    session_type = Column(String(20), nullable=False)  # websocket, http, internal
    
    # Participant
    actor_type = Column(String(20), nullable=False)
    actor_id = Column(String(10), nullable=False, index=True)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ended_at = Column(DateTime, nullable=True)
    last_activity_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Activity summary
    requests_count = Column(Integer, default=0)
    tasks_created = Column(Integer, default=0)
    votes_cast = Column(Integer, default=0)
    messages_exchanged = Column(Integer, default=0)
    
    # Status
    termination_reason = Column(String(50), nullable=True)  # logout, timeout, error
    
    # Related audit entries
    audit_entries = relationship("AuditLog", foreign_keys=[AuditLog.session_id], 
                                primaryjoin="SessionLog.session_id == AuditLog.session_id",
                                lazy="dynamic")
    
    def record_activity(self):
        """Update last activity timestamp."""
        self.last_activity_at = datetime.utcnow()
    
    def end_session(self, reason: str = "logout"):
        """Mark session as ended."""
        self.ended_at = datetime.utcnow()
        self.termination_reason = reason
    
    def is_active(self, timeout_seconds: int = 3600) -> bool:
        """Check if session is still active."""
        if self.ended_at:
            return False
        
        idle_time = (datetime.utcnow() - self.last_activity_at).total_seconds()
        return idle_time < timeout_seconds
    
    def add_audit(self, audit_entry: AuditLog):
        """Link an audit entry to this session."""
        audit_entry.session_id = self.session_id
        self.requests_count += 1
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        duration = None
        if self.ended_at and self.started_at:
            duration = (self.ended_at - self.started_at).total_seconds()
        
        base.update({
            'session_id': self.session_id,
            'actor': self.actor_id,
            'type': self.session_type,
            'duration_seconds': duration,
            'activity': {
                'requests': self.requests_count,
                'tasks': self.tasks_created,
                'votes': self.votes_cast,
                'messages': self.messages_exchanged
            },
            'status': 'active' if self.is_active() else 'ended',
            'started': self.started_at.isoformat(),
            'ended': self.ended_at.isoformat() if self.ended_at else None
        })
        return base


class HealthCheck(BaseEntity):
    """
    System health monitoring for observability.
    Tracks component status and performance metrics.
    """
    
    __tablename__ = 'health_checks'
    
    component = Column(String(50), nullable=False)  # e.g., "database", "head_council"
    status = Column(String(20), nullable=False)  # healthy, degraded, unhealthy
    latency_ms = Column(Integer, nullable=True)
    error_rate = Column(Float, nullable=True)  # 0.0 to 1.0
    
    # Metrics
    memory_usage_mb = Column(Integer, nullable=True)
    cpu_usage_percent = Column(Float, nullable=True)
    active_connections = Column(Integer, nullable=True)
    
    # Details
    check_output = Column(Text, nullable=True)  # JSON results
    last_error = Column(Text, nullable=True)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            component = kwargs.get('component', 'unknown')
            self.agentium_id = f"H{component[0].upper()}{datetime.utcnow().strftime('%H%M%S')}"
    
    def is_healthy(self) -> bool:
        """Check if component is healthy."""
        return self.status == 'healthy'
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'component': self.component,
            'status': self.status,
            'metrics': {
                'latency_ms': self.latency_ms,
                'error_rate': self.error_rate,
                'memory_mb': self.memory_usage_mb,
                'cpu_percent': self.cpu_usage_percent,
                'connections': self.active_connections
            },
            'issues': self.last_error
        })
        return base