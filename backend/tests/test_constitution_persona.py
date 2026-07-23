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
from sqlalchemy.orm import Session
from backend.models.database import SessionLocal, engine
from backend.models.entities.base import Base
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.voting import AmendmentVoting, IndividualVote
from backend.models.entities.agents import HeadOfCouncil, AgentType


def _ensure_tables(db):
    import backend.models.entities  # noqa: F401  (register all models)
    Base.metadata.create_all(bind=engine)


@pytest.fixture
def test_db():
    """Fresh DB session with tables created.

    Wrapped in an outer transaction that is rolled back at teardown so no
    test data is ever committed to the shared database.  Tests/fixtures may
    call ``commit()`` (releasing savepoints) but the outer rollback keeps
    the live database clean between runs — preventing cross-test and
    cross-run constraint violations (e.g. duplicate ``Ethos E00001``).
    """
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    _ensure_tables(db)
    yield db
    db.close()
    transaction.rollback()
    connection.close()


@pytest.fixture
def head_agent(test_db):
    """A HeadOfCouncil linked to an active Constitution with a marker clause."""
    # Clear any leftovers from a prior (possibly failed) run.
    with test_db.no_autoflush:
        prior = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if prior:
            test_db.query(IndividualVote).filter_by(
                voter_agentium_id="00001"
            ).delete(synchronize_session=False)
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
        # Tear down in FK-safe order: delete votes first, then agent (clears
        # ethos_id), then ethos, then the constitution.
        with test_db.no_autoflush:
            leftover = test_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            if leftover:
                test_db.query(IndividualVote).filter_by(
                    voter_agentium_id="00001"
                ).delete(synchronize_session=False)
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
    from backend.models.entities.voting import AmendmentVoting, IndividualVote
    import json
    test_db.query(IndividualVote).delete()
    test_db.query(AmendmentVoting).delete()
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
    # Negative: no hardcoded tier identity must leak through (Constitution is
    # the sole identity source).
    assert "You are a Task Agent focused on efficient execution" not in prompt


def test_seed_constitution_has_persona_article(test_db):
    from backend.services.initialization_service import InitializationService
    # ensure fresh seed
    from backend.models.entities.constitution import Constitution
    from backend.models.entities.voting import AmendmentVoting, IndividualVote
    test_db.query(IndividualVote).delete()
    test_db.query(AmendmentVoting).delete()
    existing = test_db.query(Constitution).filter_by(is_active=True).all()
    for e in existing:
        test_db.delete(e)
    test_db.commit()
    const = InitializationService.create_default_constitution(test_db)
    articles = const.get_articles_dict()
    assert "agent_persona_and_conduct" in articles
    prefs = const.get_sovereign_preferences()
    assert "communication_style" in prefs


def test_get_persona_channel_voice_contains_tts(test_db, head_agent):
    prompt = head_agent.get_system_prompt(db=test_db, channel="voice")
    assert "text-to-speech" in prompt


def test_no_hardcoded_persistent_ethos_persona():
    from pathlib import Path
    legacy_phrases = [
        "Eternal Head of Council",
        "ultimate decision-making authority in Agentium",
    ]
    # Resolve paths relative to the project root (repo layout:
    # <root>/backend/tests/test_constitution_persona.py) so the test is
    # independent of the current working directory.
    repo_root = Path(__file__).resolve().parent.parent.parent
    targets = [
        repo_root / "backend" / "services" / "persistent_council.py",
        repo_root / "backend" / "services" / "overflow_recovery.py",
    ]
    for path in targets:
        text = path.read_text(encoding="utf-8")
        for phrase in legacy_phrases:
            assert phrase not in text, f"'{phrase}' still present in {path}"


def test_acceptance_edit_constitution_updates_agent_and_voice(test_db):
    from backend.services.initialization_service import InitializationService
    from backend.models.entities.agents import Agent, AgentType, Ethos, HeadOfCouncil
    from backend.models.entities.constitution import Constitution
    from backend.core.constitutional_guard import ConstitutionalGuard
    import json
    import datetime

    # 0. Clean slate for constitutions so this acceptance test is self-contained
    #    even against a shared/persistent test database with leftover rows from
    #    prior runs (the new-constitution row this test creates can otherwise
    #    collide on the unique agentium_id / version_number). We deliberately
    #    leave the agent/ethos rows alone to avoid cascading into live
    #    violation_reports written by the running backend.
    test_db.query(IndividualVote).delete()
    test_db.query(AmendmentVoting).delete()
    test_db.query(Constitution).delete()
    test_db.commit()

    # 1. Seed a constitution with a unique persona clause.
    const = InitializationService.create_default_constitution(test_db)
    articles = const.get_articles_dict()
    articles["agent_persona_and_conduct"]["content"] = "UNIQUE_CLAUSE_ALPHA speak like Alpha."
    const.articles = json.dumps(articles)
    test_db.commit()

    # 2. Fresh agent + ethos.
    agent = test_db.query(Agent).filter_by(agentium_id="00001").first()
    if agent is None:
        # Use the HeadOfCouncil subclass so the single-table polymorphic
        # identity matches (a base Agent with agent_type=HEAD_OF_COUNCIL
        # triggers an incompatible-polymorphic-identity flush warning).
        agent = HeadOfCouncil(agentium_id="00001", name="Head of Council")
        test_db.add(agent)
        test_db.flush()
        ethos = Ethos(
            agentium_id="E00001",
            agent_type=AgentType.HEAD_OF_COUNCIL.value,
            mission_statement="Operational mission only — NOT persona.",
            core_values=json.dumps([]),
            behavioral_rules=json.dumps([]),
            restrictions=json.dumps([]),
            capabilities=json.dumps([]),
            created_by_agentium_id="00001",
            agent_id=agent.id,
            is_verified=True,
            verified_by_agentium_id="00001",
        )
        test_db.add(ethos)
        test_db.flush()
        agent.ethos_id = ethos.id
        test_db.commit()

    prompt_before = agent.get_system_prompt(db=test_db)
    assert "UNIQUE_CLAUSE_ALPHA" in prompt_before
    # Ethos persona must NOT leak (strengthens Task 3's vacuous check).
    assert "Operational mission only" not in prompt_before

    voice_before = agent.get_system_prompt(db=test_db, channel="voice")
    assert "UNIQUE_CLAUSE_ALPHA" in voice_before and "text-to-speech" in voice_before

    # 3. Simulate the UI edit: write a NEW active constitution version with a new clause.
    new_version_number = (const.version_number or 1) + 1
    articles2 = const.get_articles_dict()
    articles2["agent_persona_and_conduct"]["content"] = "UNIQUE_CLAUSE_BETA speak like Beta."
    new_const = Constitution(
        agentium_id=f"C{new_version_number:04d}",
        version=f"v{new_version_number}.0.0",
        version_number=new_version_number,
        preamble=const.preamble,
        articles=json.dumps(articles2),
        prohibited_actions=const.prohibited_actions,
        sovereign_preferences=const.sovereign_preferences,
        created_by_agentium_id="00001",
        is_active=True,
        effective_date=datetime.datetime.utcnow(),
    )
    const.is_active = False
    test_db.add(new_const)
    test_db.commit()
    ConstitutionalGuard.invalidate_active_constitution_cache()

    # 4. A fresh read must reflect the NEW clause, not the old.
    prompt_after = agent.get_system_prompt(db=test_db)
    assert "UNIQUE_CLAUSE_BETA" in prompt_after
    assert "UNIQUE_CLAUSE_ALPHA" not in prompt_after

    voice_after = agent.get_system_prompt(db=test_db, channel="voice")
    assert "UNIQUE_CLAUSE_BETA" in voice_after


def test_preview_persona_renders_draft():
    from backend.core.persona import build_persona_directive
    draft = {
        "preamble": "Draft preamble DRAFT_MARKER.",
        "articles": {"agent_persona_and_conduct": {"title": "Persona", "content": "DRAFT_PERSONA_CLAUSE"}},
        "prohibited_actions": [],
        "sovereign_preferences": {"communication_style": "Friendly."},
    }
    rendered = build_persona_directive(draft, tier=0, channel="text")
    assert "DRAFT_MARKER" in rendered and "DRAFT_PERSONA_CLAUSE" in rendered
