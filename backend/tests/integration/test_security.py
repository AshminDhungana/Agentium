"""
Security Suite (Phase 18.1)
===========================
Integration tests for core security controls:

  1. Expired JWT    → 401
  2. Observer role  → 403 on mutation (POST /tasks)
  3. Rate limit     → 429 after threshold
  4. HMAC tamper    → 400 (reject tampered webhook payload)
  5. XSS injection  → sanitized before storage
"""

import pytest
import hmac
import hashlib
import json
import time
import uuid
from datetime import timedelta, timezone
from fastapi.testclient import TestClient
from fastapi import FastAPI

import fakeredis.aioredis

from backend.core.auth import create_access_token
from backend.core.middleware import RateLimitMiddleware
from backend.core import middleware as rate_limit_module
from backend.models.entities.user import User, ROLE_OBSERVER
from backend.models.entities.event_trigger import EventTrigger, TriggerType
from backend.models.database import get_db_context

pytestmark = pytest.mark.integration


# ── Helpers ───────────────────────────────────────────────────────────

def _make_observer_user() -> User:
    """Create and commit an observer-role user directly to the DB."""
    with get_db_context() as db:
        user = User.create_user(
            db=db,
            username=f"observer_{uuid.uuid4().hex[:8]}",
            email=f"observer_{uuid.uuid4().hex[:8]}@test.local",
            password="observerpassword",
            is_active=True,
            is_pending=False,
            role=ROLE_OBSERVER,
        )
        # Refresh to get the generated id
        db.refresh(user)
        return user


# ── Group 1 — JWT Security ───────────────────────────────────────────

class TestJWTSecurity:
    """Expired and malformed token handling."""

    def test_expired_jwt_returns_401(self, client):
        """A token with a past expiry date must be rejected with 401."""
        expired_token = create_access_token(
            data={"sub": "admin", "user_id": "test-user-id"},
            expires_delta=timedelta(minutes=-1)
        )
        response = client.get(
            "/api/v1/auth/verify-session",
            headers={"Authorization": f"Bearer {expired_token}"}
        )
        assert response.status_code == 401
        assert "unauthorized" in response.text.lower() or "invalid" in response.text.lower()


# ── Group 2 — Role-Based Access (Observer) ─────────────────────────────

class TestObserverRole:
    """Observer read-only enforcement via ObserverReadOnlyMiddleware."""

    def test_observer_cannot_create_task(self, client):
        """Observer POSTing to /tasks should receive 403."""
        observer = _make_observer_user()

        token = create_access_token(
            data={"sub": observer.username, "user_id": observer.id, "role": observer.role}
        )
        headers = {"Authorization": f"Bearer {token}"}

        payload = {
            "title": "Observer task test",
            "description": "This should be blocked"
        }

        response = client.post("/api/v1/tasks", json=payload, headers=headers)
        assert response.status_code == 403
        assert "read-only" in response.json()["detail"].lower()

    def test_observer_cannot_mutate_existing_resource(self, client):
        """Observer DELETE on any protected endpoint should be blocked."""
        observer = _make_observer_user()

        token = create_access_token(
            data={"sub": observer.username, "user_id": observer.id, "role": observer.role}
        )
        headers = {"Authorization": f"Bearer {token}"}

        # Any state-changing method to any protected route should be blocked
        response = client.delete("/api/v1/tasks/00000000-0000-0000-0000-000000000000", headers=headers)
        assert response.status_code == 403
        assert "read-only" in response.json()["detail"].lower()

    def test_observer_can_read(self, client):
        """Observer GET requests should succeed (not blocked by middleware)."""
        observer = _make_observer_user()

        token = create_access_token(
            data={"sub": observer.username, "user_id": observer.id, "role": observer.role}
        )
        headers = {"Authorization": f"Bearer {token}"}

        response = client.get("/api/v1/tasks", headers=headers)
        # Should not be 403; could be 200 or 404 depending on data, but never 403
        assert response.status_code != 403


# ── Group 3 — Rate Limiting ────────────────────────────────────────────

class TestRateLimiting:
    """Per-IP rate limit enforcement via RateLimitMiddleware.

    Phase 17.1 consolidated rate limiting into backend.core.middleware.
    RateLimitMiddleware no longer accepts a `max_requests` kwarg — limits
    are fixed per RateLimitTier (AUTH / TASK / GENERAL) in `_RULES`, and
    enforcement runs against Redis (sliding-window sorted sets via a Lua
    script, with a native-pipeline fallback if scripting is unavailable).

    We use fakeredis (with the [lua] extra) as a real-enough Redis stand-in
    so the test exercises the actual evalsha path rather than a hand-rolled
    approximation of it, and monkeypatch the GENERAL tier's limit down so
    the test stays fast and deterministic.
    """

    def test_rate_limit_returns_429_after_threshold(self, monkeypatch):
        # Shrink the GENERAL tier limit (the route below isn't under
        # /api/v1/auth or /api/v1/tasks, so it maps to GENERAL).
        monkeypatch.setitem(
            rate_limit_module._RULES,
            rate_limit_module.RateLimitTier.GENERAL,
            rate_limit_module.RateLimitRule(requests=2, window=60, key_suffix="general"),
        )
        # Disable the CI/TESTING env bypass so we actually exercise the limiter
        monkeypatch.setattr(rate_limit_module, "_skip_rate_limit", lambda: False)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=fakeredis.aioredis.FakeRedis())

        @app.get("/test")
        def read():
            return {"status": "ok"}

        test_client = TestClient(app)

        # Consume the allowed requests
        test_client.get("/test")
        test_client.get("/test")

        # Third request should be rate-limited
        response = test_client.get("/test")
        assert response.status_code == 429
        assert "Rate limit exceeded" in response.json()["detail"]

    def test_rate_limit_resets_after_window(self, monkeypatch):
        """Once the sliding window has elapsed, requests are allowed again."""
        monkeypatch.setitem(
            rate_limit_module._RULES,
            rate_limit_module.RateLimitTier.GENERAL,
            rate_limit_module.RateLimitRule(requests=1, window=1, key_suffix="general"),
        )
        # Disable the CI/TESTING env bypass so we actually exercise the limiter
        monkeypatch.setattr(rate_limit_module, "_skip_rate_limit", lambda: False)

        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=fakeredis.aioredis.FakeRedis())

        @app.get("/test")
        def read():
            return {"status": "ok"}

        test_client = TestClient(app)

        assert test_client.get("/test").status_code == 200
        assert test_client.get("/test").status_code == 429

        time.sleep(1.1)
        assert test_client.get("/test").status_code == 200

    def test_rate_limit_fails_open_when_redis_unavailable(self):
        """If Redis is None, the middleware must allow traffic through (fail open)."""
        app = FastAPI()
        app.add_middleware(RateLimitMiddleware, redis=None)

        @app.get("/test")
        def read():
            return {"status": "ok"}

        test_client = TestClient(app)
        for _ in range(10):
            assert test_client.get("/test").status_code == 200


# ── Group 4 — Webhook HMAC Integrity ───────────────────────────────────

class TestWebhookHMAC:
    """HMAC-SHA256 validation on the public webhook receiver."""

    def test_hmac_rejects_tampered_payload(self, client, seeded_db):
        """Webhook with mismatched signature should be rejected with 400."""
        secret = "test_webhook_secret"

        # Create a trigger with an HMAC secret
        trigger = EventTrigger(
            name="Test Webhook",
            trigger_type=TriggerType.WEBHOOK,
            config={"hmac_secret": secret},
            is_active=True,
        )
        seeded_db.add(trigger)
        seeded_db.flush()
        seeded_db.refresh(trigger)

        # Original payload bytes
        original_body = b'{"event":"test","data":"original"}'
        # Compute valid signature for ORIGINAL payload
        valid_sig = "sha256=" + hmac.new(secret.encode(), original_body, hashlib.sha256).hexdigest()

        # Tamper the payload but keep the original signature
        tampered_body = b'{"event":"test","data":"tampered"}'

        response = client.post(
            f"/api/v1/events/webhook/{trigger.id}",
            data=tampered_body,
            headers={"Content-Type": "application/json", "X-Agentium-Signature": valid_sig}
        )

        assert response.status_code == 400
        assert "Invalid HMAC" in response.json().get("detail", "")

    def test_hmac_accepts_valid_payload(self, client, seeded_db):
        """A correctly signed payload should be accepted (200)."""
        secret = "another_secret"
        trigger = EventTrigger(
            name="Valid Webhook",
            trigger_type=TriggerType.WEBHOOK,
            config={"hmac_secret": secret},
            is_active=True,
        )
        seeded_db.add(trigger)
        seeded_db.flush()
        seeded_db.refresh(trigger)

        body = b'{"event":"test","data":"valid"}'
        sig = "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        response = client.post(
            f"/api/v1/events/webhook/{trigger.id}",
            data=body,
            headers={"Content-Type": "application/json", "X-Agentium-Signature": sig}
        )

        assert response.status_code == 200
        assert response.json()["status"] == "accepted"

    def test_hmac_rejects_missing_signature_when_secret_configured(self, client, seeded_db):
        """Trigger with a secret but no signature header should be rejected."""
        trigger = EventTrigger(
            name="Secret Webhook",
            trigger_type=TriggerType.WEBHOOK,
            config={"hmac_secret": "secret123"},
            is_active=True,
        )
        seeded_db.add(trigger)
        seeded_db.flush()
        seeded_db.refresh(trigger)

        body = b'{"event":"test"}'
        response = client.post(
            f"/api/v1/events/webhook/{trigger.id}",
            data=body,
            headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 400
        assert "Invalid HMAC" in response.json().get("detail", "")


# ── Group 5 — Input Sanitization (XSS) ────────────────────────────────

class TestXSSSanitization:
    """Dangerous patterns are stripped by InputSanitizationMiddleware."""

    def test_task_description_xss_stripped(self, client, auth_headers, seeded_db):
        """<script> tags in task description are removed before storage."""
        raw_description = "Normal text <script>alert('xss')</script> more text"

        payload = {
            "title": "XSS Test Task",
            "description": raw_description,
            "priority": "normal",
            "task_type": "execution"
        }

        response = client.post("/api/v1/tasks/", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert "<script" not in data["description"]
        assert "alert(" not in data["description"]
        # The script block should be completely stripped
        assert "more text" in data["description"]

    def test_javascript_protocol_stripped(self, client, auth_headers, seeded_db):
        """javascript: URIs are removed from JSON bodies."""
        payload = {
            "title": "JS Protocol Test",
            "description": "Click here: javascript:alert('xss')",
            "priority": "normal",
            "task_type": "execution"
        }

        response = client.post("/api/v1/tasks/", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        # The middleware strips 'javascript:' entirely
        assert "javascript:" not in data["description"].lower()

    def test_on_event_handlers_stripped(self, client, auth_headers, seeded_db):
        """onerror=, onclick=, etc., are removed from JSON bodies."""
        payload = {
            "title": "Event Handler Test",
            "description": "<img onerror=alert('xss') src='test.jpg'>",
            "priority": "normal",
            "task_type": "execution"
        }

        response = client.post("/api/v1/tasks/", json=payload, headers=auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert "onerror=" not in data["description"].lower()
        # The event handler prefix is stripped; remaining text may contain 'alert(' but is harmless