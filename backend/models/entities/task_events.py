"""
Task Event Sourcing Model for Agentium.
Implements immutable event log for complete audit trail and state reconstruction.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Enum, JSON, Integer
from sqlalchemy.orm import relationship
from backend.models.entities.base import BaseEntity
import enum


class TaskEventType(str, enum.Enum):
    """Types of task events for event sourcing."""
    # Lifecycle events
    TASK_CREATED = "task_created"
    TASK_UPDATED = "task_updated"
    
    # Governance events
    TASK_DELIBERATED = "task_deliberated"
    TASK_APPROVED = "task_approved"
    TASK_REJECTED = "task_rejected"
    TASK_DELEGATED = "task_delegated"
    
    # Execution events
    TASK_STARTED = "task_started"
    TASK_CHUNK_EXECUTED = "task_chunk_executed"
    TASK_FAILED = "task_failed"
    TASK_RETRIED = "task_retried"
    TASK_ESCALATED = "task_escalated"
    TASK_COMPLETED = "task_completed"
    TASK_CANCELLED = "task_cancelled"
    TASK_STOPPED = "task_stopped"
    
    # Status change (generic)
    STATUS_CHANGED = "status_changed"


class TaskEvent(BaseEntity):
    """
    Immutable event log entry for task lifecycle.
    All task state changes emit events for complete audit trail.
    """
    
    __tablename__ = 'task_events'
    
    task_id = Column(String(36), ForeignKey('tasks.id'), nullable=False, index=True)
    event_type = Column(Enum(TaskEventType), nullable=False)
    actor_id = Column(String(36), nullable=False)  # Agent or user who triggered event
    actor_type = Column(String(20), default="system")  # agent, user, system
    
    # Event data (structured JSON)
    data = Column(JSON, default=dict)
    
    # Sequence number for ordering within a task
    sequence_number = Column(Integer, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Relationship
    task = relationship("Task", back_populates="events")
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not self.agentium_id:
            # Prefix 'E' for Event. Column is VARCHAR(10): 1 (prefix) +
            # 6 (HHMMSS) + 3 (millisecond-precision suffix) = 10 chars exactly.
            now = datetime.utcnow()
            self.agentium_id = f"E{now.strftime('%H%M%S')}{now.strftime('%f')[:3]}"
    
    @classmethod
    def reconstruct_state(cls, task_id: str, db_session) -> Dict[str, Any]:
        """
        Reconstruct task state from event history.
        Returns the derived state after replaying all events.
        """
        events = db_session.query(TaskEvent).filter_by(
            task_id=task_id
        ).order_by(TaskEvent.created_at).all()
        
        if not events:
            return {"error": "No events found for task"}
        
        # Replay events to derive state
        state = {
            "task_id": task_id,
            "status": "pending",
            "retry_count": 0,
            "error_count": 0,
            "assigned_agents": [],
            "approvals": {
                "council": False,
                "head": False
            }
        }
        
        for event in events:
            data = event.data or {}
            
            if event.event_type == TaskEventType.TASK_CREATED:
                state.update({
                    "title": data.get("title"),
                    "description": data.get("description"),
                    "priority": data.get("priority"),
                    "task_type": data.get("task_type"),
                    "created_by": data.get("created_by")
                })
            
            elif event.event_type == TaskEventType.STATUS_CHANGED:
                state["status"] = data.get("new_status", state["status"])
                
                if data.get("old_status") == "retrying":
                    state["retry_count"] = state.get("retry_count", 0) + 1
            
            elif event.event_type == TaskEventType.TASK_FAILED:
                state["error_count"] = state.get("error_count", 0) + 1
                state["last_error"] = data.get("error_message")
            
            elif event.event_type == TaskEventType.TASK_APPROVED:
                if data.get("approver_type") == "council":
                    state["approvals"]["council"] = True
                elif data.get("approver_type") == "head":
                    state["approvals"]["head"] = True
            
            elif event.event_type == TaskEventType.TASK_DELEGATED:
                state["lead_agent_id"] = data.get("lead_agent_id")
            
            elif event.event_type == TaskEventType.TASK_STARTED:
                state["started_at"] = event.created_at.isoformat()
            
            elif event.event_type == TaskEventType.TASK_COMPLETED:
                state["completed_at"] = event.created_at.isoformat()
                state["result_summary"] = data.get("result_summary")
        
        return state
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'task_id': self.task_id,
            'event_type': self.event_type.value,
            'actor_id': self.actor_id,
            'actor_type': self.actor_type,
            'data': self.data,
            'sequence_number': self.sequence_number,
            'timestamp': self.created_at.isoformat() if self.created_at else None
        })
        return base