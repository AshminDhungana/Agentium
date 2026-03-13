"""
Phase 12.2 — Outbound Webhook Management API
=============================================
CRUD endpoints for managing outbound event webhook subscriptions.
"""

import secrets
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.webhook import WebhookSubscription, WebhookDeliveryLog
from backend.core.auth import get_current_user
from backend.services.webhook_dispatch_service import WebhookDispatchService

router = APIRouter(prefix="/webhooks", tags=["Outbound Webhooks"])


# ═══════════════════════════════════════════════════════════
# Pydantic Schemas
# ═══════════════════════════════════════════════════════════

class CreateWebhookRequest(BaseModel):
    url: str = Field(..., min_length=10, max_length=500, description="Webhook endpoint URL")
    events: List[str] = Field(..., min_length=1, description="Event types to subscribe to")
    secret: Optional[str] = Field(None, description="HMAC secret (auto-generated if omitted)")
    description: Optional[str] = Field(None, max_length=500)


class UpdateWebhookRequest(BaseModel):
    url: Optional[str] = Field(None, max_length=500)
    events: Optional[List[str]] = None
    description: Optional[str] = Field(None, max_length=500)
    is_active: Optional[bool] = None


class WebhookResponse(BaseModel):
    id: str
    url: str
    events: List[str]
    description: Optional[str]
    is_active: bool
    created_at: Optional[str]
    updated_at: Optional[str]


class WebhookWithSecretResponse(WebhookResponse):
    secret: str


# ═══════════════════════════════════════════════════════════
# CRUD Endpoints
# ═══════════════════════════════════════════════════════════

@router.post("/subscriptions", response_model=WebhookWithSecretResponse)
async def create_subscription(
    request: CreateWebhookRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Create a new outbound webhook subscription.

    If no secret is provided, one is auto-generated.
    The secret is only shown in the creation response.
    """
    from backend.services.webhook_dispatch_service import SUPPORTED_EVENTS

    # Validate event types
    invalid = set(request.events) - SUPPORTED_EVENTS
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid event types: {', '.join(invalid)}. "
                   f"Supported: {', '.join(sorted(SUPPORTED_EVENTS))}",
        )

    secret = request.secret or secrets.token_hex(32)

    subscription = WebhookSubscription(
        id=str(uuid.uuid4()),
        user_id=current_user.get("user_id"),
        url=request.url,
        secret=secret,
        events=request.events,
        description=request.description,
    )

    db.add(subscription)
    db.commit()
    db.refresh(subscription)

    result = subscription.to_dict()
    result["secret"] = secret  # Only shown on creation
    return result


@router.get("/subscriptions")
async def list_subscriptions(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """List all webhook subscriptions for the authenticated user."""
    user_id = current_user.get("user_id")
    subscriptions = (
        db.query(WebhookSubscription)
        .filter(WebhookSubscription.user_id == user_id)
        .order_by(WebhookSubscription.created_at.desc())
        .all()
    )
    return {"subscriptions": [s.to_dict() for s in subscriptions]}


@router.get("/subscriptions/{subscription_id}")
async def get_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get a specific webhook subscription."""
    sub = _get_user_subscription(subscription_id, current_user, db)
    return sub.to_dict()


@router.put("/subscriptions/{subscription_id}")
async def update_subscription(
    subscription_id: str,
    request: UpdateWebhookRequest,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Update a webhook subscription."""
    from backend.services.webhook_dispatch_service import SUPPORTED_EVENTS

    sub = _get_user_subscription(subscription_id, current_user, db)

    if request.events is not None:
        invalid = set(request.events) - SUPPORTED_EVENTS
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid event types: {', '.join(invalid)}",
            )
        sub.events = request.events

    if request.url is not None:
        sub.url = request.url
    if request.description is not None:
        sub.description = request.description
    if request.is_active is not None:
        sub.is_active = request.is_active

    db.commit()
    db.refresh(sub)
    return sub.to_dict()


@router.delete("/subscriptions/{subscription_id}")
async def delete_subscription(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Delete a webhook subscription and all its delivery logs."""
    sub = _get_user_subscription(subscription_id, current_user, db)
    db.delete(sub)
    db.commit()
    return {"status": "deleted", "subscription_id": subscription_id}


# ═══════════════════════════════════════════════════════════
# Delivery Logs
# ═══════════════════════════════════════════════════════════

@router.get("/subscriptions/{subscription_id}/deliveries")
async def get_deliveries(
    subscription_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """Get delivery log for a webhook subscription."""
    _get_user_subscription(subscription_id, current_user, db)

    deliveries = (
        db.query(WebhookDeliveryLog)
        .filter(WebhookDeliveryLog.subscription_id == subscription_id)
        .order_by(WebhookDeliveryLog.created_at.desc())
        .limit(limit)
        .all()
    )
    return {"deliveries": [d.to_dict() for d in deliveries]}


# ═══════════════════════════════════════════════════════════
# Test Webhook
# ═══════════════════════════════════════════════════════════

@router.post("/subscriptions/{subscription_id}/test")
async def test_webhook(
    subscription_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """
    Send a test event to a webhook subscription.

    Sends a `test.ping` event with a sample payload.
    """
    sub = _get_user_subscription(subscription_id, current_user, db)

    test_payload = {
        "event": "test.ping",
        "message": "This is a test webhook delivery from Agentium.",
        "subscription_id": sub.id,
        "timestamp": __import__("datetime").datetime.utcnow().isoformat(),
    }

    delivery = WebhookDeliveryLog(
        subscription_id=sub.id,
        delivery_id=str(uuid.uuid4()),
        event_type="test.ping",
        payload=test_payload,
    )
    db.add(delivery)
    db.flush()

    success = await WebhookDispatchService._deliver(sub, delivery, db)
    db.commit()

    return {
        "status": "delivered" if success else "failed",
        "delivery_id": delivery.delivery_id,
        "status_code": delivery.status_code,
        "error": delivery.error,
    }


# ═══════════════════════════════════════════════════════════
# Supported Events
# ═══════════════════════════════════════════════════════════

@router.get("/events")
async def list_supported_events(
    current_user: dict = Depends(get_current_user),
):
    """List all supported webhook event types."""
    from backend.services.webhook_dispatch_service import SUPPORTED_EVENTS
    return {"events": sorted(SUPPORTED_EVENTS)}


# ═══════════════════════════════════════════════════════════
# Internal Helpers
# ═══════════════════════════════════════════════════════════

def _get_user_subscription(
    subscription_id: str,
    current_user: dict,
    db: Session,
) -> WebhookSubscription:
    """Get a subscription owned by the current user, or raise 404."""
    sub = (
        db.query(WebhookSubscription)
        .filter(
            WebhookSubscription.id == subscription_id,
            WebhookSubscription.user_id == current_user.get("user_id"),
        )
        .first()
    )
    if not sub:
        raise HTTPException(status_code=404, detail="Webhook subscription not found")
    return sub
