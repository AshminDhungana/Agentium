"""
Integration tests for Constitution and Ethos models (3.3.3).
Verifies articles, amendments, ethos records persistence and relationships.
"""
import pytest
import json
from datetime import datetime, timezone
from backend.models.entities.constitution import Constitution, Ethos, DocumentType


def test_constitution_articles_persist_and_parse(db_session):
    """Verify Constitution articles JSON persists and get_articles_dict normalizes data."""
    articles_data = {
        "article_1": "The Sovereign holds ultimate decision power.",
        "article_2": {"title": "Council Powers", "content": "Council deliberates on major proposals."},
    }
    constitution = Constitution(
        agentium_id="C00002",
        version_number=1,
        version="v1.0.0",
        document_type=DocumentType.CONSTITUTION,
        articles=json.dumps(articles_data),
        prohibited_actions=json.dumps(["unauthorized_execution"]),
        sovereign_preferences=json.dumps({"privacy": "high"}),
        created_by_agentium_id="00001",
    )
    db_session.add(constitution)
    db_session.commit()

    fetched = db_session.query(Constitution).filter_by(agentium_id="C00002").first()
    assert fetched is not None

    articles_dict = fetched.get_articles_dict()
    assert "article_1" in articles_dict
    assert articles_dict["article_1"]["title"] == "Article 1"
    assert articles_dict["article_1"]["content"] == "The Sovereign holds ultimate decision power."
    assert articles_dict["article_2"]["title"] == "Council Powers"
    assert articles_dict["article_2"]["content"] == "Council deliberates on major proposals."

    assert fetched.get_prohibited_actions_list() == ["unauthorized_execution"]
    assert fetched.get_sovereign_preferences() == {"privacy": "high"}


def test_constitution_amendment_chain(db_session):
    """Verify amendment_of and replaces_version_id self-referential relationships."""
    c1 = Constitution(
        agentium_id="C10001",
        version_number=1,
        version="v1.0.0",
        articles=json.dumps({"article_1": "Initial v1"}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        created_by_agentium_id="00001",
        is_active=False,
    )
    db_session.add(c1)
    db_session.commit()

    c2 = Constitution(
        agentium_id="C10002",
        version_number=2,
        version="v2.0.0",
        articles=json.dumps({"article_1": "Amended v2"}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        created_by_agentium_id="00001",
        replaces_version_id=c1.id,
        amendment_of=c1.id,
        is_active=True,
    )
    db_session.add(c2)
    db_session.commit()

    db_session.refresh(c1)
    db_session.refresh(c2)

    assert c2.replaces_version.id == c1.id
    assert c2.amended_from.id == c1.id

    chain = c2.get_amendment_chain()
    assert len(chain) == 2
    assert chain[0].id == c1.id
    assert chain[1].id == c2.id


def test_constitution_version_validation():
    """Verify Constitution validates version string and version_number."""
    c = Constitution(version_number=1, articles="{}", prohibited_actions="[]", sovereign_preferences="{}", created_by_agentium_id="00001")

    with pytest.raises(ValueError, match="Version must start with 'v'"):
        c.validate_version("version", "1.0.0")

    with pytest.raises(ValueError, match="Version number must be positive integer"):
        c.validate_version_number("version_number", 0)


def test_constitution_archive(db_session, sample_constitution):
    """Verify archive() sets archived_date and is_active=False."""
    assert sample_constitution.is_active is True
    assert sample_constitution.archived_date is None

    sample_constitution.archive()
    db_session.commit()

    fetched = db_session.query(Constitution).filter_by(id=sample_constitution.id).first()
    assert fetched.is_active is False
    assert fetched.archived_date is not None


def test_ethos_persist_with_working_memory(db_session, sample_task_agent):
    """Verify Ethos model working memory fields persist and parse correctly."""
    ethos = Ethos(
        agentium_id="E30002",
        agent_id=sample_task_agent.id,
        agent_type="task_agent",
        mission_statement="Execute worker tasks reliably.",
        core_values=json.dumps(["accuracy", "compliance"]),
        behavioral_rules=json.dumps(["always double check output"]),
        restrictions=json.dumps(["no external calls without permission"]),
        capabilities=json.dumps(["python_execution", "vector_search"]),
        current_objective="Optimize database indexes",
        active_plan=json.dumps({"steps": ["analyze slow queries", "add index"]}),
        constitutional_references=json.dumps(["Article 2 Clause 1"]),
        task_progress_markers=json.dumps({"step_1": "done"}),
        reasoning_artifacts=json.dumps([{"thought": "Index on task_id needed"}]),
        outcome_summary="Created index on task_id",
        lessons_learned=json.dumps(["Indexes improve search performance"]),
        version=1,
        is_verified=True,
        created_by_agentium_id="00001",
    )
    db_session.add(ethos)
    db_session.commit()

    fetched = db_session.query(Ethos).filter_by(agentium_id="E30002").first()
    assert fetched is not None
    assert fetched.get_core_values() == ["accuracy", "compliance"]
    assert fetched.get_behavioral_rules() == ["always double check output"]
    assert fetched.get_restrictions() == ["no external calls without permission"]
    assert fetched.get_capabilities() == ["python_execution", "vector_search"]
    assert fetched.current_objective == "Optimize database indexes"
    assert fetched.outcome_summary == "Created index on task_id"


def test_ethos_agent_fk_link(db_session, sample_task_agent, sample_ethos):
    """Verify bidirectional link between Agent and Ethos."""
    assert sample_task_agent.ethos_id == sample_ethos.id
    assert sample_ethos.agent_id == sample_task_agent.id
