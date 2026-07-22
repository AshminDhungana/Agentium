from sqlalchemy import Column, String, Integer, JSON, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime

from .base import BaseEntity


class SpeakerProfile(BaseEntity):
    """
    Voice fingerprint profile for speaker identification.
    Stores the extracted voice embedding vector (e.g. ECAPA-TDNN) for comparison.
    """
    __tablename__ = 'speaker_profiles'

    # Optional mapping to a known user
    user_id = Column(String(36), ForeignKey('users.id'), nullable=True, index=True)

    # Human readable name or alias
    name = Column(String(100), nullable=False)

    # Store the 1D float array as JSONB / JSON
    embedding = Column(JSON, nullable=False)

    # Track how many enrollment samples were aggregated
    sample_count = Column(Integer, default=1, nullable=False)

    # Time of first enrollment
    enrolled_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Soft-delete flag — queried by every enroll/identify/list/delete path
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)

    user = relationship("User", backref="speaker_profiles")

    def soft_delete(self):
        """Mark the profile as deleted without removing the row."""
        self.is_deleted = True

    def to_dict(self):
        base = super().to_dict()
        base.update({
            'user_id': self.user_id,
            'name': self.name,
            'sample_count': self.sample_count,
            'enrolled_at': self.enrolled_at.isoformat() if self.enrolled_at else None,
            'is_deleted': self.is_deleted,
            # Let's not serve the full embedding vector in the API unless needed, to save bandwidth
            'has_embedding': True if self.embedding else False
        })
        return base
