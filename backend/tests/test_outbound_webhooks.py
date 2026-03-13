"""
Tests for Phase 12 — Outbound Webhook System.
"""
import pytest
import hmac
import hashlib
import json
from datetime import datetime
from unittest.mock import patch, MagicMock, AsyncMock

from backend.models.entities.webhook import WebhookSubscription, WebhookDeliveryLog
from backend.services.webhook_dispatch_service import WebhookDispatchService, SUPPORTED_EVENTS


class MockDB:
    """Minimal mock for SQLAlchemy Session."""
    def __init__(self):
        self._store = []

    def add(self, entity):
        self._store.append(entity)

    def flush(self):
        pass

    def commit(self):
        pass

    def refresh(self, entity):
        pass

    def delete(self, entity):
        self._store = [e for e in self._store if e is not entity]

    def query(self, model):
        mock = MagicMock()
        results = [e for e in self._store if isinstance(e, model)]

        def filter_fn(*args, **kwargs):
            return mock
        mock.filter = filter_fn
        mock.all = MagicMock(return_value=results)
        mock.first = MagicMock(return_value=results[0] if results else None)
        mock.order_by = MagicMock(return_value=mock)
        mock.limit = MagicMock(return_value=mock)
        return mock


# ═══════════════════════════════════════════════════════════
# HMAC Signing
# ═══════════════════════════════════════════════════════════

def test_sign_payload():
    """Verify HMAC-SHA256 signature generation."""
    secret = "test-secret"
    payload = b'{"event": "task.created"}'

    signature = WebhookDispatchService.sign_payload(secret, payload)

    expected = hmac.new(
        secret.encode("utf-8"),
        payload,
        hashlib.sha256,
    ).hexdigest()

    assert signature == expected
    assert len(signature) == 64  # SHA256 hex = 64 chars


def test_sign_payload_different_secrets():
    """Different secrets produce different signatures."""
    payload = b'{"test": true}'
    sig1 = WebhookDispatchService.sign_payload("secret-1", payload)
    sig2 = WebhookDispatchService.sign_payload("secret-2", payload)
    assert sig1 != sig2


# ═══════════════════════════════════════════════════════════
# Subscription Entity
# ═══════════════════════════════════════════════════════════

def test_subscription_to_dict():
    """WebhookSubscription.to_dict() includes all fields."""
    sub = WebhookSubscription(
        id="sub-1",
        user_id="user-1",
        url="https://example.com/hook",
        secret="secret-key",
        events=["task.created", "task.completed"],
        description="My webhook",
        is_active=True,
        created_at=datetime(2026, 1, 1),
        updated_at=datetime(2026, 1, 1),
    )
    d = sub.to_dict()
    assert d["id"] == "sub-1"
    assert d["url"] == "https://example.com/hook"
    assert len(d["events"]) == 2
    assert d["is_active"] is True
    # Secret should NOT be in to_dict
    assert "secret" not in d


def test_delivery_log_to_dict():
    """WebhookDeliveryLog.to_dict() includes all tracking fields."""
    log = WebhookDeliveryLog(
        id="log-1",
        subscription_id="sub-1",
        delivery_id="del-1",
        event_type="task.created",
        payload={"task_id": "t1"},
        status_code=200,
        attempts=1,
        delivered_at=datetime(2026, 1, 1),
        created_at=datetime(2026, 1, 1),
    )
    d = log.to_dict()
    assert d["event_type"] == "task.created"
    assert d["status_code"] == 200
    assert d["attempts"] == 1
    assert d["delivered_at"] is not None


# ═══════════════════════════════════════════════════════════
# Supported Events
# ═══════════════════════════════════════════════════════════

def test_supported_events():
    """All expected event types are defined."""
    expected = {
        "task.created", "task.completed", "task.failed",
        "vote.started", "vote.resolved",
        "constitution.amended",
        "agent.spawned", "agent.terminated",
    }
    assert SUPPORTED_EVENTS == expected


# ═══════════════════════════════════════════════════════════
# Dispatch (mocked HTTP)
# ═══════════════════════════════════════════════════════════

@pytest.mark.asyncio
async def test_dispatch_unknown_event():
    """dispatch_event returns 0 for unknown event types."""
    db = MockDB()
    count = await WebhookDispatchService.dispatch_event("unknown.event", {}, db)
    assert count == 0


@pytest.mark.asyncio
async def test_dispatch_no_matching_subscriptions():
    """dispatch_event returns 0 when no subscriptions match."""
    db = MockDB()
    # Add a subscription for a different event
    sub = WebhookSubscription(
        id="sub-1", user_id="u1", url="http://example.com",
        secret="secret", events=["vote.started"], is_active=True,
    )
    db.add(sub)
    count = await WebhookDispatchService.dispatch_event("task.created", {"id": "t1"}, db)
    assert count == 0


@pytest.mark.asyncio
async def test_dispatch_creates_delivery_log():
    """dispatch_event creates a WebhookDeliveryLog for matching subscriptions."""
    db = MockDB()
    sub = WebhookSubscription(
        id="sub-1", user_id="u1", url="http://example.com/hook",
        secret="test-secret", events=["task.created"], is_active=True,
    )
    db.add(sub)

    # Mock the _deliver method to avoid real HTTP calls
    with patch.object(WebhookDispatchService, '_deliver', new_callable=AsyncMock, return_value=True):
        count = await WebhookDispatchService.dispatch_event(
            "task.created",
            {"task_id": "t1", "title": "Test"},
            db,
        )

    assert count == 1
    deliveries = [e for e in db._store if isinstance(e, WebhookDeliveryLog)]
    assert len(deliveries) == 1
    assert deliveries[0].event_type == "task.created"
