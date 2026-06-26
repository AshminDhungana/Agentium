"""
Base entity model for all Agentium database models.
Provides common functionality like timestamps, UUIDs, and serialization.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from sqlalchemy import Column, String, DateTime, event, Boolean
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.orm import declarative_base
import uuid

Base = declarative_base()

class BaseEntity(Base):
    """Abstract base class for all Agentium entities."""
    
    __abstract__ = True
    
    # Primary identification
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Identification number based on entity type (0xxxx, 1xxxx, 2xxxx, 3xxxx)
    agentium_id = Column(String(20), unique=True, nullable=False, index=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    # Soft delete for audit trail preservation
    deleted_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    
    @declared_attr.directive
    def __tablename__(cls) -> str:
        """Generate table name from class name."""
        return cls.__name__.lower() + 's'
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert entity to dictionary for API responses."""
        return {
            'id': self.id,
            'agentium_id': self.agentium_id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'is_active': self.is_active
        }
    
    def deactivate(self):
        """Soft delete the entity."""
        self.is_active = False
        self.deleted_at = datetime.utcnow()
    
    def reactivate(self):
        """Reactivate a soft-deleted entity."""
        self.is_active = True
        self.deleted_at = None
        self.updated_at = datetime.utcnow()
    
    def __repr__(self):
        return f"<{self.__class__.__name__}(agentium_id={self.agentium_id})>"


@event.listens_for(BaseEntity, 'before_update', propagate=True)
def receive_before_update(mapper, connection, target):
    """Automatically update the updated_at timestamp."""
    target.updated_at = datetime.utcnow()