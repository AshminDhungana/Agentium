"""
Integration tests for 6.1 — environment/host grounding in Ethos + ChromaDB.

The ChromaDB tests use the local PersistentClient (TESTING=true / no CHROMA_HOST),
so they exercise VectorStore without a live server.
"""

import pytest
from sqlalchemy.orm import Session

from backend.core.environment_context import (
    AGENT_ENVIRONMENT_CONTEXT,
    ENV_CONTEXT_DOC_ID,
)
from backend.core.vector_store import get_vector_store
from backend.tools.ethos_tool import ethos_tool, _load_ethos
from backend.models.entities.constitution import Ethos
from backend.services.reincarnation_service import reincarnation_service
from backend.models.entities.agents import CouncilMember

pytestmark = pytest.mark.integration


def test_add_environment_context_seeded_and_queryable():
    vs = get_vector_store()
    vs.initialize()
    vs.add_environment_context(
        AGENT_ENVIRONMENT_CONTEXT, doc_id=ENV_CONTEXT_DOC_ID
    )
    ctx = vs.query_hierarchical_context("task_agent", "where is my desktop")
    env = ctx.get("agent_environment")
    assert env is not None
    assert env["documents"] and env["documents"][0]
    blob = " ".join(env["documents"][0])
    assert "/host_home/Desktop" in blob


def test_hierarchical_context_returns_environment_for_all_tiers():
    vs = get_vector_store()
    vs.initialize()
    vs.add_environment_context(
        AGENT_ENVIRONMENT_CONTEXT, doc_id=ENV_CONTEXT_DOC_ID
    )
    for tier in ("head_of_council", "council_member", "lead_agent", "task_agent"):
        ctx = vs.query_hierarchical_context(tier, "can you reach the internet")
        assert "agent_environment" in ctx


def test_initialize_knowledge_base_seeds_environment_context(db_session: Session):
    from backend.services.knowledge_service import get_knowledge_service

    svc = get_knowledge_service()
    svc.initialize_knowledge_base(db_session)

    vs = get_vector_store()
    ctx = vs.query_hierarchical_context("task_agent", "where is my desktop")
    env = ctx.get("agent_environment")
    assert env is not None
    blob = " ".join(env["documents"][0])
    assert "/host_home/Desktop" in blob
    assert "internet" in blob.lower()
