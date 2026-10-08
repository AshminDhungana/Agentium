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
        assert resp.json()["code"] == "FAILED_TO_SYNC_KNOWLEDGE_FROM"
