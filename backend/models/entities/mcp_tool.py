"""
MCP Tool Entity — Phase 6.7
Database model for MCP server tools with constitutional tier classification.
"""
from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Column, String, Boolean, Integer, DateTime, JSON, Text
)
from backend.models.entities.base import Base, BaseEntity


class MCPTool(BaseEntity):
    """
    Represents a single MCP server registered in Agentium's Tool Registry.

    Lifecycle:
        proposed → pending_vote → approved (or rejected) → [revoked | disabled]

    Tiers mirror the Constitutional Guard classification:
        pre_approved  — safe read-only APIs; Council vote required to USE
        restricted    — destructive or side-effectful; Head approval per invocation
        forbidden     — constitutionally banned; always blocked before reaching the MCP client
    """
    __tablename__ = "mcp_tools"

    # ── Identity ───────────────────────────────────────────────────────────────
    name: str = Column(String(128), nullable=False, unique=True, index=True)
    description: str = Column(Text, nullable=False)
    server_url: str = Column(String(512), nullable=False)

    # ── Constitutional classification ──────────────────────────────────────────
    # Values: "pre_approved" | "restricted" | "forbidden"
    tier: str = Column(String(32), nullable=False, default="restricted")

    # Human-readable reference to the Constitution article that governs this tool
    constitutional_article: Optional[str] = Column(String(64), nullable=True)

    # ── Approval state ─────────────────────────────────────────────────────────
    # Values: "pending" | "approved" | "rejected" | "revoked" | "disabled"
    status: str = Column(String(32), nullable=False, default="pending")

    approved_by_council: bool = Column(Boolean, default=False, nullable=False)
    approval_vote_id: Optional[str] = Column(String(64), nullable=True)
    approved_at: Optional[datetime] = Column(DateTime, nullable=True)
    approved_by: Optional[str] = Column(String(64), nullable=True)  # agentium_id

    revoked_at: Optional[datetime] = Column(DateTime, nullable=True)
    revoked_by: Optional[str] = Column(String(64), nullable=True)
    revocation_reason: Optional[str] = Column(Text, nullable=True)

    # ── Capabilities advertised by the MCP server ──────────────────────────────
    # Stored as JSON list of capability-name strings returned by list_tools()
    capabilities: List[str] = Column(JSON, nullable=False, default=list)

    # ── Health tracking ────────────────────────────────────────────────────────
    # Values: "healthy" | "degraded" | "down" | "unknown"
    health_status: str = Column(String(32), nullable=False, default="unknown")
    last_health_check_at: Optional[datetime] = Column(DateTime, nullable=True)
    failure_count: int = Column(Integer, nullable=False, default=0)
    consecutive_failures: int = Column(Integer, nullable=False, default=0)

    # ── Usage statistics ───────────────────────────────────────────────────────
    usage_count: int = Column(Integer, nullable=False, default=0)
    last_used_at: Optional[datetime] = Column(DateTime, nullable=True)

    # ── Audit trail ────────────────────────────────────────────────────────────
    # Every invocation is appended here: [{agent_id, timestamp, input_hash, result}]
    audit_log: List[dict] = Column(JSON, nullable=False, default=list)

    # ── Proposal metadata ──────────────────────────────────────────────────────
    proposed_by: Optional[str] = Column(String(64), nullable=True)  # agentium_id
    proposed_at: Optional[datetime] = Column(DateTime, nullable=True)

    def to_dict(self) -> dict:
        return {
            "id": str(self.id),
            "name": self.name,
            "description": self.description,
            "server_url": self.server_url,
            "tier": self.tier,
            "constitutional_article": self.constitutional_article,
            "status": self.status,
            "approved_by_council": self.approved_by_council,
            "approval_vote_id": self.approval_vote_id,
            "approved_at": self.approved_at.isoformat() if self.approved_at else None,
            "approved_by": self.approved_by,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "revoked_by": self.revoked_by,
            "revocation_reason": self.revocation_reason,
            "capabilities": self.capabilities or [],
            "health_status": self.health_status,
            "last_health_check_at": self.last_health_check_at.isoformat() if self.last_health_check_at else None,
            "failure_count": self.failure_count,
            "consecutive_failures": self.consecutive_failures,
            "usage_count": self.usage_count,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "proposed_by": self.proposed_by,
            "proposed_at": self.proposed_at.isoformat() if self.proposed_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }