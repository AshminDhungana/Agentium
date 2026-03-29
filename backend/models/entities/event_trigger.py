"""
Phase 13.6 — Intelligent Event Processing Models
==================================================
Entities for event triggers (webhook, schedule, threshold, api_poll)
and the corresponding event logs that track every fired event.
"""
import enum
import uuid
from datetime import datetime
from typing import Dict, Any, Optional

from sqlalchemy import (
    Column, String, Integer, Text, JSON, DateTime,
    Enum, ForeignKey, Boolean, func,
)
from sqlalchemy.orm import relationship

from backend.models.entities.base import BaseEntity


# ── Enums ─────────────────────────────────────────────────────────────────────

class TriggerType(str, enum.Enum):
    """The source type that fires an event trigger."""
    WEBHOOK = "webhook"
    SCHEDULE = "schedule"
    THRESHOLD = "threshold"
    API_POLL = "api_poll"


class EventLogStatus(str, enum.Enum):
    """Processing outcome for a single event log entry."""
    PROCESSED = "processed"
    DEAD_LETTER = "dead_letter"
    DUPLICATE = "duplicate"


# ── EventTrigger ──────────────────────────────────────────────────────────────

class EventTrigger(BaseEntity):
    """
    Defines a rule that, when matched, fires an action (create task,
    start workflow, or notify an agent).

    trigger_type  — how the trigger is activated:
      • webhook   — incoming HTTP POST with HMAC validation
      • schedule  — cron-style (handled by Celery beat or per-trigger schedule)
      • threshold — checks Redis metrics and fires when condition met
      • api_poll  — periodically polls an external URL and fires on change

    config (JSONB) — type-specific settings:
      webhook   → { hmac_secret }
      threshold → { metric, operator, value, cooldown_seconds }
      api_poll  → { url, headers, poll_interval_seconds }
      schedule  → { cron_expression }
    """
    __tablename__ = "event_triggers"

    name = Column(String(200), nullable=False)
    trigger_type = Column(
        Enum(TriggerType, name="triggertype", create_constraint=True),
        nullable=False,
    )
    config = Column(JSON, nullable=False, default=dict)

    # Optional FK links — what to do when the trigger fires
    target_workflow_id = Column(
        String(36), ForeignKey("workflows.id", ondelete="SET NULL"), nullable=True,
    )
    target_agent_id = Column(
        String(36), ForeignKey("agents.id", ondelete="SET NULL"), nullable=True,
    )

    last_fired_at = Column(DateTime, nullable=True)
    fire_count = Column(Integer, nullable=False, default=0, server_default="0")

    # Circuit-breaker fields for event rate-limiting
    max_fires_per_minute = Column(Integer, nullable=False, default=10, server_default="10")
    pause_duration_seconds = Column(Integer, nullable=False, default=300, server_default="300")
    paused_until = Column(DateTime, nullable=True)

    # Relationships
    event_logs = relationship(
        "EventLog", back_populates="trigger",
        lazy="dynamic", cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get("agentium_id"):
            self.agentium_id = self._generate_trigger_id()

    def _generate_trigger_id(self) -> str:
        """Generate trigger ID: ET + 5-digit sequence."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM event_triggers
                WHERE agentium_id ~ '^ET[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC
                LIMIT 1
            """)).scalar()
            if result:
                next_num = int(result[2:]) + 1
            else:
                next_num = 1
            return f"ET{next_num:05d}"

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "name": self.name,
            "trigger_type": self.trigger_type.value if self.trigger_type else None,
            "config": self.config,
            "target_workflow_id": self.target_workflow_id,
            "target_agent_id": self.target_agent_id,
            "last_fired_at": self.last_fired_at.isoformat() if self.last_fired_at else None,
            "fire_count": self.fire_count,
            "max_fires_per_minute": self.max_fires_per_minute,
            "pause_duration_seconds": self.pause_duration_seconds,
            "paused_until": self.paused_until.isoformat() if self.paused_until else None,
        })
        return base


# ── EventLog ──────────────────────────────────────────────────────────────────

class EventLog(BaseEntity):
    """
    Every time a trigger fires, an EventLog row is created.
    Tracks payload, processing status, and correlation for deduplication.
    """
    __tablename__ = "event_logs"

    trigger_id = Column(
        String(36), ForeignKey("event_triggers.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    event_payload = Column(JSON, nullable=False, default=dict)
    status = Column(
        Enum(EventLogStatus, name="eventlogstatus", create_constraint=True),
        nullable=False, default=EventLogStatus.PROCESSED,
    )
    correlation_id = Column(String(36), nullable=True, index=True)
    error = Column(Text, nullable=True)
    retry_count = Column(Integer, nullable=False, default=0, server_default="0")

    # Relationships
    trigger = relationship("EventTrigger", back_populates="event_logs")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get("agentium_id"):
            self.agentium_id = self._generate_log_id()

    def _generate_log_id(self) -> str:
        """Generate log ID: EL + 5-digit sequence."""
        from backend.models.database import get_db_context
        from sqlalchemy import text
        with get_db_context() as db:
            result = db.execute(text("""
                SELECT agentium_id FROM event_logs
                WHERE agentium_id ~ '^EL[0-9]+$'
                ORDER BY CAST(SUBSTRING(agentium_id FROM 3) AS INTEGER) DESC
                LIMIT 1
            """)).scalar()
            if result:
                next_num = int(result[2:]) + 1
            else:
                next_num = 1
            return f"EL{next_num:05d}"

    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            "trigger_id": self.trigger_id,
            "event_payload": self.event_payload,
            "status": self.status.value if self.status else None,
            "correlation_id": self.correlation_id,
            "error": self.error,
            "retry_count": self.retry_count,
        })
        return base
