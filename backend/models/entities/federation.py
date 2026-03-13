"""
Phase 11.2 — Federation Models
==============================
Models for tracking peer Agentium instances, federated tasks, and cross-instance voting.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, func, Float
from sqlalchemy.orm import relationship

from backend.models.entities.base import Base

def _new_uuid() -> str:
    return str(uuid.uuid4())

class FederatedInstance(Base):
    """A peer Agentium instance."""
    __tablename__ = "federated_instances"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    name = Column(String(100), nullable=False)
    base_url = Column(String(255), nullable=False, unique=True)
    shared_secret_hash = Column(String(255), nullable=False)
    
    # Phase 11.2 - For HMAC JWT Exchange Authentication
    signing_key = Column(String(255), nullable=True) # Derived key for HMAC
    
    # "active", "suspended", "pending"
    status = Column(String(20), default="pending", nullable=False)
    # "full", "limited", "read_only"
    trust_level = Column(String(20), default="limited", nullable=False)
    
    capabilities_shared = Column(JSON, default=list)

    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    outgoing_tasks = relationship("FederatedTask", foreign_keys="FederatedTask.target_instance_id")
    incoming_tasks = relationship("FederatedTask", foreign_keys="FederatedTask.source_instance_id")

class FederatedTask(Base):
    """A task delegated to or received from a peer instance."""
    __tablename__ = "federated_tasks"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    
    source_instance_id = Column(String(36), ForeignKey("federated_instances.id"), nullable=True, index=True)
    target_instance_id = Column(String(36), ForeignKey("federated_instances.id"), nullable=True, index=True)
    
    original_task_id = Column(String(36), nullable=False)  # Task ID on source
    local_task_id = Column(String(36), ForeignKey("tasks.id"), nullable=True)  # Task ID if received here
    
    # "pending", "accepted", "rejected", "completed"
    status = Column(String(20), default="pending", nullable=False)
    
    delegated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at = Column(DateTime(timezone=True), nullable=True)

class FederatedVote(Base):
    """A vote spanning multiple instances."""
    __tablename__ = "federated_votes"
    
    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    proposal_id = Column(String(36), nullable=False) # Local or remote proposal ID
    
    # List of instance IDs participating
    participating_instances = Column(JSON, default=list)
    # Dict mapping instance_id -> result (e.g. {"inst1": "PASS", "inst2": "REJECT"})
    votes = Column(JSON, default=dict)
    
    # "open", "closed"
    status = Column(String(20), default="open", nullable=False)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closes_at = Column(DateTime(timezone=True), nullable=False)
