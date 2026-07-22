"""
Tool Usage Log Entity
Persistent analytics table recording every tool invocation.
Queryable for dashboards, rate limiting, and per-tool performance reports.
"""
from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, Text, JSON, Index
from .base import BaseEntity
from datetime import datetime


class ToolUsageLog(BaseEntity):
    """
    One row per tool invocation.
    Written by ToolAnalyticsService after every execute() call.
    """
    __tablename__ = 'tool_usage_logs'

    # Inherited from BaseEntity but not used here; kept nullable to match the DB
    # schema (these tool tables never populate agentium_id).
    agentium_id = Column(String(20), nullable=True)

    # What was called
    tool_name = Column(String(100), nullable=False, index=True)
    tool_version = Column(Integer, nullable=False, default=1)

    # Who called it
    called_by_agentium_id = Column(String(10), nullable=False, index=True)
    task_id = Column(String(36), nullable=True, index=True)     # Task context, if any

    # Execution outcome
    success = Column(Boolean, nullable=False)
    error_message = Column(Text, nullable=True)
    latency_ms = Column(Float, nullable=True)                   # Wall-clock execution time

    # Input/output fingerprints (hashed — never raw data)
    input_hash = Column(String(64), nullable=True)              # SHA-256 of input kwargs
    output_size_bytes = Column(Integer, nullable=True)          # Size of result payload

    # Timestamps
    invoked_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Composite indexes for common query patterns
    __table_args__ = (
        Index('ix_tool_usage_tool_invoked', 'tool_name', 'invoked_at'),
        Index('ix_tool_usage_agent_tool', 'called_by_agentium_id', 'tool_name'),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "tool_version": self.tool_version,
            "called_by": self.called_by_agentium_id,
            "task_id": self.task_id,
            "success": self.success,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "input_hash": self.input_hash,
            "output_size_bytes": self.output_size_bytes,
            "invoked_at": self.invoked_at.isoformat() if self.invoked_at else None,
        }