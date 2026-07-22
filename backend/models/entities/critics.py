"""
Critic Agent models for Agentium.
Critics operate OUTSIDE the democratic chain with absolute veto authority.
Three types: CodeCritic (4xxxx), OutputCritic (5xxxx), PlanCritic (6xxxx).
"""

from datetime import datetime
from typing import Optional, Dict, Any, List
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Float, JSON
from sqlalchemy.orm import relationship, Session
from .base import BaseEntity
from .agents import Agent, AgentType, AgentStatus
import enum


class CriticType(str, enum.Enum):
    """Types of critic agents."""
    CODE = "code"        # Validates code syntax, security, logic
    OUTPUT = "output"    # Validates against user intent
    PLAN = "plan"        # Validates execution DAG soundness


class CriticVerdict(str, enum.Enum):
    """Possible outcomes of a critic review."""
    PASS = "pass"              # Output approved
    REJECT = "reject"          # Output rejected, retry within team
    ESCALATE = "escalate"      # Max retries exceeded, escalate to Council


# Map CriticType → AgentType for routing
CRITIC_TYPE_TO_AGENT_TYPE = {
    CriticType.CODE: AgentType.CODE_CRITIC,
    CriticType.OUTPUT: AgentType.OUTPUT_CRITIC,
    CriticType.PLAN: AgentType.PLAN_CRITIC,
}


class CriticAgent(Agent):
    """
    Critic agent — operates outside the democratic chain.
    
    Key principles:
    - Does NOT vote on amendments or participate in Council decisions
    - Has ABSOLUTE veto authority over task outputs
    - Rejections retry within the same team (no Council escalation)
    - Uses different AI models than executors (orthogonal failure modes)
    """
    
    __tablename__ = 'critic_agents'
    
    id = Column(String(36), ForeignKey('agents.id'), primary_key=True)
    
    # Critic specialization
    critic_specialty = Column(Enum(CriticType), nullable=False)
    
    # Performance tracking
    reviews_completed = Column(Integer, default=0)
    vetoes_issued = Column(Integer, default=0)
    escalations_issued = Column(Integer, default=0)
    passes_issued = Column(Integer, default=0)
    avg_review_time_ms = Column(Float, default=0.0)
    
    # Model orthogonality — critics should use a different model than executors
    preferred_review_model = Column(String(100), nullable=True)
    
    __mapper_args__ = {
        'polymorphic_identity': AgentType.CODE_CRITIC,  # default; overridden per instance
    }
    
    def __init__(self, **kwargs):
        critic_type = kwargs.pop('critic_specialty', CriticType.CODE)
        
        # Map critic specialty to the correct AgentType
        agent_type_map = {
            CriticType.CODE: AgentType.CODE_CRITIC,
            CriticType.OUTPUT: AgentType.OUTPUT_CRITIC,
            CriticType.PLAN: AgentType.PLAN_CRITIC,
        }
        kwargs['agent_type'] = agent_type_map.get(critic_type, AgentType.CODE_CRITIC)
        kwargs['critic_specialty'] = critic_type
        super().__init__(**kwargs)
    
    def record_review(self, verdict: CriticVerdict, duration_ms: float = 0):
        """Record the outcome of a review."""
        self.reviews_completed += 1
        
        if verdict == CriticVerdict.PASS:
            self.passes_issued += 1
        elif verdict == CriticVerdict.REJECT:
            self.vetoes_issued += 1
        elif verdict == CriticVerdict.ESCALATE:
            self.escalations_issued += 1
        
        # Rolling average of review time
        if self.reviews_completed > 1:
            self.avg_review_time_ms = (
                (self.avg_review_time_ms * (self.reviews_completed - 1) + duration_ms) 
                / self.reviews_completed
            )
        else:
            self.avg_review_time_ms = duration_ms
    
    @property
    def approval_rate(self) -> float:
        """Percentage of reviews that passed."""
        if self.reviews_completed == 0:
            return 0.0
        return (self.passes_issued / self.reviews_completed) * 100
    
    @property
    def veto_rate(self) -> float:
        """Percentage of reviews that were vetoed."""
        if self.reviews_completed == 0:
            return 0.0
        return (self.vetoes_issued / self.reviews_completed) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'critic_specialty': self.critic_specialty.value,
            'reviews_completed': self.reviews_completed,
            'vetoes_issued': self.vetoes_issued,
            'escalations_issued': self.escalations_issued,
            'passes_issued': self.passes_issued,
            'approval_rate': round(self.approval_rate, 1),
            'veto_rate': round(self.veto_rate, 1),
            'avg_review_time_ms': round(self.avg_review_time_ms, 1),
            'preferred_review_model': self.preferred_review_model,
        })
        return base


class OutputCriticAgent(CriticAgent):
    """
    Output critic (8xxxx) — single-table subclass of CriticAgent.

    Shares the `critic_agents` table with the other critic types; the distinct
    `polymorphic_identity` lets SQLAlchemy resolve `output_critic` rows on load.
    """

    __mapper_args__ = {
        'polymorphic_identity': AgentType.OUTPUT_CRITIC,
    }


class PlanCriticAgent(CriticAgent):
    """
    Plan critic (9xxxx) — single-table subclass of CriticAgent.

    Shares the `critic_agents` table with the other critic types; the distinct
    `polymorphic_identity` lets SQLAlchemy resolve `plan_critic` rows on load.
    """

    __mapper_args__ = {
        'polymorphic_identity': AgentType.PLAN_CRITIC,
    }


class CritiqueReview(BaseEntity):
    """
    Individual review record linking a task output to a critic's verdict.
    Tracks retry attempts and enforces the 5-retry maximum before escalation.
    """
    
    __tablename__ = 'critique_reviews'
    
    # What was reviewed
    task_id = Column(String(36), ForeignKey('tasks.id'), nullable=False, index=True)
    subtask_id = Column(String(36), ForeignKey('subtasks.id'), nullable=True)
    
    # Who reviewed it
    critic_type = Column(Enum(CriticType), nullable=False)
    critic_agentium_id = Column(String(10), nullable=False, index=True)
    
    # Review outcome
    verdict = Column(Enum(CriticVerdict), nullable=False)
    rejection_reason = Column(Text, nullable=True)
    suggestions = Column(Text, nullable=True)  # Improvement hints for the executor
    
    # Retry tracking
    retry_count = Column(Integer, default=0, nullable=False)
    max_retries = Column(Integer, default=5, nullable=False)
    
    # Metadata
    review_duration_ms = Column(Float, default=0.0)
    model_used = Column(String(100), nullable=True)  # Track which model did the review
    output_hash = Column(String(64), nullable=True)   # SHA-256 of reviewed output (dedup)
    
    # Phase 6.3: Per-criterion evaluation results
    criteria_results = Column(JSON, nullable=True)    # List[CriterionResult.to_dict()]
    criteria_evaluated = Column(Integer, nullable=True)
    criteria_passed = Column(Integer, nullable=True)
    
    # Timestamps
    reviewed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    # Phase 10.4: Autonomous Learning tracking
    learning_extracted = Column("learning_extracted", Integer, default=0, nullable=False)
    
    # Relationships
    task = relationship("Task", foreign_keys=[task_id])
    
    @property
    def can_retry(self) -> bool:
        """Check if the task can be retried after rejection."""
        return self.retry_count < self.max_retries
    
    @property
    def should_escalate(self) -> bool:
        """Check if max retries exhausted and escalation is needed."""
        return self.verdict == CriticVerdict.REJECT and self.retry_count >= self.max_retries
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'task_id': self.task_id,
            'subtask_id': self.subtask_id,
            'critic_type': self.critic_type.value,
            'critic_agentium_id': self.critic_agentium_id,
            'verdict': self.verdict.value,
            'rejection_reason': self.rejection_reason,
            'suggestions': self.suggestions,
            'retry_count': self.retry_count,
            'max_retries': self.max_retries,
            'can_retry': self.can_retry,
            'review_duration_ms': self.review_duration_ms,
            'model_used': self.model_used,
            'reviewed_at': self.reviewed_at.isoformat() if self.reviewed_at else None,
            # Phase 6.3
            'criteria_results': self.criteria_results or [],
            'criteria_evaluated': self.criteria_evaluated,
            'criteria_passed': self.criteria_passed,
            'criteria_failed': (
                (self.criteria_evaluated - self.criteria_passed)
                if self.criteria_evaluated is not None and self.criteria_passed is not None
                else None
            ),
            'learning_extracted': bool(self.learning_extracted),
        })
        return base