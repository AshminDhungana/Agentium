"""
Phase 12.2 — Webhook Dispatch Service
======================================
Fires outbound webhook events to all matching subscriptions with:
  - HMAC-SHA256 signing
  - Exponential backoff retry (5 attempts)
  - Fire-and-forget background delivery
"""

import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import httpx
from sqlalchemy.orm import Session

from backend.models.entities.webhook import WebhookSubscription, WebhookDeliveryLog

logger = logging.getLogger(__name__)

# Retry delays in seconds: 10s, 30s, 90s, 270s, 810s
RETRY_DELAYS = [10, 30, 90, 270, 810]
MAX_ATTEMPTS = 5

# All supported event types
SUPPORTED_EVENTS = {
    "task.created",
    "task.completed",
    "task.failed",
    "vote.started",
    "vote.resolved",
    "constitution.amended",
    "agent.spawned",
    "agent.terminated",
}


class WebhookDispatchService:
    """Dispatch outbound webhook events to registered subscriptions."""

    @staticmethod
    def sign_payload(secret: str, payload_bytes: bytes) -> str:
        """Generate HMAC-SHA256 signature for a payload."""
        return hmac.new(
            secret.encode("utf-8"),
            payload_bytes,
            hashlib.sha256,
        ).hexdigest()

    @staticmethod
    async def dispatch_event(
        event_type: str,
        payload: Dict[str, Any],
        db: Session,
    ) -> int:
        """
        Fan out an event to all matching active subscriptions.

        Returns the number of deliveries queued.
        """
        if event_type not in SUPPORTED_EVENTS:
            logger.warning("Unknown webhook event type: %s", event_type)
            return 0

        subscriptions: List[WebhookSubscription] = (
            db.query(WebhookSubscription)
            .filter(
                WebhookSubscription.is_active == True,
            )
            .all()
        )

        # Filter to subscriptions that include this event type
        matching = [
            sub for sub in subscriptions
            if event_type in (sub.events or [])
        ]

        if not matching:
            return 0

        count = 0
        for sub in matching:
            delivery = WebhookDeliveryLog(
                subscription_id=sub.id,
                delivery_id=str(uuid.uuid4()),
                event_type=event_type,
                payload=payload,
            )
            db.add(delivery)
            db.flush()  # get the delivery_id assigned

            # Attempt immediate delivery
            try:
                await WebhookDispatchService._deliver(sub, delivery, db)
            except Exception as exc:
                logger.error(
                    "Webhook delivery failed for sub=%s event=%s: %s",
                    sub.id, event_type, exc,
                )
                # Schedule retry
                delivery.error = str(exc)
                delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=RETRY_DELAYS[0])

            count += 1

        db.commit()
        return count

    @staticmethod
    async def _deliver(
        subscription: WebhookSubscription,
        delivery: WebhookDeliveryLog,
        db: Session,
    ) -> bool:
        """
        Attempt to deliver a webhook event.

        Returns True if delivery succeeded (2xx response).
        """
        payload_bytes = json.dumps(delivery.payload, default=str).encode("utf-8")
        signature = WebhookDispatchService.sign_payload(subscription.secret, payload_bytes)

        headers = {
            "Content-Type": "application/json",
            "X-Agentium-Event": delivery.event_type,
            "X-Agentium-Delivery-ID": delivery.delivery_id,
            "X-Agentium-Signature": f"sha256={signature}",
            "User-Agent": "Agentium-Webhooks/1.0",
        }

        delivery.attempts += 1

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    subscription.url,
                    content=payload_bytes,
                    headers=headers,
                )

            delivery.status_code = response.status_code
            delivery.response_body = response.text[:2000] if response.text else None

            if 200 <= response.status_code < 300:
                delivery.delivered_at = datetime.utcnow()
                delivery.next_retry_at = None
                delivery.error = None
                logger.info(
                    "✅ Webhook delivered: sub=%s event=%s status=%d",
                    subscription.id, delivery.event_type, response.status_code,
                )
                return True
            else:
                delivery.error = f"HTTP {response.status_code}"
                logger.warning(
                    "⚠️ Webhook delivery got non-2xx: sub=%s status=%d",
                    subscription.id, response.status_code,
                )

        except httpx.TimeoutException:
            delivery.error = "Request timed out"
            logger.warning("⚠️ Webhook timeout: sub=%s", subscription.id)
        except httpx.RequestError as exc:
            delivery.error = f"Connection error: {exc}"
            logger.warning("⚠️ Webhook connection error: sub=%s: %s", subscription.id, exc)

        # Schedule retry if attempts remain
        if delivery.attempts < MAX_ATTEMPTS:
            delay = RETRY_DELAYS[min(delivery.attempts - 1, len(RETRY_DELAYS) - 1)]
            delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
            logger.info(
                "🔄 Scheduling retry %d/%d for delivery %s in %ds",
                delivery.attempts + 1, MAX_ATTEMPTS, delivery.delivery_id, delay,
            )
        else:
            delivery.failed_at = datetime.utcnow()
            delivery.next_retry_at = None
            logger.error(
                "❌ Webhook delivery exhausted: sub=%s event=%s after %d attempts",
                subscription.id, delivery.event_type, delivery.attempts,
            )

        return False

    @staticmethod
    async def retry_pending_deliveries(db: Session) -> int:
        """
        Retry all deliveries that have a next_retry_at in the past.

        This should be called periodically (e.g., every 30 seconds via Celery).
        Returns the number of retries attempted.
        """
        now = datetime.utcnow()
        pending = (
            db.query(WebhookDeliveryLog)
            .filter(
                WebhookDeliveryLog.next_retry_at != None,
                WebhookDeliveryLog.next_retry_at <= now,
                WebhookDeliveryLog.delivered_at == None,
                WebhookDeliveryLog.failed_at == None,
            )
            .all()
        )

        retried = 0
        for delivery in pending:
            subscription = (
                db.query(WebhookSubscription)
                .filter(WebhookSubscription.id == delivery.subscription_id)
                .first()
            )
            if not subscription or not subscription.is_active:
                delivery.failed_at = now
                delivery.next_retry_at = None
                delivery.error = "Subscription deactivated"
                continue

            try:
                await WebhookDispatchService._deliver(subscription, delivery, db)
            except Exception as exc:
                logger.error("Retry failed for delivery %s: %s", delivery.delivery_id, exc)

            retried += 1

        db.commit()
        return retried


# Module-level convenience function
async def dispatch_webhook_event(
    event_type: str,
    payload: Dict[str, Any],
    db: Session,
) -> int:
    """Convenience wrapper for WebhookDispatchService.dispatch_event."""
    return await WebhookDispatchService.dispatch_event(event_type, payload, db)
