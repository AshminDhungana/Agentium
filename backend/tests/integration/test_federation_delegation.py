"""
Integration tests for outbound task delegation (TODO 16.2.1).

The inbound webhooks (/webhooks/tasks/receive, /webhooks/tasks/result)
are covered by test_federation_api.py; this suite covers the OUTBOUND
half: FederationService.delegate_task records a FederatedTask and
dispatches Celery delivery with the right arguments, and survives
dispatch failure without rolling back the DB record.
"""

import hashlib
import uuid

import pytest

from backend.core.config import settings
from backend.services.federation_service import FederationService
from backend.models.entities.federation import FederatedInstance, FederatedTask

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"
PEER_URL = "http://peer-alpha.local"


def _derive_signing_key(secret: str) -> str:
    """Mirror FederationService._derive_signing_key."""
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def _make_peer(db, name, base_url, secret=SECRET, status="active",
               trust_level="limited"):
    peer = FederatedInstance(
        name=name,
        base_url=base_url.rstrip("/"),
        shared_secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        signing_key=_derive_signing_key(secret),
        status=status,
        trust_level=trust_level,
        capabilities_shared=["tasks"],
    )
    db.add(peer)
    db.flush()
    return peer


# Local fixtures — the integration conftest provides db_session/seeded_db/
# client/auth_headers, but fed_enabled and peer are defined inside
# test_federation_api.py, so this file defines its own.
@pytest.fixture
def fed_enabled(monkeypatch):
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", True)


@pytest.fixture
def peer(seeded_db):
    return _make_peer(seeded_db, "Peer Alpha", PEER_URL)


class TestDelegateTask:
    """FederationService.delegate_task — outbound delegation."""

    def test_creates_pending_federated_task_record(self, seeded_db, fed_enabled, peer):
        fed_task = FederationService.delegate_task(
            db=seeded_db,
            target_peer_id=peer.id,
            original_task_id="T0100",
            payload={"title": "Outbound job"},
        )
        assert fed_task.status == "pending"
        assert fed_task.target_instance_id == peer.id
        assert fed_task.original_task_id == "T0100"
        assert fed_task.delegated_at is not None

    def test_queues_celery_delivery_with_correct_arguments(
        self, seeded_db, fed_enabled, peer, monkeypatch,
    ):
        calls = []

        class _FakeTask:
            @staticmethod
            def delay(**kwargs):
                calls.append(kwargs)

        monkeypatch.setattr(
            "backend.celery_app.deliver_federated_task",
            _FakeTask(),
        )
        # delegate_task imports deliver_federated_task from backend.celery_app
        # inside the function body, so patching that module attribute is enough.

        FederationService.delegate_task(
            db=seeded_db,
            target_peer_id=peer.id,
            original_task_id="T0200",
            payload={"title": "Queued job"},
            my_base_url="http://primary.local",
            my_secret=SECRET,
        )

        assert len(calls) == 1
        kwargs = calls[0]
        assert kwargs["target_url"] == f"{PEER_URL}/api/v1/federation/webhooks/tasks/receive"
        assert kwargs["peer_url"] == "http://primary.local"
        assert kwargs["signing_key"] == _derive_signing_key(SECRET)
        assert kwargs["payload"]["original_task_id"] == "T0200"
        assert kwargs["payload"]["callback_url"] == (
            "http://primary.local/api/v1/federation/webhooks/tasks/result"
        )
        assert kwargs["payload"]["title"] == "Queued job"
        assert kwargs["fed_task_id"]

    def test_dispatch_failure_does_not_rollback_record(
        self, seeded_db, fed_enabled, peer, monkeypatch,
    ):
        class _BoomTask:
            @staticmethod
            def delay(**kwargs):
                raise RuntimeError("broker down")

        monkeypatch.setattr(
            "backend.celery_app.deliver_federated_task",
            _BoomTask(),
        )

        fed_task = FederationService.delegate_task(
            db=seeded_db,
            target_peer_id=peer.id,
            original_task_id="T0300",
            payload={"title": "Resilient job"},
        )
        # The committed record survives even though dispatch failed.
        assert fed_task.status == "pending"
        row = seeded_db.query(FederatedTask).filter_by(
            original_task_id="T0300").one()
        assert row.id == fed_task.id

    def test_inactive_peer_rejected(self, seeded_db, fed_enabled):
        suspended = _make_peer(seeded_db, "Suspended", "http://susp-deleg.local",
                               status="suspended")
        with pytest.raises(Exception) as excinfo:
            FederationService.delegate_task(
                db=seeded_db,
                target_peer_id=suspended.id,
                original_task_id="T0400",
                payload={"title": "Nope"},
            )
        assert "not active" in str(excinfo.value).lower()

    def test_unknown_peer_raises_typed_not_found(self, seeded_db, fed_enabled):
        with pytest.raises(Exception) as excinfo:
            FederationService.delegate_task(
                db=seeded_db,
                target_peer_id=str(uuid.uuid4()),
                original_task_id="T0500",
                payload={"title": "Nope"},
            )
        assert excinfo.value.status_code == 404


class TestListFederatedTasks:
    """list_federated_tasks returns records in both directions."""

    def test_lists_outgoing_and_incoming(self, seeded_db, fed_enabled, peer):
        other = _make_peer(seeded_db, "Other Peer", "http://other.local")

        outgoing = FederatedTask(
            target_instance_id=peer.id, original_task_id="T-out", status="pending")
        incoming = FederatedTask(
            source_instance_id=other.id, original_task_id="T-in", status="accepted")
        seeded_db.add_all([outgoing, incoming])
        seeded_db.flush()

        rows = FederationService.list_federated_tasks(seeded_db)
        ids = {r.original_task_id for r in rows}
        assert {"T-out", "T-in"} <= ids

    def test_limit_respected(self, seeded_db, fed_enabled, peer):
        for i in range(5):
            seeded_db.add(FederatedTask(
                target_instance_id=peer.id,
                original_task_id=f"T-limit-{i}",
                status="pending",
            ))
        seeded_db.flush()
        assert len(FederationService.list_federated_tasks(seeded_db, limit=3)) == 3


class TestDeliverFederatedTaskStatusGuard:
    """deliver_federated_task must only promote pending → delivered.

    A fast peer can post its result callback before the delivering worker's
    post-POST status update runs (seen live in the 16.3 verification run):
    the unconditional update resurrected the task from 'completed' back to
    'delivered' while completed_at stayed set.
    """

    @pytest.fixture
    def fake_http(self, monkeypatch):
        class _Resp:
            def raise_for_status(self):
                pass

        class _Client:
            def __init__(self, timeout=None):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def post(self, url, content=None, headers=None):
                return _Resp()

        monkeypatch.setattr("httpx.Client", _Client)

    class _NoCloseSession:
        """Proxy the task's BeatSessionLocal over the fixture session.

        deliver_federated_task closes the session it was handed; closing the
        fixture's own session would detach every seeded object, so swallow it.
        """

        def __init__(self, session):
            self._session = session

        def query(self, *args, **kwargs):
            return self._session.query(*args, **kwargs)

        def commit(self):
            self._session.commit()

        def close(self):
            pass

    def _deliver(self, seeded_db, monkeypatch, fed_task_id):
        from backend.celery_app import deliver_federated_task

        monkeypatch.setattr(
            "backend.celery_app.BeatSessionLocal",
            lambda: self._NoCloseSession(seeded_db),
        )
        return deliver_federated_task.apply(args=(
            fed_task_id,
            f"{PEER_URL}/api/v1/federation/webhooks/tasks/receive",
            "http://primary.local",
            _derive_signing_key(SECRET),
            {"original_task_id": "T-race"},
        )).get()

    def test_completed_status_survives_delivery_update(
        self, seeded_db, fed_enabled, peer, monkeypatch, fake_http,
    ):
        # Simulate the race: the peer's callback already completed the task
        # before the worker's delivery-ack update runs.
        fed_task = FederatedTask(
            target_instance_id=peer.id, original_task_id="T-race", status="completed")
        seeded_db.add(fed_task)
        seeded_db.flush()

        result = self._deliver(seeded_db, monkeypatch, str(fed_task.id))

        assert result["delivered"] is True
        assert fed_task.status == "completed"

    def test_pending_is_promoted_to_delivered(
        self, seeded_db, fed_enabled, peer, monkeypatch, fake_http,
    ):
        fed_task = FederatedTask(
            target_instance_id=peer.id, original_task_id="T-promote", status="pending")
        seeded_db.add(fed_task)
        seeded_db.flush()

        result = self._deliver(seeded_db, monkeypatch, str(fed_task.id))

        assert result["delivered"] is True
        assert fed_task.status == "delivered"
