# 16.2 — Cross-Instance Communication: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify TODO §16.2.1 (task delegation) and §16.2.2 (knowledge sharing) with integration tests, and implement §16.2.3 (agent migration) as a synchronous, definition-only move between Agentium instances.

**Architecture:** Tasks 1–2 are verify-only: new pytest suites around existing delegation and knowledge-sharing code (bugs found get fixed in-task). Task 3 adds two new endpoints to the existing federation router: an admin `POST /federation/agents/{agent_id}/migrate` route that snapshots the agent definition, POSTs it directly to the peer via `httpx`, and terminates the local agent only on a 200 ack; and an HMAC-authenticated `POST /federation/webhooks/agents/receive` webhook that recreates the agent as a base `Agent` row with a freshly generated `agentium_id`. No schema migrations.

**Tech Stack:** FastAPI, SQLAlchemy, httpx, pytest (async test client), Celery (mocked via `.delay` monkeypatch), existing HMAC peer-auth (`authenticate_peer`).

**Spec:** `docs/superpowers/specs/2026-10-08-cross-instance-communication-design.md`

## Global Constraints

- Snapshot schema tag is exactly `"agentium/agent-definition/v1"` — reject anything else with HTTP 400.
- Migration is **definition-only**: agent fields, model-config *name* (`UserModelConfig.config_name`), and Ethos **identity fields only** (mission_statement, core_values, behavioral_rules, restrictions, capabilities, environment_context). Never Ethos working-memory fields (current_objective, active_plan, task_progress_markers, reasoning_artifacts, outcome_summary, lessons_learned, constitutional_references, task_progress_markers).
- Migration is **move** semantics: local agent gets `terminated_at` + `termination_reason="migrated_to:<peer_id>"` ONLY after a 200 ack from the peer. Any failure raises `ServiceUnavailableError` (from `backend/core/exceptions.py`) and leaves the agent untouched.
- New `agentium_id` on the receiving instance comes from `ReincarnationService.generate_id_with_retry(tier, db)`; tier map: `head_of_council→"head"`, `council_member→"council"`, `lead_agent→"lead"`, `task_agent→"task"`, `code_critic`/`output_critic`/`plan_critic→"critic"`.
- All webhook endpoints authenticate via the existing `authenticate_peer` FastAPI dependency (`backend/api/routes/federation.py:66`) — do not write new auth code.
- All admin endpoints gate with `get_current_user_from_token` + `current_user.is_admin` → `ForbiddenError` with code `ONLY_SOVEREIGN_CAN_MIGRATE_AGENTS` (migrate) as the established pattern shows.
- Outbound requests sign with the module-level `_sign_payload` from `backend/services/federation_service.py` and the instance signing key `FederationService._derive_signing_key(settings.FEDERATION_SHARED_SECRET)`; headers mirror `probe_peer` (`backend/services/federation_service.py:384`).
- Tests live in `backend/tests/integration/`, marked `pytestmark = pytest.mark.integration`, and reuse the fixtures/patterns of `backend/tests/integration/test_federation_api.py` (`client`, `auth_headers`, `seeded_db`, `fed_enabled`, `peer`, `_hmac_headers`, `_make_user`, `_login`).
- No frontend changes. No schema migrations. No Celery in the migration path.
- Commit after every green test cycle; every commit message ends with the attribution lines from the repo's git convention if present.

---

### Task 1: 16.2.2 — Knowledge sharing tests

**Files:**
- Create: `backend/tests/integration/test_federation_knowledge.py`
- Test: existing `/api/v1/federation/knowledge-share` webhook and `/api/v1/federation/knowledge/sync/{peer_id}` route (`backend/api/routes/federation.py:381-519`). No production code changes expected; fix bugs only if tests surface them.

**Interfaces:**
- Consumes: the `client`, `seeded_db`, `auth_headers` fixtures from `backend/tests/integration/conftest.py`; `backend.services.knowledge_service.get_knowledge_service()` (patched at the module boundary so no vector DB is needed); `FederationService.sync_constitution_from_peer` (HTTP mocked via `httpx.get`); the `backend.core.vector_store.VectorStore` constructor (patched for the sync path).
- Produces: nothing later tasks depend on (verify-only task).

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/integration/test_federation_knowledge.py`:

```python
"""
Integration tests for cross-instance knowledge sharing (TODO 16.2.2).

Covers:
  - POST /api/v1/federation/knowledge-share webhook: peer-auth ingest
    into the knowledge store with source='federated' metadata + dedup.
  - POST /api/v1/federation/knowledge/sync/{peer_id}: admin-gated pull
    of the peer's constitution into the local vector store.
"""

import hashlib
import hmac
import json
import time
from types import SimpleNamespace

import httpx
import pytest

from backend.core.config import settings

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"
PEER_URL = "http://peer-alpha.local"


def _derive_signing_key(secret: str) -> str:
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def _sign(signing_key: str, body: bytes, timestamp: int) -> str:
    message = f"{timestamp}:".encode() + body
    return hmac.new(signing_key.encode(), message, hashlib.sha256).hexdigest()


def _hmac_headers(peer_url: str, secret: str, body: bytes, timestamp: int = None):
    if timestamp is None:
        timestamp = int(time.time())
    sig = _sign(_derive_signing_key(secret), body, timestamp)
    return {
        "Content-Type": "application/json",
        "X-Agentium-Peer-Url": peer_url,
        "X-Agentium-Timestamp": str(timestamp),
        "X-Agentium-Signature": f"sha256={sig}",
    }


def _make_peer(db, name, base_url, secret=SECRET, status="active",
               trust_level="limited"):
    from backend.models.entities.federation import FederatedInstance
    peer = FederatedInstance(
        name=name,
        base_url=base_url.rstrip("/"),
        shared_secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        signing_key=_derive_signing_key(secret),
        status=status,
        trust_level=trust_level,
        capabilities_shared=["knowledge"],
    )
    db.add(peer)
    db.flush()
    return peer


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


@pytest.fixture
def fed_enabled(monkeypatch):
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", True)


@pytest.fixture
def peer(seeded_db):
    return _make_peer(seeded_db, "Peer Alpha", PEER_URL)


class TestKnowledgeShareWebhook:
    """POST /api/v1/federation/knowledge-share — inbound shared docs."""

    def _body(self, docs=None):
        docs = docs or ["Shared fact one", "Shared fact two"]
        return json.dumps({
            "collection_name": "domain_knowledge",
            "documents": docs,
            "metadatas": [{"origin": "test"} for _ in docs],
        }).encode()

    def test_share_requires_peer_auth(self, client, fed_enabled, peer):
        resp = client.post(
            "/api/v1/federation/knowledge-share",
            content=self._body(),
        )
        assert resp.status_code == 401

    def test_share_ingests_with_federated_metadata(
        self, client, seeded_db, fed_enabled, peer, monkeypatch,
    ):
        stored = []

        class _FakeKS:
            def store_or_revise_knowledge(self, content, collection_name,
                                          doc_id, metadata=None, **kw):
                stored.append({"content": content, "collection": collection_name,
                               "doc_id": doc_id, "metadata": metadata})
                return {"status": "stored"}

        import backend.services.knowledge_service as ks_mod
        monkeypatch.setattr(ks_mod, "get_knowledge_service",
                            lambda: _FakeKS())

        body = self._body()
        resp = client.post(
            "/api/v1/federation/knowledge-share",
            content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["acknowledged"] is True
        assert resp.json()["items_shared"] == 2

        assert len(stored) == 2
        assert stored[0]["collection"] == "domain_knowledge"
        assert stored[0]["metadata"]["source"] == "federated"
        assert stored[0]["metadata"]["shared_by"] == "Peer Alpha"
        assert stored[0]["metadata"]["origin"] == "test"
        assert stored[0]["doc_id"].startswith("fed_share_")

    def test_share_bad_json_rejected(self, client, fed_enabled, peer):
        resp = client.post(
            "/api/v1/federation/knowledge-share",
            content=b"not json at all",
            headers=_hmac_headers(PEER_URL, SECRET, b"not json at all"),
        )
        assert resp.status_code in (400, 422)


class TestKnowledgeSyncRoute:
    """POST /api/v1/federation/knowledge/sync/{peer_id} — constitution pull."""

    def test_sync_requires_admin(self, client, seeded_db, fed_enabled, peer):
        _make_user(seeded_db, "plainuser", is_admin=False)
        plain = _login(client, "plainuser")
        resp = client.post(
            f"/api/v1/federation/knowledge/sync/{peer.id}",
            headers=plain,
        )
        assert resp.status_code == 403

    def test_sync_success_upserts_articles(
        self, client, seeded_db, fed_enabled, peer, auth_headers, monkeypatch,
    ):
        upserts = []

        class _FakeCol:
            def upsert(self, ids, documents, metadatas):
                upserts.append({"ids": ids, "documents": documents,
                                "metadatas": metadatas})

        class _FakeStore:
            def __init__(self):
                self.client = SimpleNamespace(
                    get_or_create_collection=lambda name: _FakeCol())

        def fake_get(url, **kwargs):
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"articles": {
                    "art1": {"title": "Article 1", "content": "Body 1"},
                    "art2": {"title": "Article 2", "content": "Body 2"},
                }},
            )

        monkeypatch.setattr(httpx, "get", fake_get)
        import backend.core.vector_store as vs_mod
        monkeypatch.setattr(vs_mod, "VectorStore", _FakeStore)

        resp = client.post(
            f"/api/v1/federation/knowledge/sync/{peer.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "success"
        assert len(upserts) == 2
        assert upserts[0]["ids"] == [f"peer_{peer.id}_const_art1"]
        assert upserts[0]["metadatas"][0]["source"] == "federation"
        assert "Peer Alpha" in upserts[0]["documents"][0]

    def test_sync_peer_unreachable_returns_500(
        self, client, seeded_db, fed_enabled, peer, auth_headers, monkeypatch,
    ):
        def fake_get(url, **kwargs):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "get", fake_get)

        resp = client.post(
            f"/api/v1/federation/knowledge/sync/{peer.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "FAILED_TO_SYNC_KNOWLEDGE_FROM"
```

- [ ] **Step 2: Run the tests and triage**

Run: `cd backend && python -m pytest tests/integration/test_federation_knowledge.py -v --no-header -p no:cacheprovider`
Expected: PASS on the first run. Two things may legitimately differ from the expectations and count as **bugs to note**, not test bugs:

1. `test_sync_success_upserts_articles` — the admin login in `auth_headers_available` assumes the seeded admin's password is `"password123"`. If the seeded admin uses a different password, check how `backend/tests/integration/test_federation_api.py` logs in (`_login` uses `"password123"` for users it creates itself) and how the conftest's `auth_headers` fixture authenticates; use the conftest's `auth_headers` fixture directly if it is simpler (it is a fixture, so just add `auth_headers` as a test parameter and use it as the header dict).
2. `test_share_bad_json_rejected` — `receive_federated_knowledge` declares a Pydantic body (`FederateKnowledgeRequest`), so FastAPI validation returns 422 before any route code runs; 400 is also acceptable if the route's own JSON handling fires first. Keep the assertion as `in (400, 422)`.

Any other failure is a real bug — fix it in `backend/api/routes/federation.py` or `backend/services/federation_service.py`, ensure the test pins it, and name it in the commit message.

- [ ] **Step 3: Run the full federation suite**

Run: `cd backend && python -m pytest tests/integration/test_federation_api.py tests/integration/test_federation_knowledge.py -v --no-header -p no:cacheprovider`
Expected: all PASS (33 + this task's tests).

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_federation_knowledge.py backend/api/routes/federation.py backend/services/federation_service.py
git commit -m "feat(16.2.2): integration tests for cross-instance knowledge sharing

Covers the /knowledge-share ingest webhook (peer auth, federated
metadata, dedup boundary) and the admin-gated /knowledge/sync/{peer_id}
constitution pull. TODO 16.2.2."
```

---

### Task 2: 16.2.1 — Outbound task delegation tests

**Files:**
- Create: `backend/tests/integration/test_federation_delegation.py`
- Test: existing `backend/services/federation_service.py` (`delegate_task`, `list_federated_tasks`) — no production code changes expected; fix bugs only if tests surface them.

**Interfaces:**
- Consumes: `FederationService.delegate_task(db, target_peer_id, original_task_id, payload, my_base_url=None, my_secret=None) -> FederatedTask`; `FederationService.list_federated_tasks(db, limit=50) -> List[FederatedTask]`; `backend.services.tasks.task_executor.deliver_federated_task.delay(...)`; fixtures from `backend/tests/integration/test_federation_api.py` (copied helpers, not imported cross-test — each test file in this repo is self-contained).
- Produces: nothing later tasks depend on (verify-only task).

- [ ] **Step 1: Write the failing test file**

Create `backend/tests/integration/test_federation_delegation.py`:

```python
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
from datetime import datetime

import pytest

from backend.core.config import settings
from backend.services.federation_service import FederationService
from backend.models.entities.federation import FederatedInstance, FederatedTask

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"
PEER_URL = "http://peer-alpha.local"


# Local fixtures — the integration conftest provides db_session/seeded_db/
# client/auth_headers, but fed_enabled and peer are defined inside
# test_federation_api.py, so this file defines its own.
@pytest.fixture
def fed_enabled(monkeypatch):
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", True)


@pytest.fixture
def peer(seeded_db):
    return _make_peer(seeded_db, "Peer Alpha", PEER_URL)


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
            "backend.services.tasks.task_executor.deliver_federated_task",
            _FakeTask(),
            raising=False,
        )
        # delegate_task imports deliver_federated_task inside the function
        # body, so patching the module attribute it resolves from is enough.

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
            "backend.services.tasks.task_executor.deliver_federated_task",
            _BoomTask(),
            raising=False,
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
```

- [ ] **Step 2: Run the tests and triage**

These tests exercise existing behavior, so they are expected to PASS on the first run — any FAIL is a real bug in `delegate_task`/`list_federated_tasks`.

Run: `cd backend && python -m pytest tests/integration/test_federation_delegation.py -v --no-header -p no:cacheprovider`
Expected: all PASS. If anything fails, fix it in `backend/services/federation_service.py`, ensure the failing case's test pins the fix, and name the bug in the commit message.

- [ ] **Step 3: Run the full federation suite to confirm no regressions**

Run: `cd backend && python -m pytest tests/integration/test_federation_api.py tests/integration/test_federation_delegation.py tests/integration/test_federation_knowledge.py -v --no-header -p no:cacheprovider`
Expected: 33 + new tests, all PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_federation_delegation.py backend/services/federation_service.py
git commit -m "feat(16.2.1): integration tests for outbound task delegation

Covers delegate_task record creation, Celery dispatch arguments,
dispatch-failure resilience, inactive-peer rejection, and
list_federated_tasks in both directions. TODO 16.2.1."
```

---

### Task 3: 16.2.3 — Agent migration: receive webhook (TDD)

**Files:**
- Create: `backend/tests/integration/test_federation_migration.py`
- Modify: `backend/api/routes/federation.py` (add `AgentMigrationSnapshotRequest` next to the other request models around line 59; add the webhook route after the task-result webhook, around line 357)
- Modify: `backend/services/federation_service.py` (add `receive_migrated_agent` inside `FederationService`, after `list_federated_tasks` around line 613)

**Interfaces:**
- Consumes: `authenticate_peer` dependency (`backend/api/routes/federation.py:66`); `ReincarnationService.generate_id_with_retry(tier, db)` (`backend/services/reincarnation_service.py:265`); `Agent`/`AgentType`/`AgentStatus` (`backend/models/entities/agents.py`); `Ethos` (`backend/models/entities/constitution.py:210`); `UserModelConfig.config_name` (`backend/models/entities/user_config.py:83`); shared fixtures `client`, `seeded_db`, `auth_headers` from `backend/tests/integration/conftest.py`.
- Produces (exact signatures Task 4 relies on):
  - `FederationService.SNAPSHOT_SCHEMA == "agentium/agent-definition/v1"`
  - `FederationService.receive_migrated_agent(db, source_peer, snapshot) -> {"agentium_id": str, "id": str}`
  - Route `POST /api/v1/federation/webhooks/agents/receive` → 200 `{"agentium_id": ..., "id": ...}`

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/integration/test_federation_migration.py`:

```python
"""
Integration tests for agent migration between instances (TODO 16.2.3).

Move semantics, definition-only: the peer recreates the agent from a
portable snapshot (agentium/agent-definition/v1) carrying agent fields,
the model-config NAME (not the local FK), and Ethos identity fields only.
"""

import hashlib
import hmac
import json
import time

import pytest

from backend.core.config import settings
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.user import User

pytestmark = pytest.mark.integration

SECRET = "fed-integration-secret"
PEER_URL = "http://peer-alpha.local"
SNAPSHOT_SCHEMA = "agentium/agent-definition/v1"
RECEIVE_URL = "/api/v1/federation/webhooks/agents/receive"


def _derive_signing_key(secret: str) -> str:
    return hashlib.sha256((secret + ":sign").encode()).hexdigest()


def _sign(signing_key: str, body: bytes, timestamp: int) -> str:
    message = f"{timestamp}:".encode() + body
    return hmac.new(signing_key.encode(), message, hashlib.sha256).hexdigest()


def _hmac_headers(peer_url: str, secret: str, body: bytes, timestamp: int = None):
    if timestamp is None:
        timestamp = int(time.time())
    sig = _sign(_derive_signing_key(secret), body, timestamp)
    return {
        "Content-Type": "application/json",
        "X-Agentium-Peer-Url": peer_url,
        "X-Agentium-Timestamp": str(timestamp),
        "X-Agentium-Signature": f"sha256={sig}",
    }


def _make_peer(db, name, base_url, secret=SECRET, status="active",
               trust_level="limited"):
    from backend.models.entities.federation import FederatedInstance
    peer = FederatedInstance(
        name=name,
        base_url=base_url.rstrip("/"),
        shared_secret_hash=hashlib.sha256(secret.encode()).hexdigest(),
        signing_key=_derive_signing_key(secret),
        status=status,
        trust_level=trust_level,
        capabilities_shared=["agents"],
    )
    db.add(peer)
    db.flush()
    return peer


def _make_user(db, username: str, is_admin: bool):
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


def _snapshot(overrides=None, agent_overrides=None):
    snap = {
        "schema": SNAPSHOT_SCHEMA,
        "source_instance": "http://primary.local",
        "source_agentium_id": "30123",
        "agent": {
            "name": "Migrating Agent",
            "description": "Delegated worker",
            "agent_type": "task_agent",
            "system_prompt_override": "Be terse.",
            "persistent_role": "system_optimizer",
        },
        "preferred_model_config_name": "primary-openai",
        "ethos": {
            "agent_type": "task_agent",
            "mission_statement": "Serve the federation",
            "core_values": '["loyalty", "diligence"]',
            "behavioral_rules": '["be honest"]',
            "restrictions": '["no lying"]',
            "capabilities": '["tasks", "web"]',
            "environment_context": "hosted on primary",
        },
    }
    if agent_overrides:
        snap["agent"].update(agent_overrides)
    if overrides:
        snap.update(overrides)
    return snap


@pytest.fixture
def fed_enabled(monkeypatch):
    monkeypatch.setattr(settings, "FEDERATION_ENABLED", True)


@pytest.fixture
def peer(seeded_db):
    return _make_peer(seeded_db, "Peer Alpha", PEER_URL)


class TestReceiveMigratedAgentWebhook:
    """POST /webhooks/agents/receive recreates the agent locally."""

    def test_receive_requires_peer_auth(self, client, fed_enabled, peer):
        resp = client.post(RECEIVE_URL, json=_snapshot())
        assert resp.status_code == 401

    def test_receive_creates_agent_and_ethos(
        self, client, seeded_db, fed_enabled, peer,
    ):
        body = json.dumps(_snapshot()).encode()
        resp = client.post(
            RECEIVE_URL, content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["agentium_id"]
        assert data["id"]

        agent = seeded_db.query(Agent).filter(Agent.id == data["id"]).one()
        assert agent.agentium_id == data["agentium_id"]
        assert agent.agent_type == AgentType.TASK_AGENT
        assert agent.name == "Migrating Agent"
        assert agent.description == "Delegated worker"
        assert agent.system_prompt_override == "Be terse."
        assert agent.status == AgentStatus.INITIALIZING
        # Fresh local ID, not the source instance's ID
        assert agent.agentium_id != "30123"

        from backend.models.entities.constitution import Ethos
        ethos = seeded_db.query(Ethos).filter(Ethos.agent_id == agent.id).one()
        assert ethos.mission_statement == "Serve the federation"
        assert ethos.core_values == '["loyalty", "diligence"]'
        # Working-memory fields are NOT populated from a migration snapshot
        assert ethos.current_objective is None
        assert ethos.active_plan is None

    def test_receive_resolves_model_config_by_name(
        self, client, seeded_db, fed_enabled, peer,
    ):
        from backend.models.entities.user_config import UserModelConfig, ProviderType
        cfg = UserModelConfig(
            config_name="primary-openai",
            provider=ProviderType.OPENAI,
            default_model="gpt-4o",
        )
        seeded_db.add(cfg)
        seeded_db.flush()

        body = json.dumps(_snapshot()).encode()
        resp = client.post(
            RECEIVE_URL, content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200
        agent = seeded_db.query(Agent).filter(
            Agent.id == resp.json()["id"]).one()
        assert agent.preferred_config_id == cfg.id

    def test_receive_unmatched_model_config_name_leaves_null(
        self, client, seeded_db, fed_enabled, peer,
    ):
        body = json.dumps(
            _snapshot(overrides={"preferred_model_config_name": "no-such-config"})
        ).encode()
        resp = client.post(
            RECEIVE_URL, content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200
        agent = seeded_db.query(Agent).filter(
            Agent.id == resp.json()["id"]).one()
        assert agent.preferred_config_id is None

    def test_receive_bad_schema_tag_rejected(self, client, fed_enabled, peer):
        body = json.dumps(
            _snapshot(overrides={"schema": "agentium/agent-definition/v2"})
        ).encode()
        resp = client.post(
            RECEIVE_URL, content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 400

    def test_receive_without_ethos_still_creates_agent(
        self, client, seeded_db, fed_enabled, peer,
    ):
        body = json.dumps(_snapshot(overrides={"ethos": None})).encode()
        resp = client.post(
            RECEIVE_URL, content=body,
            headers=_hmac_headers(PEER_URL, SECRET, body),
        )
        assert resp.status_code == 200
        agent = seeded_db.query(Agent).filter(
            Agent.id == resp.json()["id"]).one()
        assert agent.ethos_id is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: FAIL — `404 Not Found` on `POST /api/v1/federation/webhooks/agents/receive` (route does not exist yet), except `test_receive_requires_peer_auth` which may already 404/401 — either way it must not be a 200.

- [ ] **Step 3: Implement `FederationService.receive_migrated_agent`**

Add inside `class FederationService` in `backend/services/federation_service.py`, after `list_federated_tasks` (around line 613):

```python
    # ── 16.2.3: Agent migration ─────────────────────────────────────────────

    SNAPSHOT_SCHEMA = "agentium/agent-definition/v1"

    # agent_type -> ID-generation tier understood by
    # ReincarnationService.generate_id_with_retry
    AGENT_TYPE_TIER_MAP = {
        "head_of_council": "head",
        "council_member": "council",
        "lead_agent": "lead",
        "task_agent": "task",
        "code_critic": "critic",
        "output_critic": "critic",
        "plan_critic": "critic",
    }

    @staticmethod
    def receive_migrated_agent(
        db: Session,
        source_peer: FederatedInstance,
        snapshot: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Recreate an agent from a migration snapshot sent by a peer.

        Definition-only: agent fields, model-config NAME, and Ethos
        identity fields. Working memory, task history, and knowledge do
        NOT transfer. Returns {"agentium_id", "id"} for the ack.
        """
        if snapshot.get("schema") != FederationService.SNAPSHOT_SCHEMA:
            raise BadRequestError(
                error=f"Unsupported snapshot schema '{snapshot.get('schema')}'.",
                code="UNSUPPORTED_SNAPSHOT_SCHEMA",
            )

        from backend.services.reincarnation_service import ReincarnationService
        from backend.models.entities.agents import Agent, AgentType, AgentStatus
        from backend.models.entities.constitution import Ethos

        agent_data = snapshot.get("agent") or {}
        try:
            agent_type = AgentType(agent_data.get("agent_type", "task_agent"))
        except ValueError:
            raise BadRequestError(
                error=f"Unknown agent_type '{agent_data.get('agent_type')}'.",
                code="UNKNOWN_AGENT_TYPE",
            )

        tier = FederationService.AGENT_TYPE_TIER_MAP[agent_type.value]
        new_agentium_id = ReincarnationService.generate_id_with_retry(tier, db)

        # Resolve the model-config NAME against local configs — names port
        # between instances; local FK ids do not.
        preferred_config_id = None
        config_name = snapshot.get("preferred_model_config_name")
        if config_name:
            from backend.models.entities.user_config import UserModelConfig
            cfg = db.query(UserModelConfig).filter(
                UserModelConfig.config_name == config_name
            ).first()
            if cfg:
                preferred_config_id = cfg.id

        agent = Agent(
            agentium_id=new_agentium_id,
            agent_type=agent_type,
            name=agent_data.get("name", f"Migrated from {source_peer.name}"),
            description=agent_data.get("description"),
            system_prompt_override=agent_data.get("system_prompt_override"),
            persistent_role=agent_data.get("persistent_role"),
            preferred_config_id=preferred_config_id,
            status=AgentStatus.INITIALIZING,
        )
        db.add(agent)
        db.flush()

        ethos_data = snapshot.get("ethos")
        if ethos_data:
            ethos = Ethos(
                agent_type=agent_type.value,
                agent_id=str(agent.id),
                mission_statement=ethos_data.get(
                    "mission_statement", "Migrated agent"),
                core_values=ethos_data.get("core_values", "[]"),
                behavioral_rules=ethos_data.get("behavioral_rules", "[]"),
                restrictions=ethos_data.get("restrictions", "[]"),
                capabilities=ethos_data.get("capabilities", "[]"),
                environment_context=ethos_data.get("environment_context"),
            )
            db.add(ethos)
            db.flush()
            agent.ethos_id = ethos.id

        db.commit()
        db.refresh(agent)
        logger.info(
            f"Federation: received migrated agent '{agent.name}' "
            f"({agent.agentium_id}) from '{source_peer.name}'"
        )
        return {"agentium_id": agent.agentium_id, "id": str(agent.id)}
```

- [ ] **Step 4: Implement the receive webhook route**

In `backend/api/routes/federation.py`, add this request model next to `TaskResultRequest` (around line 59):

```python
class AgentMigrationSnapshotRequest(BaseModel):
    schema: str
    source_instance: str
    source_agentium_id: str
    agent: Dict[str, Any]
    preferred_model_config_name: Optional[str] = None
    ethos: Optional[Dict[str, Any]] = None
```

And add this route after the task-result webhook (before the Phase 11.2 section, around line 357):

```python
# ── 16.2.3: Agent migration ─────────────────────────────────────────────────

@router.post(
    "/webhooks/agents/receive",
    summary="Receive Migrated Agent",
    description="Webhook: a peer instance sends an agent definition snapshot; "
                "recreate the agent locally. Definition-only (no memory, no knowledge).",
    responses=build_responses(None),
)
async def receive_migrated_agent(
    snapshot: AgentMigrationSnapshotRequest,
    db: Session = Depends(get_db),
    peer=Depends(authenticate_peer),
):
    """
    Webhook: a peer instance sends an agent definition snapshot;
    recreate the agent locally (definition-only).
    """
    return FederationService.receive_migrated_agent(
        db=db,
        source_peer=peer,
        snapshot=snapshot.model_dump(),
    )
```

- [ ] **Step 5: Run the receive tests to verify they pass**

Run: `cd backend && python -m pytest tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: all `TestReceiveMigratedAgentWebhook` tests PASS. Two known pitfalls to watch:
- If `Agent(...)` creation fails with an agentium_id constraint or event-listener conflict (unit-test conftests register an `ensure_agent_id` mapper event), check `backend/models/entities/base.py` and the integration conftest for ID-defaulting listeners; the explicitly passed `agentium_id` must survive. If a listener overwrites it, fix the listener interaction inside the test environment — do not weaken the model.
- If `generate_id_with_retry` fails to see uncommitted test-transaction state, confirm the `db` it receives is the overridden `get_db` session (it is — the route's `Depends(get_db)` is what the conftest patches).

- [ ] **Step 6: Run the full federation suite**

Run: `cd backend && python -m pytest tests/integration/test_federation_api.py tests/integration/test_federation_delegation.py tests/integration/test_federation_knowledge.py tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/integration/test_federation_migration.py backend/api/routes/federation.py backend/services/federation_service.py
git commit -m "feat(16.2.3): agent-migration receive webhook

New POST /federation/webhooks/agents/receive recreates an agent from
an agentium/agent-definition/v1 snapshot: fresh agentium_id via
ReincarnationService, model-config name resolution, Ethos identity
fields only. TODO 16.2.3 (receive half)."
```

---

### Task 4: 16.2.3 — Agent migration: admin migrate route (TDD)

**Files:**
- Modify: `backend/tests/integration/test_federation_migration.py` (add `TestMigrateAgentRoute` and `TestBuildAgentSnapshot` classes)
- Modify: `backend/services/federation_service.py` (add `build_agent_snapshot` and `migrate_agent` inside `FederationService`)
- Modify: `backend/api/routes/federation.py` (add `AgentMigrateRequest` model and the `POST /agents/{agent_id}/migrate` route, after the delegate-task route around line 259)

**Interfaces:**
- Consumes: `FederationService.receive_migrated_agent` and `FederationService.SNAPSHOT_SCHEMA` (Task 3); `authenticate_peer` webhook on the peer (Task 3); module-level `_sign_payload` and `FederationService._derive_signing_key` (`backend/services/federation_service.py:31,78`); `probe_peer`'s outbound header shape (`federation_service.py:384-405`); `Agent`, `AgentStatus` (`backend/models/entities/agents.py`); `Ethos` (`backend/models/entities/constitution.py:210`); `UserModelConfig` (`backend/models/entities/user_config.py:64`); `ServiceUnavailableError`, `NotFoundError`, `BadRequestError`, `ForbiddenError` (`backend/core/exceptions.py`); `settings.FEDERATION_INSTANCE_URL`, `settings.FEDERATION_SHARED_SECRET` (`backend/core/config.py`).
- Produces:
  - `FederationService.build_agent_snapshot(db, agent) -> Dict[str, Any]` — portable `agentium/agent-definition/v1` dict
  - `FederationService.migrate_agent(db, agent_id, target_peer_id) -> Dict[str, Any]` — returns `{"source_agentium_id", "new_agentium_id", "new_agent_id", "peer_name"}`
  - Route `POST /api/v1/federation/agents/{agent_id}/migrate` (admin-only) → 200 on success

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/integration/test_federation_migration.py` (new imports at the top: `from datetime import datetime` and `from backend.models.entities.federation import FederatedInstance` — the latter already imported lazily inside `_make_peer`; keep it lazy or hoist it, either is fine):

```python
def _make_agent(db, name="Local Agent", agentium_id="30123",
                system_prompt_override=None, with_ethos=True,
                with_config=None):
    from backend.models.entities.agents import Agent, AgentType, AgentStatus
    agent = Agent(
        agentium_id=agentium_id,
        agent_type=AgentType.TASK_AGENT,
        name=name,
        description="A local worker",
        system_prompt_override=system_prompt_override,
        status=AgentStatus.ACTIVE,
    )
    if with_config is not None:
        agent.preferred_config_id = with_config.id
    db.add(agent)
    db.flush()

    if with_ethos:
        from backend.models.entities.constitution import Ethos
        ethos = Ethos(
            agent_type="task_agent",
            agent_id=str(agent.id),
            mission_statement="Do good work",
            core_values='["diligence"]',
            behavioral_rules='["be honest"]',
            restrictions='["no lying"]',
            capabilities='["tasks"]',
            environment_context="hosted locally",
            # Working-memory fields set — these must NOT transfer
            current_objective="secret in-flight objective",
            active_plan='{"step": 1}',
        )
        db.add(ethos)
        db.flush()
        agent.ethos_id = ethos.id
    return agent


class TestBuildAgentSnapshot:
    """FederationService.build_agent_snapshot — portable definition dict."""

    def test_snapshot_carries_identity_not_memory(
        self, seeded_db, fed_enabled, peer,
    ):
        agent = _make_agent(seeded_db, system_prompt_override="Be terse.")
        snap = FederationService.build_agent_snapshot(seeded_db, agent)

        assert snap["schema"] == FederationService.SNAPSHOT_SCHEMA
        assert snap["source_agentium_id"] == "30123"
        assert snap["agent"]["name"] == "Local Agent"
        assert snap["agent"]["agent_type"] == "task_agent"
        assert snap["agent"]["system_prompt_override"] == "Be terse."
        # Identity transfers...
        assert snap["ethos"]["mission_statement"] == "Do good work"
        assert snap["ethos"]["environment_context"] == "hosted locally"
        # ...working memory does NOT
        assert "current_objective" not in snap["ethos"]
        assert "active_plan" not in snap["ethos"]

    def test_snapshot_resolves_model_config_name(
        self, seeded_db, fed_enabled, peer,
    ):
        from backend.models.entities.user_config import UserModelConfig, ProviderType
        cfg = UserModelConfig(
            config_name="local-openai",
            provider=ProviderType.OPENAI,
            default_model="gpt-4o",
        )
        seeded_db.add(cfg)
        seeded_db.flush()

        agent = _make_agent(seeded_db, with_config=cfg)
        snap = FederationService.build_agent_snapshot(seeded_db, agent)
        assert snap["preferred_model_config_name"] == "local-openai"

    def test_snapshot_without_config_and_ethos(
        self, seeded_db, fed_enabled, peer,
    ):
        agent = _make_agent(seeded_db, with_ethos=False)
        snap = FederationService.build_agent_snapshot(seeded_db, agent)
        assert snap["preferred_model_config_name"] is None
        assert snap["ethos"] is None


class TestMigrateAgentRoute:
    """POST /agents/{agent_id}/migrate — synchronous move."""

    def _mock_peer_accept(self, monkeypatch):
        """Mock httpx.post so the peer 'accepts' the migration."""
        captured = {}

        def fake_post(url, content=None, headers=None, timeout=None, **kw):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = content
            return SimpleNamespace(
                status_code=200,
                json=lambda: {"agentium_id": "30999", "id": "new-agent-uuid"},
            )

        monkeypatch.setattr(httpx, "post", fake_post)
        return captured

    def test_migrate_success_terminates_local_agent(
        self, client, seeded_db, fed_enabled, peer, auth_headers, monkeypatch,
    ):
        agent = _make_agent(seeded_db)
        captured = self._mock_peer_accept(monkeypatch)

        resp = client.post(
            f"/api/v1/federation/agents/{agent.id}/migrate",
            headers=auth_headers,
            json={"target_peer_id": peer.id},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["source_agentium_id"] == "30123"
        assert data["new_agentium_id"] == "30999"
        assert data["peer_name"] == "Peer Alpha"

        # Outbound call went to the peer's receive webhook, HMAC-signed
        assert captured["url"] == (
            f"{PEER_URL}/api/v1/federation/webhooks/agents/receive")
        assert "X-Agentium-Signature" in captured["headers"]

        # Move semantics: local agent terminated with provenance
        seeded_db.refresh(agent)
        assert agent.status == AgentStatus.TERMINATED
        assert agent.terminated_at is not None
        assert agent.termination_reason == f"migrated_to:{peer.id}"

    def test_migrate_requires_admin(
        self, client, seeded_db, fed_enabled, peer,
    ):
        _make_user(seeded_db, "plainuser", is_admin=False)
        plain = _login(client, "plainuser")
        agent = _make_agent(seeded_db, agentium_id="30150")

        resp = client.post(
            f"/api/v1/federation/agents/{agent.id}/migrate",
            headers=plain,
            json={"target_peer_id": peer.id},
        )
        assert resp.status_code == 403

    def test_migrate_unknown_agent_404(
        self, client, seeded_db, fed_enabled, peer, auth_headers,
    ):
        resp = client.post(
            f"/api/v1/federation/agents/{uuid.uuid4()}/migrate",
            headers=auth_headers,
            json={"target_peer_id": peer.id},
        )
        assert resp.status_code == 404

    def test_migrate_inactive_peer_400(
        self, client, seeded_db, fed_enabled, auth_headers, monkeypatch,
    ):
        suspended = _make_peer(seeded_db, "Suspended", "http://susp-mig.local",
                               status="suspended")
        agent = _make_agent(seeded_db, agentium_id="30160")
        self._mock_peer_accept(monkeypatch)

        resp = client.post(
            f"/api/v1/federation/agents/{agent.id}/migrate",
            headers=auth_headers,
            json={"target_peer_id": suspended.id},
        )
        assert resp.status_code == 400

    def test_migrate_peer_unreachable_leaves_agent_untouched(
        self, client, seeded_db, fed_enabled, peer, auth_headers, monkeypatch,
    ):
        agent = _make_agent(seeded_db, agentium_id="30170")

        def fake_post(url, **kw):
            raise httpx.ConnectError("connection refused")

        monkeypatch.setattr(httpx, "post", fake_post)

        resp = client.post(
            f"/api/v1/federation/agents/{agent.id}/migrate",
            headers=auth_headers,
            json={"target_peer_id": peer.id},
        )
        assert resp.status_code == 503
        seeded_db.refresh(agent)
        assert agent.status == AgentStatus.ACTIVE
        assert agent.terminated_at is None
        assert agent.termination_reason is None

    def test_migrate_peer_non_200_leaves_agent_untouched(
        self, client, seeded_db, fed_enabled, peer, auth_headers, monkeypatch,
    ):
        agent = _make_agent(seeded_db, agentium_id="30180")

        def fake_post(url, **kw):
            return SimpleNamespace(status_code=500, json=lambda: {})

        monkeypatch.setattr(httpx, "post", fake_post)

        resp = client.post(
            f"/api/v1/federation/agents/{agent.id}/migrate",
            headers=auth_headers,
            json={"target_peer_id": peer.id},
        )
        assert resp.status_code == 503
        seeded_db.refresh(agent)
        assert agent.status == AgentStatus.ACTIVE
        assert agent.termination_reason is None
```

Add these imports at the top of the test file alongside the existing ones:

```python
import uuid
from types import SimpleNamespace

import httpx

from backend.services.federation_service import FederationService
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: FAIL — `AttributeError: FederationService has no attribute 'build_agent_snapshot'` and 404 on `POST /api/v1/federation/agents/{id}/migrate`.

- [ ] **Step 3: Implement `build_agent_snapshot` and `migrate_agent`**

Add inside `class FederationService` in `backend/services/federation_service.py`, after `receive_migrated_agent`:

```python
    @staticmethod
    def build_agent_snapshot(db: Session, agent) -> Dict[str, Any]:
        """
        Build the portable agentium/agent-definition/v1 snapshot for an
        agent: agent fields, model-config NAME, Ethos identity fields.
        Working memory, task history, and knowledge never transfer.
        """
        from backend.models.entities.user_config import UserModelConfig

        config_name = None
        if agent.preferred_config_id:
            cfg = db.query(UserModelConfig).filter(
                UserModelConfig.id == agent.preferred_config_id
            ).first()
            if cfg:
                config_name = cfg.config_name

        ethos_snapshot = None
        if agent.ethos_id:
            from backend.models.entities.constitution import Ethos
            ethos = db.query(Ethos).filter(Ethos.id == agent.ethos_id).first()
            if ethos:
                # Identity fields ONLY — never working memory
                ethos_snapshot = {
                    "agent_type": ethos.agent_type,
                    "mission_statement": ethos.mission_statement,
                    "core_values": ethos.core_values,
                    "behavioral_rules": ethos.behavioral_rules,
                    "restrictions": ethos.restrictions,
                    "capabilities": ethos.capabilities,
                    "environment_context": ethos.environment_context,
                }

        return {
            "schema": FederationService.SNAPSHOT_SCHEMA,
            "source_instance": settings.FEDERATION_INSTANCE_URL,
            "source_agentium_id": agent.agentium_id,
            "agent": {
                "name": agent.name,
                "description": agent.description,
                "agent_type": agent.agent_type.value if hasattr(agent.agent_type, "value") else agent.agent_type,
                "system_prompt_override": agent.system_prompt_override,
                "persistent_role": agent.persistent_role,
            },
            "preferred_model_config_name": config_name,
            "ethos": ethos_snapshot,
        }

    @classmethod
    def migrate_agent(
        cls,
        db: Session,
        agent_id: str,
        target_peer_id: str,
    ) -> Dict[str, Any]:
        """
        Move an agent to a peer instance — synchronous, definition-only.

        POSTs the snapshot to the peer's receive webhook. ONLY on a 200
        ack is the local agent terminated (with provenance in
        termination_reason). Any failure raises ServiceUnavailableError
        and leaves the local agent untouched.
        """
        from backend.models.entities.agents import Agent, AgentStatus

        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise NotFoundError(error="Agent not found.", code="AGENT_NOT_FOUND")

        peer = cls.get_peer(db, target_peer_id)
        if peer.status != "active":
            raise BadRequestError(
                error="Target peer is not active.",
                code="TARGET_PEER_IS_NOT_ACTIVE",
            )

        snapshot = cls.build_agent_snapshot(db, agent)
        body = json.dumps(snapshot).encode()
        ts = int(time.time())
        my_secret = getattr(settings, "FEDERATION_SHARED_SECRET", "")
        sig = _sign_payload(cls._derive_signing_key(my_secret), body, ts)

        try:
            resp = httpx.post(
                f"{peer.base_url}/api/v1/federation/webhooks/agents/receive",
                content=body,
                headers={
                    "Content-Type": "application/json",
                    "X-Agentium-Peer-Url": settings.FEDERATION_INSTANCE_URL,
                    "X-Agentium-Timestamp": str(ts),
                    "X-Agentium-Signature": f"sha256={sig}",
                },
                timeout=30,
            )
        except Exception as exc:
            logger.warning(
                f"Federation: migration of agent {agent.agentium_id} to "
                f"'{peer.name}' failed: {exc}"
            )
            raise ServiceUnavailableError(
                error=f"Peer '{peer.name}' unreachable: {exc}",
                code="PEER_UNREACHABLE_DURING_MIGRATION",
            )

        if resp.status_code != 200:
            logger.warning(
                f"Federation: migration of agent {agent.agentium_id} to "
                f"'{peer.name}' returned {resp.status_code}"
            )
            raise ServiceUnavailableError(
                error=f"Peer '{peer.name}' rejected the migration "
                      f"(HTTP {resp.status_code}).",
                code="PEER_REJECTED_MIGRATION",
            )

        ack = resp.json()

        # Peer acknowledged — NOW terminate locally (move semantics)
        agent.status = AgentStatus.TERMINATED
        agent.terminated_at = datetime.utcnow()
        agent.termination_reason = f"migrated_to:{peer.id}"
        db.commit()

        logger.info(
            f"Federation: migrated agent '{agent.name}' ({agent.agentium_id}) "
            f"to '{peer.name}' as {ack.get('agentium_id')}"
        )
        return {
            "source_agentium_id": agent.agentium_id,
            "new_agentium_id": ack.get("agentium_id"),
            "new_agent_id": ack.get("id"),
            "peer_name": peer.name,
        }
```

Add `import json` to the module imports at the top of `backend/services/federation_service.py` if not already present (it currently imports `uuid, hmac, hashlib, time` — `json` is NOT imported; add it).

- [ ] **Step 4: Implement the migrate route**

In `backend/api/routes/federation.py`, add the request model next to `TaskDelegateRequest` (around line 43):

```python
class AgentMigrateRequest(BaseModel):
    target_peer_id: str
```

And the route after the delegate-task route (around line 259), before `list_federated_tasks`:

```python
@router.post(
    "/agents/{agent_id}/migrate",
    summary="Migrate Agent To Peer",
    description="Move an agent to a peer instance (definition-only). The local "
                "agent is terminated only after the peer confirms receipt. "
                "Sovereign only.",
    responses=build_responses(None),
)
def migrate_agent(
    agent_id: str,
    request: AgentMigrateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user_from_token),
):
    """Move an agent to a peer instance (definition-only, move semantics)."""
    if not current_user.is_admin:
        raise ForbiddenError(
            error="Only Sovereign can migrate agents.",
            code="ONLY_SOVEREIGN_CAN_MIGRATE_AGENTS",
        )
    return FederationService.migrate_agent(
        db=db,
        agent_id=agent_id,
        target_peer_id=request.target_peer_id,
    )
```

- [ ] **Step 5: Run the migration tests to verify they pass**

Run: `cd backend && python -m pytest tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: all tests in `TestReceiveMigratedAgentWebhook`, `TestBuildAgentSnapshot`, and `TestMigrateAgentRoute` PASS.

Watch for: `settings.FEDERATION_INSTANCE_URL` must exist and be non-empty in the test environment (the 16.1 suite's `beat_env` fixture sets `FEDERATION_INSTANCE_URL=http://primary.local` via env var; if the plain test env lacks it, add to the test file's `fed_enabled` fixture: `monkeypatch.setattr(settings, "FEDERATION_INSTANCE_URL", "http://primary.local")` and `monkeypatch.setattr(settings, "FEDERATION_SHARED_SECRET", "primary-secret")`).

- [ ] **Step 6: Run the entire federation suite**

Run: `cd backend && python -m pytest tests/integration/test_federation_api.py tests/integration/test_federation_delegation.py tests/integration/test_federation_knowledge.py tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: all PASS (33 + all new tests).

- [ ] **Step 7: Commit**

```bash
git add backend/tests/integration/test_federation_migration.py backend/api/routes/federation.py backend/services/federation_service.py
git commit -m "feat(16.2.3): agent-migration admin route — synchronous move

POST /federation/agents/{id}/migrate snapshots the agent definition
(agentium/agent-definition/v1), POSTs it to the peer's receive webhook,
and terminates the local agent only on 200 ack. Peer failures raise
ServiceUnavailableError and leave the agent untouched. TODO 16.2.3."
```

---

### Task 5: Mark TODO 16.2 complete + final verification

**Files:**
- Modify: `docs/documents/TODO.md` (section 16.2, around line 797)

**Interfaces:**
- Consumes: all green federation suites from Tasks 1–4.
- Produces: updated TODO.md with verification notes (the repo's convention, as done for 16.1).

- [ ] **Step 1: Run the entire federation suite one final time**

Run: `cd backend && python -m pytest tests/integration/test_federation_api.py tests/integration/test_federation_delegation.py tests/integration/test_federation_knowledge.py tests/integration/test_federation_migration.py -v --no-header -p no:cacheprovider`
Expected: all PASS. Note the exact test count for the TODO verification note.

- [ ] **Step 2: Mark the TODO checkboxes and add verification notes**

In `docs/documents/TODO.md`, change section 16.2 (around line 797) from:

```markdown
- [ ] **16.2 — Cross-Instance Communication**
  - [ ] 16.2.1 — Task delegation to peer instances works
  - [ ] 16.2.2 — Knowledge sharing between peers works
  - [ ] 16.2.3 — Agent migration between instances works
```

to:

```markdown
- [x] **16.2 — Cross-Instance Communication**
  - [x] 16.2.1 — Task delegation to peer instances works
  - [x] 16.2.2 — Knowledge sharing between peers works
  - [x] 16.2.3 — Agent migration between instances works

  > **Verified:** integration suites in `backend/tests/integration/`:
  > `test_federation_delegation.py` (outbound delegation: record creation,
  > Celery dispatch args, dispatch-failure resilience, inactive-peer
  > rejection), `test_federation_knowledge.py` (knowledge-share webhook
  > ingest with federated metadata + dedup boundary; admin-gated
  > constitution sync), `test_federation_migration.py` (definition-only
  > move: receive webhook creates Agent + Ethos identity, migrate route
  > terminates local agent only on 200 ack, failures leave agent intact).
```

- [ ] **Step 3: Commit**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark Section 16.2 Cross-Instance Communication complete

Verification notes added per repo convention."
```

- [ ] **Step 4: Merge / push per repo workflow**

If working on a feature branch, merge to `main` per the repo's usual flow (as done for 16.1 and 12.4). Then:

```bash
git push
```

---

## Plan Self-Review (completed after writing)

- **Spec coverage:** 16.2.1 → Task 2; 16.2.2 → Task 1; 16.2.3 receive half → Task 3; migrate half → Task 4; snapshot/error/testing tables → Tasks 3–4; TODO marking → Task 5. Spec's bug-fix policy is embedded in Tasks 1–2's triage steps. No spec requirement left untasked.
- **Placeholders:** none — every step carries complete code or exact commands.
- **Type consistency:** `receive_migrated_agent(db, source_peer, snapshot)`, `build_agent_snapshot(db, agent)`, `migrate_agent(db, agent_id, target_peer_id)`, `SNAPSHOT_SCHEMA = "agentium/agent-definition/v1"` are identical across Tasks 3 and 4 and their tests.




---
