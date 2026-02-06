"""
Constitution and Ethos management for Agentium.
The Constitution is the supreme law, while Ethos defines individual agent behavior.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy import Column, String, Text, DateTime, ForeignKey, Integer, Enum, Boolean, event, Index
from sqlalchemy.orm import relationship, validates
from backend.models.entities.base import BaseEntity
from sqlalchemy.orm import remote
import enum

class DocumentType(str, enum.Enum):
    """Types of governance documents."""
    CONSTITUTION = "constitution"
    ETHOS = "ethos"



class Constitution(BaseEntity):
    """
    The Supreme Law of Agentium.
    - Only Head of Council (0xxxx) can modify
    - Updated daily via voting process
    - Read-only for all other entities
    - Supports amendment chaining via replaces_version_id
    """
    
    __tablename__ = 'constitutions'
    
    # Document metadata
    version = Column(String(10), nullable=False, unique=True)  # v1.0.0 format (display)
    version_number = Column(Integer, nullable=False, unique=True)  # Sequential: 1, 2, 3...
    document_type = Column(Enum(DocumentType), default=DocumentType.CONSTITUTION, nullable=False)
    
    # Content sections
    preamble = Column(Text, nullable=True)
    articles = Column(Text, nullable=False)  # JSON string of articles
    prohibited_actions = Column(Text, nullable=False)  # JSON array
    sovereign_preferences = Column(Text, nullable=False)  # JSON object - User's preferences
    changelog = Column(Text, nullable=True)  # JSON array documenting changes from previous version
    
    effective_date = Column(DateTime, default=datetime.utcnow, nullable=False)
    amendment_date = Column(DateTime, nullable=True)
    archived_date = Column(DateTime, nullable=True)
    is_active = Column(String(1), default='Y', nullable=False)
    # Authority
    created_by_agentium_id = Column(String(10), nullable=False)  # Usually 00001 (Head of Council)
    
    amendment_of = Column(String(36), ForeignKey('constitutions.id'), nullable=True)
    replaces_version_id = Column(String(36), ForeignKey('constitutions.id'), nullable=True)

    amendments = relationship(
        "Constitution",
        back_populates="amended_from",
        remote_side=lambda: Constitution.id,  # Lambda to avoid NameError
        cascade="all",
        passive_deletes=True,
    )

    amended_from = relationship(
        "Constitution",
        foreign_keys=[amendment_of],
        back_populates="amendments",
    )

    # Previous version (this replaces an older one) — use string remote_side here
    replaces_version = relationship(
        "Constitution",
        foreign_keys=[replaces_version_id],
        remote_side=["Constitution.id"],           # string notation — safe, no NameError
        # back_populates="replaced_by",            # uncomment only if you define replaced_by below
    )

    # Optional forward: newer versions that replace this one
    # replaced_by = relationship(
    #     "Constitution",
    #     foreign_keys=[replaces_version_id],
    #     remote_side=["Constitution.id"],       # string again
    #     back_populates="replaces_version",
    # )

    # voting_sessions remains unchanged
    voting_sessions = relationship("AmendmentVoting", back_populates="amendment", lazy="dynamic")
    
    def __init__(self, **kwargs):
        # Auto-generate version strings if not provided
        if 'version' not in kwargs and 'version_number' in kwargs:
            kwargs['version'] = f"v{kwargs['version_number']}.0.0"
        elif 'version' not in kwargs:
            kwargs['version'] = f"v{datetime.utcnow().strftime('%Y.%m.%d.%H%M')}"
        
        # Auto-generate version_number if not provided (get next sequential)
        if 'version_number' not in kwargs:
            # This should be handled by service layer, but default to 1
            kwargs['version_number'] = 1
            
        super().__init__(**kwargs)
    
    @validates('version')
    def validate_version(self, key, version):
        if not version.startswith('v'):
            raise ValueError("Version must start with 'v'")
        return version
    
    @validates('version_number')
    def validate_version_number(self, key, version_number):
        if version_number < 1:
            raise ValueError("Version number must be positive integer")
        return version_number
    
    def get_articles_dict(self) -> Dict[str, Any]:
        """Parse articles JSON to dictionary."""
        import json
        try:
            return json.loads(self.articles) if self.articles else {}
        except json.JSONDecodeError:
            return {}
    
    def get_prohibited_actions_list(self) -> List[str]:
        """Parse prohibited actions to list."""
        import json
        try:
            return json.loads(self.prohibited_actions) if self.prohibited_actions else []
        except json.JSONDecodeError:
            return []
    
    def get_sovereign_preferences(self) -> Dict[str, Any]:
        """Parse sovereign preferences to dictionary."""
        import json
        try:
            return json.loads(self.sovereign_preferences) if self.sovereign_preferences else {}
        except json.JSONDecodeError:
            return {}
    
    def get_changelog(self) -> List[Dict[str, Any]]:
        """Parse changelog to list of changes."""
        import json
        try:
            return json.loads(self.changelog) if self.changelog else []
        except json.JSONDecodeError:
            return []
    
    def get_amendment_chain(self) -> List['Constitution']:
        """Get chain of constitutions leading to this one (oldest first)."""
        chain = []
        current = self
        while current.replaces_version:
            chain.insert(0, current.replaces_version)
            current = current.replaces_version
        chain.append(self)
        return chain
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'version': self.version,
            'version_number': self.version_number,
            'document_type': self.document_type.value,
            'preamble': self.preamble,
            'articles': self.get_articles_dict(),
            'prohibited_actions': self.get_prohibited_actions_list(),
            'sovereign_preferences': self.get_sovereign_preferences(),
            'changelog': self.get_changelog(),
            'created_by': self.created_by_agentium_id,
            'amendment_date': self.amendment_date.isoformat() if self.amendment_date else None,
            'effective_date': self.effective_date.isoformat() if self.effective_date else None,
            'replaces_version': self.replaces_version.version if self.replaces_version else None,
            'is_archived': self.archived_date is not None,
            'is_active': self.is_active == 'Y'
        })
        return base
    
    def archive(self):
        """Archive this constitution version when new one takes effect."""
        self.archived_date = datetime.utcnow()
        self.is_active = 'N'

        # Table indexes for Phase 0 verification
    __table_args__ = (
        Index('idx_constitution_version', 'version'),           # Quick version lookup
        Index('idx_constitution_version_number', 'version_number'),  # Chronological sorting
        Index('idx_constitution_active', 'is_active'),          # Active constitution queries
        Index('idx_constitution_effective', 'effective_date'),  # Effective date queries
    )


class Ethos(BaseEntity):
    """
    Individual Agent Ethos - behavioral rules for specific agents.
    Created by higher authority, updated by agent itself, verified by lead.
    """
    
    __tablename__ = 'ethos'
    
    # Identification
    agent_type = Column(String(20), nullable=False)  # head_of_council, council_member, lead_agent, task_agent
    agentium_id = Column(String(10), nullable=True)  # E0xxxx, E1xxxx format for ethos identification
    
    # Content
    mission_statement = Column(Text, nullable=False)
    core_values = Column(Text, nullable=False)  # JSON array
    behavioral_rules = Column(Text, nullable=False)  # JSON array of do's
    restrictions = Column(Text, nullable=False)  # JSON array of don'ts
    capabilities = Column(Text, nullable=False)  # JSON array of what this agent can do
    
    # Authority & versioning
    created_by_agentium_id = Column(String(10), nullable=False)  # Higher authority
    version = Column(Integer, default=1, nullable=False)
    agent_id = Column(String(36), nullable=False)  # Links to specific agent instance
    
    # Verification
    verified_by_agentium_id = Column(String(10), nullable=True)  # Lead/Head who verified
    verified_at = Column(DateTime, nullable=True)
    is_verified = Column(Boolean, default=False)
    
    # Update tracking (agents can update their own ethos)
    last_updated_by_agent = Column(Boolean, default=False)  # True if agent updated itself
    
    def get_core_values(self) -> List[str]:
        import json
        try:
            return json.loads(self.core_values) if self.core_values else []
        except json.JSONDecodeError:
            return []
    
    def get_behavioral_rules(self) -> List[str]:
        import json
        try:
            return json.loads(self.behavioral_rules) if self.behavioral_rules else []
        except json.JSONDecodeError:
            return []
    
    def get_restrictions(self) -> List[str]:
        import json
        try:
            return json.loads(self.restrictions) if self.restrictions else []
        except json.JSONDecodeError:
            return []
    
    def get_capabilities(self) -> List[str]:
        import json
        try:
            return json.loads(self.capabilities) if self.capabilities else []
        except json.JSONDecodeError:
            return []
    
    def verify(self, verifier_agentium_id: str):
        """Mark ethos as verified by a higher authority."""
        self.verified_by_agentium_id = verifier_agentium_id
        self.verified_at = datetime.utcnow()
        self.is_verified = True
    
    def increment_version(self):
        """Increment version when updated."""
        self.version += 1
        self.last_updated_by_agent = True
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base.update({
            'agent_type': self.agent_type,
            'agentium_id': self.agentium_id,
            'mission_statement': self.mission_statement,
            'core_values': self.get_core_values(),
            'behavioral_rules': self.get_behavioral_rules(),
            'restrictions': self.get_restrictions(),
            'capabilities': self.get_capabilities(),
            'version': self.version,
            'created_by': self.created_by_agentium_id,
            'verified': self.is_verified,
            'verified_by': self.verified_by_agentium_id,
            'agent_id': self.agent_id
        })
        return base





# Event listeners for audit trail
@event.listens_for(Constitution, 'after_insert')
def log_constitution_creation(mapper, connection, target):
    """Log when a new constitution is created."""
    from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
    # Create audit log entry
    audit = AuditLog(
        level=AuditLevel.INFO,
        category=AuditCategory.GOVERNANCE,
        actor_type="system",
        actor_id=target.created_by_agentium_id,
        action="constitution_created",
        target_type="constitution",
        target_id=target.agentium_id,
        description=f"Constitution v{target.version} (revision {target.version_number}) created",
        after_state={
            'version': target.version,
            'version_number': target.version_number,
            'effective_date': target.effective_date.isoformat() if target.effective_date else None
        },
        created_at=datetime.utcnow()
    )
    # Note: In actual implementation, you'd add this to the session
    # But in event listeners, we use connection.execute or similar

@event.listens_for(Ethos, 'after_update')
def log_ethos_update(mapper, connection, target):
    """Log when an ethos is modified."""
    if target.last_updated_by_agent:
        target.last_updated_by_agent = False  # Reset for next time