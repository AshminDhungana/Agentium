"""
Voting and deliberation system for Agentium.
Handles democratic decision-making for tasks and constitutional amendments.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, JSON, CheckConstraint, Index
from sqlalchemy.orm import relationship, validates
from backend.models.entities.base import BaseEntity
import enum

class VoteType(str, enum.Enum):
    """Types of votes a council member can cast."""
    FOR = "for"
    AGAINST = "against"
    ABSTAIN = "abstain"

class DeliberationStatus(str, enum.Enum):
    """Status of a deliberation session."""
    PENDING = "pending"           # Waiting to start
    ACTIVE = "active"             # Voting open
    QUORUM_REACHED = "quorum"     # Minimum votes received
    CONCLUDED = "concluded"       # Voting closed, result calculated
    EXECUTED = "executed"         # Decision acted upon

class AmendmentStatus(str, enum.Enum):
    """Status of a constitutional amendment voting process."""
    PROPOSED = "proposed"
    DELIBERATING = "deliberating"
    VOTING = "voting"
    PASSED = "passed"
    REJECTED = "rejected"
    RATIFIED = "ratified"

class AmendmentVoting(BaseEntity):
    """
    Voting process for a constitutional amendment.
    Requires strict quorum and supermajority.
    """
    
    __tablename__ = 'amendment_votings'
    
    amendment_id = Column(String(36), ForeignKey('constitutions.id'), nullable=False)
    
    # Configuration
    eligible_voters = Column(JSON, nullable=False)  # List of Council Member IDs
    required_votes = Column(Integer, default=3, nullable=False)
    supermajority_threshold = Column(Integer, default=66)  # Percentage (e.g., 66%)
    
    # Status
    status = Column(Enum(AmendmentStatus), default=AmendmentStatus.PROPOSED, nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    
    # Results
    votes_for = Column(Integer, default=0)
    votes_against = Column(Integer, default=0)
    votes_abstain = Column(Integer, default=0)
    final_result = Column(String(20), nullable=True)
    
    # Relationships
    amendment = relationship("Constitution", back_populates="voting_sessions")
    individual_votes = relationship("IndividualVote", back_populates="amendment_voting", lazy="dynamic")
    
    # Discussion
    discussion_thread = Column(JSON, default=list)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = f"AV{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
    def start_voting(self):
        """Open voting session."""
        self.status = AmendmentStatus.VOTING
        self.started_at = datetime.utcnow()
        self.add_discussion_entry("System", "Amendment voting session started.")
        
    def cast_vote(self, council_member_id: str, vote: VoteType, rationale: str = None) -> 'IndividualVote':
        """Cast a vote on the amendment."""
        if self.status != AmendmentStatus.VOTING:
            raise ValueError("Voting is not currently open")
            
        if council_member_id not in self.eligible_voters:
            raise PermissionError("Agent is not eligible to vote on this amendment")
            
        # Check if already voted
        existing = self.individual_votes.filter_by(voter_agentium_id=council_member_id).first()
        if existing:
            # Revoke old vote logic would go here
            self._revoke_vote(existing.vote)
            existing.vote = vote
            existing.rationale = rationale
            existing.changed_at = datetime.utcnow()
            vote_record = existing
        else:
            vote_record = IndividualVote(
                amendment_voting_id=self.id,
                voter_agentium_id=council_member_id,
                vote=vote,
                rationale=rationale,
                agentium_id=f"V{council_member_id}"
            )
            self.individual_votes.append(vote_record)
            
        self._apply_vote(vote)
        
        # Log vote
        if rationale:
            self.add_discussion_entry(council_member_id, f"Voted {vote.value}. Reason: {rationale}")
            
        return vote_record

    def _apply_vote(self, vote: VoteType):
        """Increment counters."""
        if vote == VoteType.FOR:
            self.votes_for += 1
        elif vote == VoteType.AGAINST:
            self.votes_against += 1
        elif vote == VoteType.ABSTAIN:
            self.votes_abstain += 1
            
    def _revoke_vote(self, vote: VoteType):
        """Decrement counters."""
        if vote == VoteType.FOR:
            self.votes_for -= 1
        elif vote == VoteType.AGAINST:
            self.votes_against -= 1
        elif vote == VoteType.ABSTAIN:
            self.votes_abstain -= 1

    def conclude(self) -> Dict[str, Any]:
        """Concluding the voting process."""
        self.status = AmendmentStatus.PASSED # Logic to determine pass/fail
        total_votes = self.votes_for + self.votes_against + self.votes_abstain
        if total_votes == 0:
             self.status = AmendmentStatus.REJECTED
             self.final_result = "rejected"
        else:
            percent_for = (self.votes_for / total_votes) * 100
            if percent_for >= self.supermajority_threshold:
                 self.status = AmendmentStatus.PASSED
                 self.final_result = "passed"
            else:
                 self.status = AmendmentStatus.REJECTED
                 self.final_result = "rejected"
                 
        self.ended_at = datetime.utcnow()
        self.add_discussion_entry("System", f"Voting concluded. Result: {self.final_result}")
        
        return {
            "result": self.final_result,
            "votes_for": self.votes_for, 
            "votes_against": self.votes_against
        }

    def add_discussion_entry(self, agentium_id: str, message: str):
        """Add entry to discussion."""
        thread = self.discussion_thread or []
        thread.append({
            'timestamp': datetime.utcnow().isoformat(),
            'agent': agentium_id,
            'message': message
        })
        self.discussion_thread = thread
        
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
             "status": self.status.value,
             "votes_for": self.votes_for,
             "votes_against": self.votes_against,
             "result": self.final_result
        })
        return base


class TaskDeliberation(BaseEntity):
    """
    Deliberation session for a specific task.
    Council Members debate and vote on whether a task should be approved.
    """
    
    __tablename__ = 'task_deliberations'
    
    task_id = Column(String(36), ForeignKey('tasks.id'), nullable=False)
    
    # Configuration
    participating_members = Column(JSON, nullable=False)  # Array of Council Member IDs
    required_approvals = Column(Integer, default=2, nullable=False)  # Minimum yes votes needed
    min_quorum = Column(Integer, default=2)  # Minimum total votes required
    
    # Status
    status = Column(Enum(DeliberationStatus), default=DeliberationStatus.PENDING, nullable=False)
    started_at = Column(DateTime, nullable=True)
    ended_at = Column(DateTime, nullable=True)
    time_limit_minutes = Column(Integer, default=30)  # Voting window
    
    # Results
    votes_for = Column(Integer, default=0)
    votes_against = Column(Integer, default=0)
    votes_abstain = Column(Integer, default=0)
    final_decision = Column(String(20), nullable=True)  # approved/rejected/tie
    
    # Head of Council override
    head_overridden = Column(Boolean, default=False)
    head_override_reason = Column(Text, nullable=True)
    head_override_at = Column(DateTime, nullable=True)
    
    # Relationships
    task = relationship("Task", back_populates="deliberation")
    individual_votes = relationship("IndividualVote", back_populates="task_deliberation", lazy="dynamic")
    
    # Discussion thread (JSON array of messages)
    discussion_thread = Column(JSON, default=list)
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if not kwargs.get('agentium_id'):
            self.agentium_id = f"D{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
    
    def start(self):
        """Open voting."""
        self.status = DeliberationStatus.ACTIVE
        self.started_at = datetime.utcnow()
        self.add_discussion_entry("System", "Deliberation started. Voting is now open.")
    
    def cast_vote(self, council_member_id: str, vote: VoteType, rationale: str = None) -> 'IndividualVote':
        """
        Record a vote from a council member.
        Returns the IndividualVote record.
        """
        if self.status != DeliberationStatus.ACTIVE:
            raise ValueError("Voting is not currently open")
        
        if council_member_id not in self.participating_members:
            raise PermissionError("Agent is not part of this deliberation")
        
        # Check if already voted
        existing = self.individual_votes.filter_by(voter_agentium_id=council_member_id).first()
        if existing:
            # Revoke old vote
            self._revoke_vote(existing.vote)
            existing.vote = vote
            existing.rationale = rationale
            existing.changed_at = datetime.utcnow()
            vote_record = existing
        else:
            # Create new vote
            vote_record = IndividualVote(
                task_deliberation_id=self.id,
                voter_agentium_id=council_member_id,
                vote=vote,
                rationale=rationale,
                agentium_id=f"V{council_member_id}"  # Vote ID format
            )
            self.individual_votes.append(vote_record)
        
        # Apply new vote
        self._apply_vote(vote)
        
        # Check quorum
        total_votes = self.votes_for + self.votes_against + self.votes_abstain
        if total_votes >= self.min_quorum:
            self.status = DeliberationStatus.QUORUM_REACHED
        
        # Add to discussion if rationale provided
        if rationale:
            self.add_discussion_entry(council_member_id, f"Voted {vote.value}. Reason: {rationale}")
        
        return vote_record
    
    def _apply_vote(self, vote: VoteType):
        """Increment appropriate counter."""
        if vote == VoteType.FOR:
            self.votes_for += 1
        elif vote == VoteType.AGAINST:
            self.votes_against += 1
        elif vote == VoteType.ABSTAIN:
            self.votes_abstain += 1
    
    def _revoke_vote(self, vote: VoteType):
        """Decrement counter for changed vote."""
        if vote == VoteType.FOR:
            self.votes_for -= 1
        elif vote == VoteType.AGAINST:
            self.votes_against -= 1
        elif vote == VoteType.ABSTAIN:
            self.votes_abstain -= 1
    
    def conclude(self) -> Dict[str, Any]:
        """Close voting and calculate result."""
        if self.status not in [DeliberationStatus.ACTIVE, DeliberationStatus.QUORUM_REACHED]:
            raise ValueError("Cannot conclude deliberation that is not active")
        
        self.status = DeliberationStatus.CONCLUDED
        self.ended_at = datetime.utcnow()
        
        # Determine outcome
        if self.votes_for >= self.required_approvals and self.votes_for > self.votes_against:
            self.final_decision = "approved"
        elif self.votes_against >= self.required_approvals or self.votes_against > self.votes_for:
            self.final_decision = "rejected"
        else:
            self.final_decision = "tie"
        
        result = {
            'decision': self.final_decision,
            'votes_for': self.votes_for,
            'votes_against': self.votes_against,
            'votes_abstain': self.votes_abstain,
            'participation_rate': (self.votes_for + self.votes_against + self.votes_abstain) / len(self.participating_members)
        }
        
        self.add_discussion_entry("System", f"Deliberation concluded. Result: {self.final_decision}")
        
        # Update task status
        if self.task:
            if self.final_decision == "approved":
                self.task.approve_by_council(self.votes_for, self.votes_against)
            else:
                self.task.approve_by_council(0, 1)  # Will set to rejected
        
        return result
    
    def emergency_override(self, head_agentium_id: str, reason: str, approve: bool = True):
        """
        Head of Council emergency override.
        Bypasses normal voting process.
        """
        self.head_overridden = True
        self.head_override_reason = reason
        self.head_override_at = datetime.utcnow()
        self.final_decision = "approved" if approve else "rejected"
        self.status = DeliberationStatus.CONCLUDED
        
        self.add_discussion_entry(head_agentium_id, f"EMERGENCY OVERRIDE: {reason}")
        
        if self.task:
            if approve:
                self.task.approve_by_council(999, 0)  # Simulated unanimous
            else:
                self.task.approve_by_council(0, 999)
    
    def add_discussion_entry(self, agentium_id: str, message: str):
        """Add a message to the deliberation thread."""
        thread = self.discussion_thread or []
        thread.append({
            'timestamp': datetime.utcnow().isoformat(),
            'agent': agentium_id,
            'message': message
        })
        self.discussion_thread = thread
    
    def get_participation_rate(self) -> float:
        """Calculate what percentage of council members voted."""
        if not self.participating_members:
            return 0.0
        total_votes = self.votes_for + self.votes_against + self.votes_abstain
        return (total_votes / len(self.participating_members)) * 100
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'task_id': self.task.agentium_id if self.task else None,
            'status': self.status.value,
            'participants': self.participating_members,
            'votes': {
                'for': self.votes_for,
                'against': self.votes_against,
                'abstain': self.votes_abstain,
                'required': self.required_approvals
            },
            'result': self.final_decision,
            'participation_rate': self.get_participation_rate(),
            'discussion': self.discussion_thread[-10:] if self.discussion_thread else [],  # Last 10 messages
            'overridden': self.head_overridden,
            'timing': {
                'started': self.started_at.isoformat() if self.started_at else None,
                'ended': self.ended_at.isoformat() if self.ended_at else None
            }
        })
        return base


class IndividualVote(BaseEntity):
    """
    Individual vote record for audit and transparency.
    Tracks how each council member voted on each issue.
    """
    
    __tablename__ = 'individual_votes'
    
    # Can be associated with either task deliberation or amendment voting
    task_deliberation_id = Column(String(36), ForeignKey('task_deliberations.id'), nullable=True)
    amendment_voting_id = Column(String(36), ForeignKey('amendment_votings.id'), nullable=True)
    
    # Vote details
    voter_agentium_id = Column(String(10), ForeignKey('agents.agentium_id'), nullable=False)
    vote = Column(Enum(VoteType), nullable=False)
    rationale = Column(Text, nullable=True)  # Why they voted this way
    
    # Change tracking (voters can change their mind during deliberation)
    vote_changed = Column(Boolean, default=False)
    original_vote = Column(Enum(VoteType), nullable=True)
    changed_at = Column(DateTime, nullable=True)
    
    # Relations
    task_deliberation = relationship("TaskDeliberation", back_populates="individual_votes")
    amendment_voting = relationship("AmendmentVoting", back_populates="individual_votes")
    council_member = relationship("Agent", foreign_keys=[voter_agentium_id])
    
    __table_args__ = (
        CheckConstraint(
            '(task_deliberation_id IS NOT NULL) OR (amendment_voting_id IS NOT NULL)',
            name='check_vote_has_parent'
        ),
    )
    
    def change_vote(self, new_vote: VoteType, new_rationale: str = None):
        """Allow council member to change their vote during deliberation."""
        if not self.vote_changed:
            self.original_vote = self.vote
            self.vote_changed = True
        
        self.vote = new_vote
        self.rationale = new_rationale or self.rationale
        self.changed_at = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'voter': self.voter_agentium_id,
            'vote': self.vote.value,
            'rationale': self.rationale,
            'changed': self.vote_changed,
            'original_vote': self.original_vote.value if self.original_vote else None
        })
        return base


class VotingRecord(BaseEntity):
    """
    Historical record of voting statistics for agents.
    Used for analytics and agent performance evaluation.
    """
    
    __tablename__ = 'voting_records'
    
    agentium_id = Column(String(10), ForeignKey('agents.agentium_id'), nullable=False)
    period_start = Column(DateTime, nullable=False)  # Weekly/monthly aggregation
    period_end = Column(DateTime, nullable=False)
    
    # Statistics
    total_votes_cast = Column(Integer, default=0)
    votes_for = Column(Integer, default=0)
    votes_against = Column(Integer, default=0)
    votes_abstain = Column(Integer, default=0)
    votes_changed = Column(Integer, default=0)  # Changed mind during deliberation
    
    # Participation
    deliberations_participated = Column(Integer, default=0)
    deliberations_missed = Column(Integer, default=0)
    avg_participation_rate = Column(Integer, default=0)  # Percentage
    
    # Influence
    proposals_made = Column(Integer, default=0)
    proposals_accepted = Column(Integer, default=0)
    
    @classmethod
    def generate_for_period(cls, agentium_id: str, start: datetime, end: datetime, session):
        """Generate voting statistics for an agent over a time period."""
        # Query all votes by this agent in period
        votes = session.query(IndividualVote).filter(
            IndividualVote.voter_agentium_id == agentium_id,
            IndividualVote.created_at >= start,
            IndividualVote.created_at <= end
        ).all()
        
        if not votes:
            return None
        
        stats = {
            'total': len(votes),
            'for': sum(1 for v in votes if v.vote == VoteType.FOR),
            'against': sum(1 for v in votes if v.vote == VoteType.AGAINST),
            'abstain': sum(1 for v in votes if v.vote == VoteType.ABSTAIN),
            'changed': sum(1 for v in votes if v.vote_changed)
        }
        
        record = cls(
            agentium_id=agentium_id or f"R{agentium_id}{start.strftime('%Y%m%d')}",
            period_start=start,
            period_end=end,
            **stats
        )
        
        return record
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'agent': self.agentium_id,
            'period': {
                'start': self.period_start.isoformat(),
                'end': self.period_end.isoformat()
            },
            'votes': {
                'total': self.total_votes_cast,
                'breakdown': {
                    'for': self.votes_for,
                    'against': self.votes_against,
                    'abstain': self.votes_abstain
                },
                'changed_mind': self.votes_changed
            },
            'participation': {
                'attended': self.deliberations_participated,
                'missed': self.deliberations_missed,
                'rate': self.avg_participation_rate
            },
            'influence': {
                'proposals': self.proposals_made,
                'accepted': self.proposals_accepted
            }
        })
        return base