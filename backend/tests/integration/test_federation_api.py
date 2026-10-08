"""
Integration tests for the Federation API (TODO Section 16.1).

Covers:
  16.1.1 - POST /api/v1/federation/peers registers a peer instance
  16.1.2 - GET  /api/v1/federation/peers lists connected peers
  16.1.3 - Peer heartbeat (webhook probe + Celery task on 5-min interval)
  16.1.4 - Stale peer cleanup (FederationService + Celery task on hourly beat)

Plus peer management (DELETE / PATCH trust), dual-mode webhook auth
(HMAC-SHA256 + legacy secret), and the task delegation webhooks
(/webhooks/tasks/receive and /webhooks/tasks/result).
"""

import hashlib
import hmac
import json
import time
import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy.orm import sessionmaker

import backend.celery_app as celery_module
from backend.celery_app import federation_cleanup_stale, federation_heartbeat
from backend.core.config import settings
from backend.models.entities.federation import FederatedInstance, FederatedTask
from backend.models.entities.task import Task, TaskStatus
from backend.services.federation_service import FederationService

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"
PEER_URL = "http://peer-alpha.local"


# ==========================================================================
# Helpers
# ==========================================================================

def _derive_signing_key(secret: str) -> str:
    """Mirror FederationService._derive_signing_key (SHA-256(secret + ':sign'))."""
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def _sign(signing_key: str, body: bytes, timestamp: int) -> str:
    """Mirror federation_service._sign_payload — HMAC over f'{ts}:' + body."""
    message = f"{timestamp}:".encode() + body
    return hmac.new(signing_key.encode(), message, hashlib.sha256).hexdigest()


def _hmac_headers(peer_url: str, secret: str, body: bytes, timestamp: int = None):
    """Headers an authenticated peer would send with `body`."""
    if timestamp is None:
        timestamp = int(time.time())
    sig = _sign(_derive_signing_key(secret), body, timestamp)
    return {
        "Content-Type": "application/json",
        "X-Agentium-Peer-Url": peer_url,
        "X-Agentium-Timestamp": str(timestamp),
        "X-Agentium-Signature": f"sha256={sig}",
    }


def _make_peer(
    db,
    name: str,
    base_url: str,
    secret: str = SECRET,
    status: str = "active",
    trust_level: str = "limited",
    last_heartbeat_at: datetime = None,
) -> FederatedInstance:
    """Insert a FederatedInstance row directly (bypassing the API)."""
    peer = FederatedInstance(
        name=name,
        base_url=base_url.rstrip("/"),
        shared_secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        signing_key=_derive_signing_key(secret),
        status=status,
        trust_level=trust_level,
        capabilities_shared=["tasks"],
        last_heartbeat_at=last_heartbeat_at,
    )
    db.add(peer)
    db.flush()
    return peer


def _register_peer_via_api(client, auth_headers, name="Peer Alpha",
                           base_url=PEER_URL, secret=SECRET,
                           trust_level="limited", capabilities=None):
    return client.post(
        "/api/v1/federation/peers",
        headers=auth_headers,
        json={
            "name": name,
            "base_url": base_url,
            "shared_secret": secret,
            "trust_level": trust_level,
            "capabilities": capabilities or ["tasks"],
        },
    )


def _make_user(db, username: str, is_admin: bool):
    from backend.models.entities.user import User
    user = User(
        username=username,
        email=f"{username}@agentium.test",
        hashed_password=User.hash_password("password123"),
        is_admin=is_admin,
        is_active=True,
        is_pending=False,
    )
    db.add(user)
    db.flush()
    return user


def _login(client, username: str):
    resp = client.post(
        "/api/v1/auth/login",
        json={"username": username, "password": "password123"},
    )
    assert resp.status_code == 200, f"login failed for {username}: {resp.text}"
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


# ==========================================================================
# Fixtures
# ==========================================================================

@pytest.fixture
def fed_enabled(monkeypatch):
    """Enable federation on this instance for service-level checks."""
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", True)


@pytest.fixture
def beat_session_factory(db_session, monkeypatch):
    """
    Point celery_app.BeatSessionLocal at the test's transactional connection
    so Celery task bodies read/write the same rolled-back transaction.
    """
    test_beat = sessionmaker(bind=db_session.get_bind())
    monkeypatch.setattr(celery_module, "BeatSessionLocal", test_beat)
    return test_beat


@pytest.fixture
def beat_env(monkeypatch, beat_session_factory):
    """Env vars the Celery federation tasks read at runtime."""
    monkeypatch.setenv("FEDERATION_ENABLED", "true")
    monkeypatch.setenv("FEDERATION_INSTANCE_URL", "http://primary.local")
    monkeypatch.setenv("FEDERATION_SHARED_SECRET", "primary-secret")


@pytest.fixture
def peer(seeded_db):
    """One active, limited-trust peer visible to API and webhooks."""
    return _make_peer(seeded_db, "Peer Alpha", PEER_URL)


# ==========================================================================
# 16.1.1 + 16.1.2 — Registration & Listing
# ==========================================================================

class TestPeerRegistration:
    """POST /api/v1/federation/peers registers a peer instance."""

    def test_register_peer_returns_201(self, client, auth_headers, seeded_db, fed_enabled):
        resp = _register_peer_via_api(client, auth_headers, base_url="http://reg-a.local")
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Peer Alpha"
        assert body["base_url"] == "http://reg-a.local"
        assert body["status"] == "active"
        assert body["trust_level"] == "limited"
        assert body["capabilities_shared"] == ["tasks"]

        # Secret is never echoed — only its hash is stored
        row = seeded_db.query(FederatedInstance).filter_by(base_url="http://reg-a.local").one()
        assert row.shared_secret_hash == hashlib.sha256(SECRET.encode()).hexdigest()
        assert row.signing_key == _derive_signing_key(SECRET)

    def test_register_peer_normalizes_trailing_slash(self, client, auth_headers, seeded_db, fed_enabled):
        resp = _register_peer_via_api(client, auth_headers, base_url="http://reg-b.local/")
        assert resp.status_code == 201
        assert resp.json()["base_url"] == "http://reg-b.local"

    def test_duplicate_base_url_rejected(self, client, auth_headers, seeded_db, fed_enabled):
        assert _register_peer_via_api(client, auth_headers, base_url="http://dup.local").status_code == 201
        resp = _register_peer_via_api(client, auth_headers, name="Second", base_url="http://dup.local")
        assert resp.status_code == 400

    def test_registration_requires_admin(self, client, auth_headers, seeded_db, fed_enabled):
        _make_user(seeded_db, "plainuser", is_admin=False)
        plain_headers = _login(client, "plainuser")
        resp = _register_peer_via_api(client, plain_headers, base_url="http://noadmin.local")
        assert resp.status_code == 403

    def test_registration_requires_auth(self, client, fed_enabled):
        resp = client.post(
            "/api/v1/federation/peers",
            json={"name": "X", "base_url": "http://x.local", "shared_secret": "s"},
        )
        assert resp.status_code == 401


class TestPeerListing:
    """GET /api/v1/federation/peers lists connected peers."""

    def test_list_peers_includes_registered_peer(self, client, auth_headers, seeded_db, fed_enabled):
        _register_peer_via_api(client, auth_headers, name="Listed Peer",
                               base_url="http://list-a.local")
        resp = client.get("/api/v1/federation/peers", headers=auth_headers)
        assert resp.status_code == 200
        peers = resp.json()
        matching = [p for p in peers if p["base_url"] == "http://list-a.local"]
        assert len(matching) == 1
        assert matching[0]["name"] == "Listed Peer"
        assert matching[0]["status"] == "active"
        assert "last_heartbeat_at" in matching[0]
        assert "registered_at" in matching[0]

    def test_list_peers_pagination(self, client, auth_headers, seeded_db, fed_enabled):
        for i in range(3):
            _register_peer_via_api(client, auth_headers, name=f"P{i}",
                                   base_url=f"http://page-{i}.local")
        all_peers = client.get("/api/v1/federation/peers", headers=auth_headers).json()
        page = client.get("/api/v1/federation/peers?skip=1&limit=1", headers=auth_headers).json()
        assert len(page) == 1
        # Newest-first ordering means skip=1 returns the second-newest row
        assert page[0]["base_url"] == all_peers[1]["base_url"]

    def test_list_peers_requires_auth(self, client, fed_enabled):
        assert client.get("/api/v1/federation/peers").status_code == 401


class TestPeerManagement:
    """DELETE /peers/{id} and PATCH /peers/{id}/trust."""

    def test_delete_peer(self, client, auth_headers, seeded_db, fed_enabled, peer):
        resp = client.delete(f"/api/v1/federation/peers/{peer.id}", headers=auth_headers)
        assert resp.status_code == 204
        assert seeded_db.query(FederatedInstance).filter_by(id=peer.id).count() == 0

    def test_delete_missing_peer_404(self, client, auth_headers, fed_enabled):
        resp = client.delete(f"/api/v1/federation/peers/{uuid.uuid4()}", headers=auth_headers)
        assert resp.status_code == 404

    def test_delete_requires_admin(self, client, auth_headers, seeded_db, fed_enabled, peer):
        _make_user(seeded_db, "plainuser", is_admin=False)
        plain_headers = _login(client, "plainuser")
        resp = client.delete(f"/api/v1/federation/peers/{peer.id}", headers=plain_headers)
        assert resp.status_code == 403

    def test_update_trust_level(self, client, auth_headers, seeded_db, fed_enabled, peer):
        resp = client.patch(
            f"/api/v1/federation/peers/{peer.id}/trust",
            headers=auth_headers,
            json={"trust_level": "full"},
        )
        assert resp.status_code == 200
        assert resp.json()["trust_level"] == "full"
        seeded_db.refresh(peer)
        assert peer.trust_level == "full"

    def test_update_trust_rejects_invalid_value(self, client, auth_headers, fed_enabled, peer):
        resp = client.patch(
            f"/api/v1/federation/peers/{peer.id}/trust",
            headers=auth_headers,
            json={"trust_level": "bogus"},
        )
        assert resp.status_code == 400


# ==========================================================================
# Webhook authentication (heartbeat probe target)
# ==========================================================================

class TestWebhookAuthentication:
    """Dual-mode peer auth on /webhooks/* endpoints."""

    def test_heartbeat_with_valid_hmac(self, client, seeded_db, fed_enabled, peer):
        body = b"{}"
        resp = client.post(
            "/api/v1/federation/webhooks/heartbeat",
            content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["alive"] is True
        seeded_db.refresh(peer)
        assert peer.last_heartbeat_at is not None

    def test_heartbeat_with_wrong_secret(self, client, fed_enabled, peer):
        body = b"{}"
        resp = client.post(
            "/api/v1/federation/webhooks/heartbeat",
            content=body,
            headers=_hmac_headers(PEER_URL, "wrong-secret", body),
        )
        assert resp.status_code == 401

    def test_heartbeat_rejects_stale_timestamp(self, client, fed_enabled, peer):
        body = b"{}"
        stale_ts = int(time.time()) - 600  # beyond the 300s replay window
        resp = client.post(
            "/api/v1/federation/webhooks/heartbeat",
            content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body, timestamp=stale_ts),
        )
        assert resp.status_code == 401

    def test_heartbeat_with_legacy_secret(self, client, seeded_db, fed_enabled, peer):
        resp = client.post(
            "/api/v1/federation/webhooks/heartbeat",
            content=b"{}",
            headers={
                "Content-Type": "application/json",
                "X-Agentium-Peer-Url": PEER_URL,
                "X-Agentium-Secret": SECRET,
            },
        )
        assert resp.status_code == 200
        seeded_db.refresh(peer)
        assert peer.last_heartbeat_at is not None

    def test_heartbeat_missing_peer_url_header(self, client, fed_enabled, peer):
        resp = client.post("/api/v1/federation/webhooks/heartbeat", content=b"{}")
        assert resp.status_code == 401

    def test_heartbeat_unregistered_peer(self, client, fed_enabled, peer):
        body = b"{}"
        resp = client.post(
            "/api/v1/federation/webhooks/heartbeat",
            content=body,
            headers=_hmac_headers("http://unknown.local", SECRET, body),
        )
        assert resp.status_code == 401

    def test_heartbeat_suspended_peer_forbidden(self, client, seeded_db, fed_enabled):
        peer = _make_peer(seeded_db, "Suspended Peer", "http://susp.local", status="suspended")
        body = b"{}"
        resp = client.post(
            "/api/v1/federation/webhooks/heartbeat",
            content=body,
            headers=_hmac_headers("http://susp.local", SECRET, body),
        )
        assert resp.status_code == 403


# ==========================================================================
# Task delegation webhooks
# ==========================================================================

class TestTaskReceiveWebhook:
    """POST /webhooks/tasks/receive creates a real local Task."""

    def test_receive_delegated_task(self, client, seeded_db, fed_enabled, peer):
        body = json.dumps({
            "original_task_id": "T0001",
            "payload": {
                "title": "Federated job",
                "description": "Do something across instances",
                "callback_url": "http://peer-alpha.local/api/v1/federation/webhooks/tasks/result",
            },
        }).encode()

        resp = client.post(
            "/api/v1/federation/webhooks/tasks/receive",
            content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["accepted"] is True
        assert data["local_task_id"]

        # A real local Task was created for agents to pick up.
        # local_task_id is the Task's UUID PK (FK target: tasks.id), not the
        # human-facing agentium_id ("T00001").
        local_task = seeded_db.query(Task).filter(
            Task.id == data["local_task_id"]
        ).one()
        assert local_task.created_by == "federation"
        assert local_task.status == TaskStatus.PENDING
        assert "Peer Alpha" in local_task.constitutional_basis

        # And the federated shadow record links source -> local
        fed_task = seeded_db.query(FederatedTask).filter(
            FederatedTask.source_instance_id == peer.id
        ).one()
        assert fed_task.status == "accepted"
        assert fed_task.original_task_id == "T0001"
        assert fed_task.local_task_id == data["local_task_id"]
        assert fed_task.local_task_id == str(local_task.id)

    def test_read_only_peer_cannot_delegate_tasks(self, client, seeded_db, fed_enabled):
        _make_peer(seeded_db, "Reader Peer", "http://reader.local", trust_level="read_only")
        body = json.dumps({
            "original_task_id": "T0002",
            "payload": {"title": "Should be rejected"},
        }).encode()
        resp = client.post(
            "/api/v1/federation/webhooks/tasks/receive",
            content=body,
            headers=_hmac_headers("http://reader.local", SECRET, body),
        )
        assert resp.status_code == 403


class TestTaskResultWebhook:
    """POST /webhooks/tasks/result completes an outgoing delegated task."""

    def _seed_outgoing_task(self, db, peer, original_agentium_id="T0042"):
        orig_task = Task(
            agentium_id=original_agentium_id,
            title="Original local task",
            description="Delegated to a peer",
            status=TaskStatus.PENDING,
        )
        db.add(orig_task)
        fed_task = FederatedTask(
            target_instance_id=peer.id,
            original_task_id=original_agentium_id,
            status="delivered",
        )
        db.add(fed_task)
        db.flush()
        return orig_task, fed_task

    def test_receive_task_result(self, client, seeded_db, fed_enabled, peer):
        orig_task, fed_task = self._seed_outgoing_task(seeded_db, peer)

        body = json.dumps({
            "original_task_id": "T0042",
            "local_task_id": "T9999",
            "status": "completed",
            "result_summary": "Peer finished the work",
        }).encode()

        resp = client.post(
            "/api/v1/federation/webhooks/tasks/result",
            content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"acknowledged": True, "fed_task_status": "completed"}

        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"
        assert fed_task.completed_at is not None

        seeded_db.refresh(orig_task)
        assert orig_task.status == TaskStatus.COMPLETED
        assert orig_task.result_summary == "Peer finished the work"

    def test_result_for_unknown_task_404(self, client, fed_enabled, peer):
        body = json.dumps({
            "original_task_id": "T-nope",
            "local_task_id": "T1",
            "status": "completed",
        }).encode()
        resp = client.post(
            "/api/v1/federation/webhooks/tasks/result",
            content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 404

    def test_result_webhook_requires_peer_auth(self, client, fed_enabled, peer):
        resp = client.post(
            "/api/v1/federation/webhooks/tasks/result",
            content=b"{}",
        )
        assert resp.status_code == 401


# ==========================================================================
# 16.1.3 — Heartbeat Celery task (5-min beat interval)
# ==========================================================================

class TestCeleryHeartbeatTask:
    """agentium.celery_app.federation_heartbeat probes peers on its beat tick."""

    def test_heartbeat_probes_and_suspends(self, seeded_db, beat_env, monkeypatch):
        good = _make_peer(seeded_db, "Good Peer", "http://good.local")
        bad = _make_peer(seeded_db, "Bad Peer", "http://bad.local")
        recovered = _make_peer(seeded_db, "Recovered Peer", "http://recovered.local",
                               status="suspended")

        def fake_post(url, **kwargs):
            if "bad.local" in url:
                raise httpx.ConnectError("connection refused")
            return SimpleNamespace(status_code=200)

        monkeypatch.setattr(httpx, "post", fake_post)

        result = federation_heartbeat()

        assert result == {"probed": 3, "alive": 2, "suspended": 1}

        seeded_db.refresh(good)
        seeded_db.refresh(bad)
        seeded_db.refresh(recovered)
        assert good.status == "active"
        assert good.last_heartbeat_at is not None
        assert bad.status == "suspended"
        # A previously suspended peer that answers again is reactivated
        assert recovered.status == "active"

    def test_heartbeat_skipped_when_federation_disabled(self, beat_env, monkeypatch):
        monkeypatch.setenv("FEDERATION_ENABLED", "false")

        called = []
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: called.append(a))

        result = federation_heartbeat()
        assert result == {"skipped": "federation disabled"}
        assert called == []

    def test_heartbeat_beat_schedule_is_5_minutes(self):
        """16.1.3: the beat entry probes every 300 seconds."""
        entry = celery_module.celery_app.conf.beat_schedule["federation-heartbeat"]
        assert entry["task"] == "agentium.celery_app.federation_heartbeat"
        assert entry["schedule"] == 300.0


# ==========================================================================
# 16.1.4 — Stale peer cleanup (hourly beat interval)
# ==========================================================================

class TestStalePeerCleanup:
    """Peers with no heartbeat inside the timeout window get suspended."""

    def test_cleanup_suspends_stale_peers(self, seeded_db, fed_enabled):
        stale = _make_peer(seeded_db, "Stale Peer", "http://stale.local",
                           last_heartbeat_at=datetime.utcnow() - timedelta(days=2))
        fresh = _make_peer(seeded_db, "Fresh Peer", "http://fresh.local",
                           last_heartbeat_at=datetime.utcnow() - timedelta(minutes=5))

        suspended = FederationService.cleanup_stale_peers(seeded_db)

        assert suspended == 1
        seeded_db.refresh(stale)
        seeded_db.refresh(fresh)
        assert stale.status == "suspended"
        assert fresh.status == "active"

    def test_cleanup_custom_timeout_window(self, seeded_db, fed_enabled):
        two_hours_old = _make_peer(seeded_db, "Two Hours", "http://2h.local",
                                   last_heartbeat_at=datetime.utcnow() - timedelta(hours=2))
        # Default window (24h) would keep it active; a 1h window suspends it
        suspended = FederationService.cleanup_stale_peers(seeded_db, timeout_minutes=60)
        assert suspended == 1
        seeded_db.refresh(two_hours_old)
        assert two_hours_old.status == "suspended"

    def test_cleanup_ignores_already_suspended(self, seeded_db, fed_enabled):
        _make_peer(seeded_db, "Already Suspended", "http://gone.local",
                   status="suspended",
                   last_heartbeat_at=datetime.utcnow() - timedelta(days=30))
        suspended = FederationService.cleanup_stale_peers(seeded_db)
        assert suspended == 0

    def test_cleanup_celery_task(self, seeded_db, beat_env):
        """agentium.celery_app.federation_cleanup_stale suspends stale peers."""
        _make_peer(seeded_db, "Stale Peer", "http://stale-celery.local",
                   last_heartbeat_at=datetime.utcnow() - timedelta(days=3))

        result = federation_cleanup_stale()
        assert result == {"suspended": 1}
        row = seeded_db.query(FederatedInstance).filter_by(
            base_url="http://stale-celery.local").one()
        assert row.status == "suspended"

    def test_cleanup_beat_schedule_is_hourly(self):
        """16.1.4: the beat entry runs the cleanup every hour."""
        entry = celery_module.celery_app.conf.beat_schedule["federation-cleanup-stale"]
        assert entry["task"] == "agentium.celery_app.federation_cleanup_stale"
        assert entry["schedule"] == 3600.0
