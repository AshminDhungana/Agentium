"""
WaitCondition entity for Agentium Wait & Poll feature.

A WaitCondition suspends a task until an external signal arrives or a
poll-based strategy resolves the condition (HTTP, Redis key, timeout).
"""

from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, JSON
from sqlalchemy.orm import relationship
from backend.models.entities.base import BaseEntity
import enum


class WaitStrategy(str, enum.Enum):
    """How the condition is resolved."""
    HTTP_POLL   = "http_poll"    # Poll an external HTTP endpoint
    REDIS_KEY   = "redis_key"    # Wait for a Redis key to appear / match
    TIMEOUT     = "timeout"      # Pure time-based wait (no external check)
    WEBHOOK     = "webhook"      # Resolved by an inbound webhook call
    MANUAL      = "manual"       # Resolved manually via API
    EXECUTION   = "execution"    # Wait for a RemoteExecutionRecord to complete


class WaitConditionStatus(str, enum.Enum):
    """Lifecycle states for a WaitCondition record."""
    PENDING   = "pending"    # Created but task not yet in WAITING state
    ACTIVE    = "active"     # Task is WAITING; poller is checking
    RESOLVED  = "resolved"   # Condition met; task resumed
    EXPIRED   = "expired"    # Max attempts / deadline exceeded
    CANCELLED = "cancelled"  # Cancelled before resolution


class WaitCondition(BaseEntity):
    """
    Suspends a task until an external condition is satisfied.

    The poller (``poll_wait_conditions`` Celery beat task) inspects all
    ACTIVE records and calls ``WaitPollService.evaluate()`` on each one.
    When evaluation returns True the task is automatically resumed.
    """

    __tablename__ = "wait_conditions"

    # ── Core FK ───────────────────────────────────────────────────────────
    task_id = Column(String(36), ForeignKey("tasks.id"), nullable=False, index=True)

    # ── Strategy ──────────────────────────────────────────────────────────
    strategy     = Column(Enum(WaitStrategy, values_callable=lambda obj: [e.value for e in obj]),         nullable=False)
    status       = Column(Enum(WaitConditionStatus, values_callable=lambda obj: [e.value for e in obj]),  nullable=False,
                          default=WaitConditionStatus.PENDING, index=True)

    # ── Strategy-specific configuration (JSON) ────────────────────────────
    # HTTP_POLL  → { url, method, headers, expected_status, jsonpath, expected_value }
    # REDIS_KEY  → { key, expected_value, match_type }  (match_type: exists|eq|gt)
    # TIMEOUT    → { seconds }
    # WEBHOOK    → { secret_token }
    # MANUAL     → {}
    config = Column(JSON, nullable=False, default=dict)

    # ── Poll bookkeeping ──────────────────────────────────────────────────
    max_attempts  = Column(Integer, nullable=False, default=60)
    attempt_count = Column(Integer, nullable=False, default=0)
    poll_interval_seconds = Column(Integer, nullable=False, default=30)

    # ── Deadline (optional hard cut-off regardless of attempts) ───────────
    expires_at = Column(DateTime, nullable=True)

    # ── Resolution detail ─────────────────────────────────────────────────
    resolved_at     = Column(DateTime, nullable=True)
    resolution_data = Column(JSON,     nullable=True)  # raw response / value that triggered resolution
    failure_reason  = Column(Text,     nullable=True)

    # ── Who triggered the wait ────────────────────────────────────────────
    created_by_agent_id = Column(String(36), nullable=True)

    # ── Relationship ──────────────────────────────────────────────────────
    task = relationship("Task", foreign_keys=[task_id])

    # ─────────────────────────────────────────────────────────────────────

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get("agentium_id"):
            self.agentium_id = self._generate_wc_id()

    def _generate_wc_id(self) -> str:
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text(
                "SELECT agentium_id FROM wait_conditions "
                "WHERE agentium_id ~ '^WC[0-9]+$' "
                "ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC LIMIT 1"
            )).scalar()
            next_num = (int(result[2:]) + 1) if result else 1
            return f"WC{next_num:05d}"

    # ── Convenience helpers ───────────────────────────────────────────────

    def activate(self) -> None:
        """Mark as ACTIVE (called when the parent task enters WAITING)."""
        self.status = WaitConditionStatus.ACTIVE

    def resolve(self, data: Optional[Dict] = None) -> None:
        """Mark as RESOLVED with optional resolution payload."""
        self.status        = WaitConditionStatus.RESOLVED
        self.resolved_at   = datetime.utcnow()
        self.resolution_data = data or {}

    def expire(self, reason: str = "max_attempts_exceeded") -> None:
        """Mark as EXPIRED."""
        self.status         = WaitConditionStatus.EXPIRED
        self.failure_reason = reason

    def cancel(self) -> None:
        """Mark as CANCELLED."""
        self.status = WaitConditionStatus.CANCELLED

    def is_overdue(self) -> bool:
        """True if the hard deadline has passed."""
        if self.expires_at and datetime.utcnow() > self.expires_at:
            return True
        return False

    def increment_attempt(self) -> bool:
        """Increment attempt counter. Returns False when max is exceeded."""
        self.attempt_count += 1
        return self.attempt_count <= self.max_attempts

    # ── Serialisation ─────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "task_id":              self.task_id,
            "strategy":             self.strategy.value,
            "status":               self.status.value,
            "config":               self.config,
            "max_attempts":         self.max_attempts,
            "attempt_count":        self.attempt_count,
            "poll_interval_seconds": self.poll_interval_seconds,
            "expires_at":           self.expires_at.isoformat() if self.expires_at else None,
            "resolved_at":          self.resolved_at.isoformat() if self.resolved_at else None,
            "resolution_data":      self.resolution_data,
            "failure_reason":       self.failure_reason,
            "created_by_agent_id":  self.created_by_agent_id,
        })
        return base