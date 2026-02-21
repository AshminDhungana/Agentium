"""Database models for remote code execution."""
from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Text, DateTime, JSON, Integer, Float, ForeignKey, Enum
from sqlalchemy.orm import relationship
import enum

from backend.models.entities.base import BaseEntity


class ExecutionStatus(str, enum.Enum):
    """Status of remote execution."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


class SandboxStatus(str, enum.Enum):
    """Status of sandbox container."""
    CREATING = "creating"
    READY = "ready"
    BUSY = "busy"
    CLEANING = "cleaning"
    ERROR = "error"
    DESTROYED = "destroyed"


class RemoteExecutionRecord(BaseEntity):
    """Record of a remote code execution."""
    __tablename__ = "remote_executions"

    # Execution identification
    execution_id = Column(String(50), unique=True, nullable=False, index=True)
    agent_id = Column(String(5), ForeignKey("agents.agentium_id"), nullable=False)
    task_id = Column(String(50), ForeignKey("tasks.task_id"), nullable=True)

    # Execution content
    code = Column(Text, nullable=False)  # Python code to execute
    language = Column(String(20), default="python")
    dependencies = Column(JSON, default=list)  # pip packages to install

    # Execution context (what agent needs to know)
    input_data_schema = Column(JSON, nullable=True)  # Schema of input data
    expected_output_schema = Column(JSON, nullable=True)  # Expected result schema

    # Execution results (summary only, never raw data)
    status = Column(String(20), default=ExecutionStatus.PENDING)
    summary = Column(JSON, nullable=True)  # ExecutionSummary as dict
    error_message = Column(Text, nullable=True)

    # Resource usage
    cpu_time_seconds = Column(Float, default=0.0)
    memory_peak_mb = Column(Float, default=0.0)
    execution_time_ms = Column(Integer, default=0)

    # Sandbox info
    sandbox_id = Column(String(50), nullable=True)
    sandbox_container_id = Column(String(100), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    agent = relationship("Agent", back_populates="remote_executions")
    task = relationship("Task", back_populates="remote_executions")

    def to_dict(self) -> Dict[str, Any]:
        """Convert execution record to dictionary."""
        return {
            "id": self.id,
            "execution_id": self.execution_id,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "language": self.language,
            "status": self.status,
            "summary": self.summary,
            "error_message": self.error_message,
            "cpu_time_seconds": self.cpu_time_seconds,
            "memory_peak_mb": self.memory_peak_mb,
            "execution_time_ms": self.execution_time_ms,
            "sandbox_id": self.sandbox_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class SandboxRecord(BaseEntity):
    """Record of a sandbox container."""
    __tablename__ = "sandboxes"

    sandbox_id = Column(String(50), unique=True, nullable=False, index=True)
    container_id = Column(String(100), nullable=True)
    status = Column(String(20), default=SandboxStatus.CREATING)

    # Resource limits
    cpu_limit = Column(Float, default=1.0)  # CPU cores
    memory_limit_mb = Column(Integer, default=512)  # MB
    timeout_seconds = Column(Integer, default=300)  # 5 minutes

    # Network isolation
    network_mode = Column(String(20), default="none")  # none, bridge, custom
    allowed_hosts = Column(JSON, default=list)  # Whitelist for network access

    # Storage
    volume_mounts = Column(JSON, default=list)  # [{"host": "/data", "container": "/data"}]
    max_disk_mb = Column(Integer, default=1024)  # 1GB

    # Current execution
    current_execution_id = Column(String(50), nullable=True)
    created_by_agent_id = Column(String(5), nullable=False)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)
    destroyed_at = Column(DateTime, nullable=True)
    destroy_reason = Column(String(100), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert sandbox record to dictionary."""
        return {
            "id": self.id,
            "sandbox_id": self.sandbox_id,
            "container_id": self.container_id,
            "status": self.status,
            "cpu_limit": self.cpu_limit,
            "memory_limit_mb": self.memory_limit_mb,
            "timeout_seconds": self.timeout_seconds,
            "network_mode": self.network_mode,
            "max_disk_mb": self.max_disk_mb,
            "current_execution_id": self.current_execution_id,
            "created_by_agent_id": self.created_by_agent_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "destroyed_at": self.destroyed_at.isoformat() if self.destroyed_at else None,
            "destroy_reason": self.destroy_reason,
        }


class ExecutionSummary:
    """Summary of execution results - NEVER contains raw data."""

    def __init__(
        self,
        schema: Dict[str, str],  # Column names and types
        row_count: int,
        sample: List[Dict],  # Small preview (max 3 rows)
        stats: Dict[str, Any],  # Statistical summary
        execution_metadata: Dict[str, Any]
    ):
        self.schema = schema
        self.row_count = row_count
        self.sample = sample
        self.stats = stats
        self.execution_metadata = execution_metadata

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema": self.schema,
            "row_count": self.row_count,
            "sample": self.sample,
            "stats": self.stats,
            "execution_metadata": self.execution_metadata
        }
