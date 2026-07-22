"""
ReasoningTrace database entity.
Stores the sealed trace summary produced by ReasoningTraceService.
"""

from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean, Text, DateTime,
    ForeignKey, JSON
)
from sqlalchemy.orm import relationship

from .base import BaseEntity


class ReasoningTraceModel(BaseEntity):
    """
    One row per task execution attempt by one agent.
    """
    __tablename__ = "reasoning_traces"

    # ── Identity ──────────────────────────────────────────────────────────────
    trace_id   = Column(String(64),  nullable=False, unique=True, index=True)
    task_id    = Column(String(64),  nullable=False, index=True)
    agent_id   = Column(String(32),  nullable=False, index=True)
    agent_tier = Column(Integer,     nullable=False, default=3)
    incarnation = Column(Integer,    nullable=False, default=1)

    # ── Goal ──────────────────────────────────────────────────────────────────
    goal          = Column(Text, nullable=False)
    goal_restated = Column(Text, nullable=True)

    # ── Plan & context ────────────────────────────────────────────────────────
    plan             = Column(JSON, nullable=True)   # List[str]
    skills_used      = Column(JSON, nullable=True)   # List[str]
    context_summary  = Column(Text, nullable=True)

    # ── Outcome ───────────────────────────────────────────────────────────────
    current_phase      = Column(String(32),  nullable=False, default="goal_interpretation")
    final_outcome      = Column(String(16),  nullable=True)   # "success" | "failure"
    failure_reason     = Column(Text,        nullable=True)
    validation_passed  = Column(Boolean,     nullable=True)
    validation_notes   = Column(Text,        nullable=True)

    # ── Performance ───────────────────────────────────────────────────────────
    total_tokens      = Column(Integer, nullable=False, default=0)
    total_duration_ms = Column(Float,   nullable=False, default=0.0)

    # ── Timestamps ────────────────────────────────────────────────────────────
    started_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # ── Steps (child) ─────────────────────────────────────────────────────────
    steps = relationship(
        "ReasoningStepModel",
        back_populates="trace",
        cascade="all, delete-orphan",
        order_by="ReasoningStepModel.sequence",
    )

    def to_dict(self):
        return {
            "trace_id":          self.trace_id,
            "task_id":           self.task_id,
            "agent_id":          self.agent_id,
            "agent_tier":        self.agent_tier,
            "incarnation":       self.incarnation,
            "goal":              self.goal,
            "goal_restated":     self.goal_restated,
            "plan":              self.plan or [],
            "skills_used":       self.skills_used or [],
            "context_summary":   self.context_summary,
            "current_phase":     self.current_phase,
            "final_outcome":     self.final_outcome,
            "failure_reason":    self.failure_reason,
            "validation_passed": self.validation_passed,
            "validation_notes":  self.validation_notes,
            "total_tokens":      self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "started_at":        self.started_at.isoformat() if self.started_at else None,
            "completed_at":      self.completed_at.isoformat() if self.completed_at else None,
            "steps":             [s.to_dict() for s in self.steps],
        }


class ReasoningStepModel(BaseEntity):
    """
    One row per step within a ReasoningTrace.
    """
    __tablename__ = "reasoning_steps"

    # ── Parent ────────────────────────────────────────────────────────────────
    trace_db_id = Column(String(36), ForeignKey("reasoning_traces.id"), nullable=False, index=True)
    trace       = relationship("ReasoningTraceModel", back_populates="steps")

    # ── Identity ──────────────────────────────────────────────────────────────
    step_id    = Column(String(80), nullable=False, index=True)
    phase      = Column(String(32), nullable=False)
    sequence   = Column(Integer,    nullable=False)

    # ── Content ───────────────────────────────────────────────────────────────
    description  = Column(Text, nullable=False)
    rationale    = Column(Text, nullable=False)
    alternatives = Column(JSON, nullable=True)   # List[str]
    inputs       = Column(JSON, nullable=True)
    outputs      = Column(JSON, nullable=True)

    # ── Outcome ───────────────────────────────────────────────────────────────
    outcome     = Column(String(16), nullable=False, default="pending")
    error       = Column(Text,       nullable=True)
    tokens_used = Column(Integer,    nullable=False, default=0)
    duration_ms = Column(Float,      nullable=False, default=0.0)

    # ── Timestamps ────────────────────────────────────────────────────────────
    started_at   = Column(DateTime, nullable=False, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    def to_dict(self):
        return {
            "step_id":      self.step_id,
            "phase":        self.phase,
            "sequence":     self.sequence,
            "description":  self.description,
            "rationale":    self.rationale,
            "alternatives": self.alternatives or [],
            "inputs":       self.inputs or {},
            "outputs":      self.outputs or {},
            "outcome":      self.outcome,
            "error":        self.error,
            "tokens_used":  self.tokens_used,
            "duration_ms":  self.duration_ms,
            "started_at":   self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }