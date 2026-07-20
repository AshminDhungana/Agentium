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

    agent = HeadOfCouncil(
        agentium_id="00001",
        name="Test Head",
        status="active",
    )
    test_db.add(agent)
    test_db.commit()
    test_db.refresh(agent)

    # Build the Ethos from the operational templates (Task 5) so the agent's
    # Ethos reflects the live template values.
    ethos = agent._create_default_ethos(agent, test_db)
    test_db.flush()
    agent.ethos_id = ethos.id
    test_db.commit()
    test_db.refresh(agent)

    try:
        yield agent
    finally:
        # Tear down in FK-safe order: agent first (clears ethos_id), then ethos,
        # then the constitution.
        leftover = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if leftover:
            if leftover.ethos_id:
                linked_ethos = test_db.query(Ethos).filter_by(id=leftover.ethos_id).first()
                if linked_ethos:
                    test_db.delete(linked_ethos)
            test_db.delete(leftover)
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


def test_read_and_align_constitution_missing_fallback_file_ok(test_db, head_agent):
    # The fallback text file docs/constitution/core.md is absent in the repo.
    # Alignment must still succeed (return True) rather than fail.
    import os
    fallback = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
        "docs", "constitution", "core.md"
    )
    assert not os.path.isfile(fallback), "precondition: fallback file must be absent"
    result = head_agent.read_and_align_constitution(test_db)
    assert result is True


def test_ethos_creation_has_no_persona(test_db, head_agent):
    ethos = head_agent.ethos
    assert ethos is not None
    # No hardcoded identity persona phrasing in the Ethos mission.
    assert "ultimate decision-making authority" not in (ethos.mission_statement or "")
    assert "Eternal Head of Council" not in (ethos.mission_statement or "")
    # Persona values are no longer seeded as Ethos values.
    assert ethos.get_core_values() == []
    assert ethos.get_behavioral_rules() == []
    assert ethos.get_restrictions() == []
    # Capabilities (operational) are still present.
    assert ethos.get_capabilities()


def _seed_constitution_with_marker(test_db):
    from backend.models.entities.constitution import Constitution
    import json
    prior = test_db.query(Constitution).filter_by(agentium_id="C00001").first()
    if prior:
        test_db.delete(prior)
        test_db.commit()
    articles = {"agent_persona_and_conduct": {"title": "Persona", "content": "MARKER_PERSONA_CLAUSE be helpful."}}
    const = Constitution(
        agentium_id="C00001", version="v1.0.0", version_number=1,
        preamble="Preamble MARKER.",
        articles=json.dumps(articles),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        created_by_agentium_id="00001",
        is_active=True,
    )
    test_db.add(const)
    test_db.commit()
    return const


def test_build_system_prompt_constitution_persona(test_db):
    _seed_constitution_with_marker(test_db)
    from backend.services.prompt_template_manager import prompt_template_manager, ProviderType
    prompt, _, _ = prompt_template_manager.build_system_prompt(
        provider=ProviderType.OPENAI,
        model_name="gpt-4o",
        task_description="do a thing",
        agent_ethos=None,
        agent_tier=3,
        db=test_db,
    )
    assert "MARKER_PERSONA_CLAUSE" in prompt
