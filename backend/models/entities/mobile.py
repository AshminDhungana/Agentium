"""
Phase 11.4 — Mobile API Models
==============================
Models for tracking mobile device tokens for push notifications.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import relationship

from .base import Base

def _new_uuid() -> str:
    return str(uuid.uuid4())


class DeviceToken(Base):
    """A registered mobile device token for push notifications."""
    __tablename__ = "device_tokens"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # "ios" or "android"
    platform = Column(String(20), nullable=False)
    # FCM or APNs token
    token = Column(String(255), nullable=False, unique=True, index=True)
    
    is_active = Column(Boolean, default=True, nullable=False)
    
    registered_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_used_at = Column(DateTime(timezone=True), nullable=True)

    # Relationships
    user = relationship("User")


class NotificationPreference(Base):
    """Per-user notification preferences for mobile push notifications."""
    __tablename__ = "notification_preferences"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    user_id = Column(
        String(36),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Granular toggles
    votes_enabled = Column(Boolean, default=True, nullable=False)
    alerts_enabled = Column(Boolean, default=True, nullable=False)
    tasks_enabled = Column(Boolean, default=True, nullable=False)
    constitutional_enabled = Column(Boolean, default=True, nullable=False)

    # Quiet hours (e.g. "22:00" – "07:00")
    quiet_hours_start = Column(String(5), nullable=True)  # HH:MM
    quiet_hours_end = Column(String(5), nullable=True)    # HH:MM

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User")
