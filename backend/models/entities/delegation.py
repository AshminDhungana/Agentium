"""
Phase 11.1 — Delegation Model
==============================
Records capability delegations between users (sovereigns).
Supports time-limited grants, emergency overrides, and revocation.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, func
from sqlalchemy.orm import relationship

from .base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class Delegation(Base):
    __tablename__ = "delegations"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)

    grantor_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    grantee_id = Column(
        String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # JSON list of capability strings, e.g. ["configure_agents", "veto"]
    capabilities = Column(JSON, nullable=False, default=list)
    reason = Column(String(500), nullable=True)

    granted_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)  # None = permanent
    revoked_at = Column(DateTime(timezone=True), nullable=True)

    is_emergency = Column(Boolean, default=False, nullable=False)

    # Relationships
    grantor = relationship(
        "User",
        foreign_keys=[grantor_id],
        back_populates="delegations_granted",
    )
    grantee = relationship(
        "User",
        foreign_keys=[grantee_id],
        back_populates="delegations_received",
    )

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @property
    def is_active(self) -> bool:
        """Whether this delegation is currently in effect."""
        if self.revoked_at is not None:
            return False
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return False
        return True

    def revoke(self) -> None:
        """Mark the delegation as revoked."""
        self.revoked_at = datetime.utcnow()

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "grantor_id": self.grantor_id,
            "grantee_id": self.grantee_id,
            "capabilities": self.capabilities or [],
            "reason": self.reason,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "is_emergency": self.is_emergency,
            "is_active": self.is_active,
        }

    def __repr__(self) -> str:
        return (
            f"<Delegation {self.id[:8]} "
            f"grantor={self.grantor_id[:8]} -> grantee={self.grantee_id[:8]} "
            f"active={self.is_active}>"
        )
