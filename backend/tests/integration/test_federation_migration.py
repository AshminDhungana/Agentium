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
