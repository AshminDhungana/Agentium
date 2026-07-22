"""
Tool Staging Entity
Staging table for proposed tools pending approval.
Extracted from tool_creation_service.py into its own model file.
"""
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, JSON
from .base import BaseEntity
from datetime import datetime


class ToolStaging(BaseEntity):
    """
    Staging record for a tool proposal before activation.
    Tracks the full lifecycle: proposed → approved/rejected → activated/deprecated.
    """
    __tablename__ = 'tool_staging'

    # Inherited from BaseEntity but not used here; kept nullable to match the DB
    # schema (these tool tables never populate agentium_id).
    agentium_id = Column(String(20), nullable=True)

    tool_name = Column(String(100), unique=True, nullable=False, index=True)
    proposed_by_agentium_id = Column(String(10), nullable=False, index=True)
    tool_path = Column(String(500), nullable=False)
    request_json = Column(Text, nullable=False)          # Full ToolCreationRequest as JSON

    requires_vote = Column(Boolean, default=True)
    voting_id = Column(String(36), nullable=True)

    # Lifecycle status
    # pending_approval | approved | activated | rejected | deprecated | sunset
    status = Column(String(50), default='pending_approval', index=True)

    # Timestamps
    activated_at = Column(DateTime, nullable=True)
    deprecated_at = Column(DateTime, nullable=True)
    sunset_at = Column(DateTime, nullable=True)          # Hard-removal scheduled date

    # Deprecation metadata
    deprecated_by_agentium_id = Column(String(10), nullable=True)
    deprecation_reason = Column(Text, nullable=True)
    replacement_tool_name = Column(String(100), nullable=True)  # Successor tool, if any

    # Versioning link
    current_version = Column(Integer, default=1, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "proposed_by": self.proposed_by_agentium_id,
            "tool_path": self.tool_path,
            "status": self.status,
            "requires_vote": self.requires_vote,
            "voting_id": self.voting_id,
            "current_version": self.current_version,
            "activated_at": self.activated_at.isoformat() if self.activated_at else None,
            "deprecated_at": self.deprecated_at.isoformat() if self.deprecated_at else None,
            "sunset_at": self.sunset_at.isoformat() if self.sunset_at else None,
            "deprecated_by": self.deprecated_by_agentium_id,
            "deprecation_reason": self.deprecation_reason,
            "replacement_tool_name": self.replacement_tool_name,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }