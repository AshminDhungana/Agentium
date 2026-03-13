"""
Phase 12.2 — Outbound Webhook Models
=====================================
Entities for managing outbound event webhook subscriptions and delivery logs.
"""
import uuid
from datetime import datetime

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey, JSON, Integer, Text, func
from backend.models.entities.base import Base


def _new_uuid() -> str:
    return str(uuid.uuid4())


class WebhookSubscription(Base):
    """
    An outbound webhook subscription.

    Users register a URL and a set of event types they want to receive.
    Each matching event is delivered with an HMAC-SHA256 signature.
    """
    __tablename__ = "webhook_subscriptions"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    url = Column(String(500), nullable=False)
    secret = Column(String(255), nullable=False)  # HMAC signing secret
    description = Column(String(500), nullable=True)

    # JSON list of event types, e.g. ["task.created", "vote.started"]
    events = Column(JSON, nullable=False, default=list)

    is_active = Column(Boolean, nullable=False, default=True, server_default="true")

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "url": self.url,
            "description": self.description,
            "events": self.events or [],
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


class WebhookDeliveryLog(Base):
    """
    Tracks each delivery attempt for outbound webhooks.

    Failed deliveries are retried with exponential backoff up to 5 attempts.
    """
    __tablename__ = "webhook_delivery_logs"

    id = Column(String(36), primary_key=True, default=_new_uuid, index=True)
    subscription_id = Column(
        String(36),
        ForeignKey("webhook_subscriptions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Delivery ID sent in X-Agentium-Delivery-ID header
    delivery_id = Column(String(36), nullable=False, unique=True, default=_new_uuid)

    event_type = Column(String(50), nullable=False, index=True)
    payload = Column(JSON, nullable=False)

    # HTTP response status from the recipient
    status_code = Column(Integer, nullable=True)
    response_body = Column(Text, nullable=True)

    attempts = Column(Integer, nullable=False, default=0)
    max_attempts = Column(Integer, nullable=False, default=5)

    # null = pending, set after final attempt
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    next_retry_at = Column(DateTime(timezone=True), nullable=True)
    failed_at = Column(DateTime(timezone=True), nullable=True)

    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "subscription_id": self.subscription_id,
            "delivery_id": self.delivery_id,
            "event_type": self.event_type,
            "payload": self.payload,
            "status_code": self.status_code,
            "attempts": self.attempts,
            "max_attempts": self.max_attempts,
            "delivered_at": self.delivered_at.isoformat() if self.delivered_at else None,
            "next_retry_at": self.next_retry_at.isoformat() if self.next_retry_at else None,
            "failed_at": self.failed_at.isoformat() if self.failed_at else None,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
