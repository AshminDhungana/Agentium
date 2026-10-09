"""
Integration tests for the federated result-callback loop (TODO 16.3.3).

Covers FederationService.notify_federation_result: the hook the task
executor calls when a federated local task reaches a terminal state.
It must (a) update the incoming FederatedTask row so the receiving
instance's UI shows completion, and (b) best-effort dispatch the
send_federation_result Celery callback to the source instance.
"""

import hashlib
import json

import pytest

from backend.core.config import settings
from backend.services.federation_service import FederationService
from backend.models.entities.federation import FederatedInstance, FederatedTask
from backend.models.entities.task import Task

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"


def _derive_signing_key(secret: str) -> str:
    """Mirror FederationService._derive_signing_key."""
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def _make_peer(db, name="Peer Alpha", base_url="http://peer-alpha.local"):
    peer = FederatedInstance(
        name=name,
        base_url=base_url.rstrip("/"),
        shared_secret_hash=hashlib.sha256(SECRET.encode()).hexdigest(),
        signing_key=_derive_signing_key(SECRET),
        status="active",
        trust_level="limited",
        capabilities_shared=["tasks"],
    )
    db.add(peer)
    db.flush()
    return peer


@pytest.fixture
def recorder(monkeypatch):
    """Capture send_federation_result.delay kwargs.

    The helper imports send_federation_result inside its method body from
    backend.celery_app, so patching the module attribute is enough.
    """
    calls = []

    class _FakeTask:
        @staticmethod
        def delay(**kwargs):
            calls.append(kwargs)

    monkeypatch.setattr("backend.celery_app.send_federation_result", _FakeTask())
    return calls


def _receive_task(db, peer, original_task_id="T0100",
                  callback_url="http://primary.local/api/v1/federation/webhooks/tasks/result"):
    """Create a federated local task via the real receive path."""
    fed_task = FederationService.receive_delegated_task(
        db=db,
        source_peer=peer,
        original_task_id=original_task_id,
        payload={"title": "Federated job", "callback_url": callback_url},
    )
    local_task = db.query(Task).filter(Task.id == fed_task.local_task_id).one()
    db.refresh(local_task)
    return local_task, fed_task


class TestNotifyFederationResult:

    def test_completed_dispatches_callback_with_correct_arguments(
        self, seeded_db, recorder,
    ):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer)
        local_task.result_summary = "Job finished OK"
        local_task.result_data = {"full_output": "done"}
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert len(recorder) == 1
        kwargs = recorder[0]
        assert kwargs["callback_url"] == "http://primary.local/api/v1/federation/webhooks/tasks/result"
        assert kwargs["signing_key"] == peer.signing_key
        assert kwargs["original_task_id"] == "T0100"
        assert kwargs["local_task_id"] == fed_task.local_task_id
        assert kwargs["task_status"] == "completed"
        assert kwargs["result_summary"] == "Job finished OK"
        assert kwargs["result_data"] == {"full_output": "done"}
        assert kwargs["peer_url"] == settings.FEDERATION_INSTANCE_URL.rstrip("/")

        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"
        assert fed_task.completed_at is not None

    def test_failed_dispatches_callback_with_failed_status(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer)

        FederationService.notify_federation_result(
            seeded_db, local_task, "failed",
            result_summary="Failed: provider_unreachable",
        )

        assert recorder[0]["task_status"] == "failed"
        assert recorder[0]["result_summary"] == "Failed: provider_unreachable"
        seeded_db.refresh(fed_task)
        assert fed_task.status == "failed"
        assert fed_task.completed_at is None

    def test_non_federated_task_is_a_no_op(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, _ = _receive_task(seeded_db, peer)
        local_task.execution_context = json.dumps({"federated": False})
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert recorder == []

    def test_missing_callback_url_still_updates_status_and_skips_dispatch(
        self, seeded_db, recorder,
    ):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer, callback_url=None)

        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert recorder == []
        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"

    def test_unknown_source_peer_skips_dispatch_but_updates_status(
        self, seeded_db, recorder,
    ):
        peer = _make_peer(seeded_db)
        local_task, fed_task = _receive_task(seeded_db, peer)
        ctx = json.loads(local_task.execution_context)
        ctx["source_instance_id"] = "00000000-0000-0000-0000-000000000000"
        local_task.execution_context = json.dumps(ctx)
        seeded_db.commit()



        FederationService.notify_federation_result(seeded_db, local_task, "completed")

        assert recorder == []
        seeded_db.refresh(fed_task)
        assert fed_task.status == "completed"

    def test_malformed_execution_context_never_raises(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, _ = _receive_task(seeded_db, peer)
        local_task.execution_context = "not-json{{"
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")
        # malformed context == treated as non-federated: no dispatch, no raise
        assert recorder == []

    def test_no_federated_task_row_never_raises(self, seeded_db, recorder):
        peer = _make_peer(seeded_db)
        local_task, _ = _receive_task(seeded_db, peer)
        seeded_db.query(FederatedTask).delete()
        seeded_db.commit()

        FederationService.notify_federation_result(seeded_db, local_task, "completed")
        assert recorder == []
