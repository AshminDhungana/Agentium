"""
Tool Version Entity
Tracks every code revision of a generated tool, enabling rollback and diff history.
"""
from sqlalchemy import Column, String, Integer, Text, Boolean, DateTime, ForeignKey
from backend.models.entities.base import BaseEntity
from datetime import datetime


class ToolVersion(BaseEntity):
    """
    Immutable record of a tool at a specific version.
    New version created on every approved update.
    Rollback = reactivating a prior ToolVersion's code.
    """
    __tablename__ = 'tool_versions'

    # Inherited from BaseEntity but not used here; kept nullable to match the DB
    # schema (these tool tables never populate agentium_id).
    agentium_id = Column(String(20), nullable=True)

    tool_name = Column(String(100), nullable=False, index=True)
    version_number = Column(Integer, nullable=False)            # 1, 2, 3 …
    version_tag = Column(String(20), nullable=False)            # "v1.0.0", "v2.0.0"

    # The actual code snapshot at this version
    code_snapshot = Column(Text, nullable=False)
    tool_path = Column(String(500), nullable=False)             # Path on disk

    # Who made this version and why
    authored_by_agentium_id = Column(String(10), nullable=False)
    change_summary = Column(Text, nullable=True)                # Human-readable changelog entry

    # Approval metadata
    approved_by_voting_id = Column(String(36), nullable=True)
    approved_at = Column(DateTime, nullable=True)

    # State flags
    is_active = Column(Boolean, default=False)                  # Only one version active at a time
    is_rolled_back = Column(Boolean, default=False)             # Was this restored via rollback?
    rolled_back_from_version = Column(Integer, nullable=True)   # If rollback, which version triggered it

    def to_dict(self):
        return {
            "id": self.id,
            "tool_name": self.tool_name,
            "version_number": self.version_number,
            "version_tag": self.version_tag,
            "authored_by": self.authored_by_agentium_id,
            "change_summary": self.change_summary,
            "approved_by_voting_id": self.approved_by_voting_id,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "is_active": self.is_active,
            "is_rolled_back": self.is_rolled_back,
            "rolled_back_from_version": self.rolled_back_from_version,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }