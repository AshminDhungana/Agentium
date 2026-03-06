"""
A/B Testing Framework - Database Entities

"""

import uuid
import enum
from datetime import datetime
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean,
    DateTime, ForeignKey, Enum, Index, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from backend.models.entities.base import Base


# ── Enums ─────────────────────────────────────────────────────────────────────

class ExperimentStatus(str, enum.Enum):
    DRAFT     = "draft"
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"
    CANCELLED = "cancelled"


class RunStatus(str, enum.Enum):
    PENDING   = "pending"
    RUNNING   = "running"
    COMPLETED = "completed"
    FAILED    = "failed"


class TaskComplexity(str, enum.Enum):
    SIMPLE  = "simple"
    MEDIUM  = "medium"
    COMPLEX = "complex"


# ── Experiment ────────────────────────────────────────────────────────────────

class Experiment(Base):
    """A/B test experiment definition."""
    __tablename__ = "experiments"
    __table_args__ = (
        # Fast status-filtered list queries (most common access pattern)
        Index("ix_experiments_status", "status"),
        # Fast time-ordered listing
        Index("ix_experiments_created_at", "created_at"),
        # Combined index for admin user's experiment list
        Index("ix_experiments_created_by_status", "created_by", "status"),
    )

    id          = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name        = Column(String(200), nullable=False)
    description = Column(Text)

    # Test configuration
    task_template   = Column(Text, nullable=False)
    system_prompt   = Column(Text)
    test_iterations = Column(Integer, default=1)

    # Ownership & status
    created_by  = Column(String(100), default="unknown", nullable=False)
    status      = Column(Enum(ExperimentStatus), default=ExperimentStatus.DRAFT, nullable=False)
    created_at  = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at  = Column(DateTime)
    completed_at = Column(DateTime)

    # Relationships
    runs    = relationship("ExperimentRun",    back_populates="experiment", cascade="all, delete-orphan", lazy="select")
    results = relationship("ExperimentResult", back_populates="experiment", cascade="all, delete-orphan", lazy="select")


# ── ExperimentRun ─────────────────────────────────────────────────────────────

class ExperimentRun(Base):
    """Single execution of a model within an experiment."""
    __tablename__ = "experiment_runs"
    __table_args__ = (
        # Fast bulk-load of all runs for one experiment (used in detail view)
        Index("ix_runs_experiment_id", "experiment_id"),
        # Filter runs by status within an experiment
        Index("ix_runs_experiment_status", "experiment_id", "status"),
    )

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey("experiments.id"), nullable=False)

    # Model configuration
    config_id        = Column(String(36), ForeignKey("user_model_configs.id"))
    model_name       = Column(String(100))
    iteration_number = Column(Integer, default=1)

    # Lifecycle
    status       = Column(Enum(RunStatus), default=RunStatus.PENDING, nullable=False)
    started_at   = Column(DateTime)
    completed_at = Column(DateTime)
    error_message = Column(Text)

    # Raw output
    output_text  = Column(Text)
    tokens_used  = Column(Integer)
    latency_ms   = Column(Integer)
    cost_usd     = Column(Float)

    # Quality metrics (populated by CriticService)
    critic_plan_score        = Column(Float)
    critic_code_score        = Column(Float)
    critic_output_score      = Column(Float)
    overall_quality_score    = Column(Float)
    critic_feedback          = Column(JSON)
    constitutional_violations = Column(Integer, default=0)

    # Relationships
    experiment = relationship("Experiment", back_populates="runs")
    config     = relationship("UserModelConfig")


# ── ExperimentResult ──────────────────────────────────────────────────────────

class ExperimentResult(Base):
    """Aggregated results comparing all models in an experiment."""
    __tablename__ = "experiment_results"
    __table_args__ = (
        Index("ix_results_experiment_id", "experiment_id"),
    )

    id            = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    experiment_id = Column(String(36), ForeignKey("experiments.id"), nullable=False)

    # Winner
    winner_config_id  = Column(String(36), ForeignKey("user_model_configs.id"))
    winner_model_name = Column(String(100))
    selection_reason  = Column(Text)

    # Aggregate metrics (JSON blob — schema documented in ModelComparison TS type)
    model_comparisons      = Column(JSON)
    statistical_significance = Column(Float)

    # Recommendation metadata
    recommended_for_similar = Column(Boolean, default=False)
    confidence_score        = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    experiment    = relationship("Experiment", back_populates="results")
    winner_config = relationship("UserModelConfig")


# ── ModelPerformanceCache ─────────────────────────────────────────────────────

class ModelPerformanceCache(Base):
    """
    Cache of per-category model performance for rapid recommendation.

    One row per task_category (upserted after each completed experiment).
    Rows older than 30 days are excluded from the recommendations endpoint.
    """
    __tablename__ = "model_performance_cache"
    __table_args__ = (
        # Ensure at most one recommendation per category (enables safe upsert)
        UniqueConstraint("task_category", name="uq_perf_cache_task_category"),
        Index("ix_perf_cache_last_updated", "last_updated"),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))

    task_category  = Column(String(50), nullable=False)
    task_complexity = Column(Enum(TaskComplexity))

    best_config_id  = Column(String(36), ForeignKey("user_model_configs.id"))
    best_model_name = Column(String(100))

    avg_latency_ms    = Column(Integer)
    avg_cost_usd      = Column(Float)
    avg_quality_score = Column(Float)
    success_rate      = Column(Float)
    sample_size       = Column(Integer, default=0)

    derived_from_experiment_id = Column(String(36), ForeignKey("experiments.id"))
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    best_config = relationship("UserModelConfig")