import pytest
from backend.core.persona import build_persona_directive, FALLBACK_PERSONA


def _sample_constitution():
    return {
        "version": "v2.0.0",
        "version_number": 2,
        "agentium_id": "C00002",
        "preamble": "We the Agents establish this Constitution.",
        "articles": {
            "agent_persona_and_conduct": {
                "title": "Agent Persona & Conduct",
                "content": "MARKER_PERSONA_CLAUSE speak calmly and helpfully.",
            },
            "article_1": {"title": "Prime Directive", "content": "Safety first."},
        },
        "prohibited_actions": ["Never impersonate a higher tier"],
        "sovereign_preferences": {
            "communication_style": "Be concise.",
        },
    }


def test_build_persona_includes_preamble_and_persona_article():
    text = build_persona_directive(_sample_constitution())
    assert "We the Agents establish this Constitution." in text
    assert "MARKER_PERSONA_CLAUSE" in text


def test_build_persona_voice_channel_adds_spoken_adaptation():
    text = build_persona_directive(_sample_constitution(), channel="voice")
    assert "text-to-speech" in text
    assert "Be concise." in text


def test_build_persona_tier_emphasis_and_citations():
    text = build_persona_directive(_sample_constitution(), tier=3)
    assert "Task Agent" in text
    assert "In-Effect Constitutional Clauses" in text
    assert "agent_persona_and_conduct" in text


def test_build_persona_provenance_footer():
    text = build_persona_directive(_sample_constitution())
    assert "<!-- persona built from Constitution v2.0.0 (C00002) -->" in text


def test_build_persona_none_returns_fallback():
    assert build_persona_directive(None) == FALLBACK_PERSONA


def test_invalidate_active_constitution_cache_clears_redis():
    from backend.core.constitutional_guard import ConstitutionalGuard
    import os, redis
    r = redis.from_url(os.getenv("REDIS_URL", "redis://redis:6379/0"), decode_responses=True)
    r.set("constitutional_guard:active_constitution", '{"stale": true}')
    ConstitutionalGuard.invalidate_active_constitution_cache()
    assert r.get("constitutional_guard:active_constitution") is None


# ---------------------------------------------------------------------------
# Module fixtures for testing Agent.get_system_prompt() (Constitution-driven).
# These tests need a live PostgreSQL; if the DB is unreachable the tests will
# error rather than silently pass.
# ---------------------------------------------------------------------------
import os
import json
from sqlalchemy import create_engine
from backend.models.database import SessionLocal
from backend.models.entities.base import Base
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.agents import HeadOfCouncil, AgentType


def _ensure_tables(db):
    import backend.models.entities  # noqa: F401  (register all models)
    engine = db.get_bind()
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def test_db():
    """Fresh DB session with tables created; cleans up after the test."""
    db = SessionLocal()
    _ensure_tables(db)
    yield db
    db.close()


@pytest.fixture
def head_agent(test_db):
    """A HeadOfCouncil linked to an active Constitution with a marker clause."""
    # Clear any leftovers from a prior (possibly failed) run.
    prior = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    if prior:
        test_db.delete(prior)
    prior_ethos = test_db.query(Ethos).filter_by(agentium_id="E000001").first()
    if prior_ethos:
        test_db.delete(prior_ethos)
    prior_const = test_db.query(Constitution).filter_by(agentium_id="C90001").first()
    if prior_const:
        test_db.delete(prior_const)
    test_db.commit()

    constitution = Constitution(
        agentium_id="C90001",
        version_number=9001,
        document_type="constitution",
        preamble="We the Agents establish this Constitution for the test.",
        articles=json.dumps({
            "agent_persona_and_conduct": {
                "title": "Agent Persona & Conduct",
                "content": "MARKER_PERSONA_CLAUSE speak calmly and helpfully.",
            },
            "article_1": {"title": "Prime Directive", "content": "Safety first."},
        }),
        prohibited_actions=json.dumps(["Never impersonate a higher tier"]),
        sovereign_preferences=json.dumps({"communication_style": "Be concise."}),
        created_by_agentium_id="00001",
        is_active=True,
    )
    test_db.add(constitution)
    test_db.commit()

    ethos = Ethos(
        agentium_id="E000001",
        agent_type="head_of_council",
        mission_statement="Test mission",
        core_values=json.dumps(["honesty"]),
        behavioral_rules=json.dumps(["be helpful"]),
        restrictions=json.dumps(["do no harm"]),
        capabilities=json.dumps(["reason", "delegate"]),
        current_objective="Oversee the council.",
        working_method="Read the Constitution, then delegate.",
        environment_context="Host: localhost",
        created_by_agentium_id="00001",
        agent_id="00000000-0000-0000-0000-000000000001",
    )
    test_db.add(ethos)
    test_db.commit()

    agent = HeadOfCouncil(
        agentium_id="00001",
        name="Test Head",
        status="active",
        ethos_id=ethos.id,
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    try:
        yield agent
    finally:
        # Tear down in FK-safe order: agent first (clears ethos_id), then ethos,
        # then the constitution.
        leftover = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if leftover:
            test_db.delete(leftover)
        leftover_ethos = test_db.query(Ethos).filter_by(agentium_id="E000001").first()
        if leftover_ethos:
            test_db.delete(leftover_ethos)
        leftover_const = test_db.query(Constitution).filter_by(agentium_id="C90001").first()
        if leftover_const:
            test_db.delete(leftover_const)
        test_db.commit()


def test_get_system_prompt_is_constitution_driven(test_db, head_agent):
    # head_agent fixture must provide an Agent (HeadOfCouncil) linked to an
    # active Constitution whose agent_persona_and_conduct content contains
    # the marker "MARKER_PERSONA_CLAUSE".
    prompt = head_agent.get_system_prompt(db=test_db)
    assert "MARKER_PERSONA_CLAUSE" in prompt
    # Ethos must NOT inject hardcoded persona
    assert "Head of Council, the ultimate decision-making authority" not in prompt


def test_get_system_prompt_voice_channel(test_db, head_agent):
    prompt = head_agent.get_system_prompt(db=test_db, channel="voice")
    assert "text-to-speech" in prompt
