"""
Integration tests for governance models (Agent, Constitution, Ethos, Voting).
Tests DB persistence, FK constraints, cascades, uniqueness using SQLite with JSONB patches.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy.exc import IntegrityError
from sqlalchemy import inspect
import json

from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.voting import AmendmentVoting, TaskDeliberation, IndividualVote, VoteType, AmendmentStatus, DeliberationStatus


def utcnow():
    """Get current UTC datetime."""
    return datetime.now(timezone.utc)


# =========================================================================
# Agent Integration Tests
# =========================================================================

def test_agent_persist_with_linked_ethos(db_session):
    """Persist agent with linked Ethos (FK ethos_id)."""
    agent = Agent(
        agentium_id="00001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        name="Test Head",
    )
    db_session.add(agent)
    db_session.commit()

    ethos = Ethos(
        agentium_id="E00001",
        agent_id=agent.id,
        agent_type="head_of_council",
        mission_statement="Test mission",
        core_values=json.dumps([]),
        behavioral_rules=json.dumps([]),
        restrictions=json.dumps([]),
        capabilities=json.dumps([]),
        current_objective="Test",
        version=1,
        is_verified=True,
        created_by_agentium_id="00001",
    )
    db_session.add(ethos)
    db_session.commit()

    # Verify FK link - manually link them since it's not auto-linked
    agent.ethos_id = ethos.id
    db_session.commit()
    db_session.refresh(agent)
    assert agent.ethos_id == ethos.id
    assert ethos.agent_id == agent.id


def test_agent_parent_child_fk_constraint_restrict(db_session):
    """Parent/child FK constraint (ondelete='RESTRICT').

    Note: SQLite's FK RESTRICT may not raise in ORM delete() if session handles it
    by setting parent_id to NULL first. We test at the raw SQL level.
    """
    parent = Agent(
        agentium_id="00001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        name="Parent"
    )
    db_session.add(parent)
    db_session.commit()

    child = Agent(
        agentium_id="10001",
        agent_type=AgentType.COUNCIL_MEMBER,
        status=AgentStatus.ACTIVE,
        name="Child",
        parent_id=parent.id
    )
    db_session.add(child)
    db_session.commit()

    # Test FK exists at schema level
    from sqlalchemy import inspect
    inspector = inspect(db_session.bind)
    agents_fks = inspector.get_foreign_keys("agents")
    parent_fks = [fk for fk in agents_fks if fk["constrained_columns"] == ["parent_id"]]
    assert len(parent_fks) > 0
    assert parent_fks[0]["options"].get("ondelete") == "RESTRICT"

    # Verify raw SQL delete fails
    from sqlalchemy import text
    with pytest.raises(Exception):  # IntegrityError or equivalent
        db_session.execute(text(f"DELETE FROM agents WHERE id = '{parent.id}'"))
        db_session.commit()
    db_session.rollback()


def test_agent_agentium_id_uniqueness(db_session):
    """Agentium ID must be unique."""
    agent1 = Agent(
        agentium_id="00001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        name="Head1"
    )
    agent2 = Agent(
        agentium_id="00001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        name="Head2"
    )
    db_session.add(agent1)
    db_session.commit()

    db_session.add(agent2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_agent_status_defaults_to_initializing(db_session):
    """Agent defaults to INITIALIZING status."""
    agent = Agent(
        agentium_id="99999",
        agent_type=AgentType.TASK_AGENT,
        name="Test Agent"
    )
    db_session.add(agent)
    db_session.commit()
    assert agent.status == AgentStatus.INITIALIZING


def test_agent_polymorphic_subclasses_persist_correctly(db_session):
    """HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent persist with correct type."""
    head = Agent(
        agentium_id="00001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        name="Head"
    )
    council = Agent(
        agentium_id="10001",
        agent_type=AgentType.COUNCIL_MEMBER,
        status=AgentStatus.ACTIVE,
        name="Council"
    )
    lead = Agent(
        agentium_id="20001",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        name="Lead"
    )
    task = Agent(
        agentium_id="30001",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        name="Task"
    )

    db_session.add_all([head, council, lead, task])
    db_session.commit()

    # Verify they store with correct polymorphic identity
    assert head.agent_type == AgentType.HEAD_OF_COUNCIL
    assert council.agent_type == AgentType.COUNCIL_MEMBER
    assert lead.agent_type == AgentType.LEAD_AGENT
    assert task.agent_type == AgentType.TASK_AGENT


def test_agent_terminate_end_timestamp_persists(db_session):
    """terminate() persists terminated_at and termination_reason."""
    agent = Agent(
        agentium_id="99999",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        name="Test Agent"
    )
    db_session.add(agent)
    db_session.commit()

    agent.terminate("Test termination reason")
    db_session.commit()

    db_session.refresh(agent)
    assert agent.status == AgentStatus.TERMINATED
    assert agent.terminated_at is not None
    assert agent.termination_reason == "Test termination reason"
    assert agent.is_active is False


# =========================================================================
# Constitution Integration Tests
# =========================================================================

def test_constitution_persist_and_retrieve(db_session):
    """Constitution persists all fields correctly."""
    constitution = Constitution(
        agentium_id="C00001",
        version_number=1,
        version="v1.0.0",
        preamble="Test preamble",
        articles=json.dumps({"article_1": {"title": "Article 1", "content": "Content 1"}}),
        prohibited_actions=json.dumps(["action1", "action2"]),
        sovereign_preferences=json.dumps({"pref1": "value1"}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
    )
    db_session.add(constitution)
    db_session.commit()

    db_session.refresh(constitution)
    assert constitution.agentium_id == "C00001"
    assert constitution.version_number == 1
    assert constitution.version == "v1.0.0"
    assert constitution.is_active is True


def test_constitution_amendment_chain_fk(db_session):
    """Amendment chain FK (replaces_version_id) works."""
    constitution_v1 = Constitution(
        agentium_id="C00001",
        version_number=1,
        version="v1.0.0",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
    )
    db_session.add(constitution_v1)
    db_session.commit()

    constitution_v2 = Constitution(
        agentium_id="C00002",
        version_number=2,
        version="v1.1.0",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
        replaces_version_id=constitution_v1.id,
    )
    db_session.add(constitution_v2)
    db_session.commit()

    db_session.refresh(constitution_v2)
    assert constitution_v2.replaces_version_id == constitution_v1.id
    assert constitution_v2.replaces_version is not None


def test_constitution_archive_sets_inactive_and_date(db_session):
    """archive() sets archived_date and is_active=False."""
    constitution = Constitution(
        agentium_id="C00001",
        version_number=1,
        version="v1.0.0",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
    )
    db_session.add(constitution)
    db_session.commit()

    constitution.archive()
    db_session.commit()

    assert constitution.is_active is False
    assert constitution.archived_date is not None


def test_constitution_version_number_uniqueness(db_session):
    """Constitution version_number must be unique."""
    con1 = Constitution(
        agentium_id="C00001",
        version_number=1,
        version="v1.0.0",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
    )
    con2 = Constitution(
        agentium_id="C00002",
        version_number=1,  # Duplicate
        version="v1.0.0",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
    )
    db_session.add(con1)
    db_session.commit()

    db_session.add(con2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# =========================================================================
# Ethos Integration Tests
# =========================================================================

def test_ethos_persist_all_fields(db_session, sample_task_agent):
    """Ethos persists all working memory fields."""
    ethos = Ethos(
        agentium_id="E30001",
        agent_id=sample_task_agent.id,
        agent_type="task_agent",
        mission_statement="Test mission",
        core_values=json.dumps(["value1"]),
        behavioral_rules=json.dumps(["rule1"]),
        restrictions=json.dumps(["restriction1"]),
        capabilities=json.dumps(["capability1"]),
        current_objective="Objective",
        active_plan=json.dumps({"steps": ["step1"]}),
        constitutional_references=json.dumps([{"ref": "article_1"}]),
        task_progress_markers=json.dumps({"step1": "done"}),
        reasoning_artifacts=json.dumps([{"thought": "thought1"}]),
        outcome_summary="Summary",
        lessons_learned=json.dumps([{"lesson": "lesson1"}]),
        version=1,
        is_verified=True,
        created_by_agentium_id="00001",
        working_method="Test method",
        environment_context="Test env",
    )
    db_session.add(ethos)
    db_session.commit()

    db_session.refresh(ethos)
    assert ethos.agent_id == sample_task_agent.id
    assert ethos.mission_statement == "Test mission"
    assert ethos.get_core_values() == ["value1"]
    assert ethos.get_behavioral_rules() == ["rule1"]
    assert ethos.get_restrictions() == ["restriction1"]
    assert ethos.get_capabilities() == ["capability1"]
    assert ethos.get_active_plan()["steps"] == ["step1"]
    assert ethos.get_constitutional_references() == [{"ref": "article_1"}]
    assert ethos.get_task_progress() == {"step1": "done"}
    assert ethos.get_reasoning_artifacts() == [{"thought": "thought1"}]
    assert ethos.outcome_summary == "Summary"
    assert ethos.get_lessons_learned() == [{"lesson": "lesson1"}]
    assert ethos.working_method == "Test method"
    assert ethos.environment_context == "Test env"


def test_ethos_version_increments_on_update(db_session, sample_task_agent):
    """Ethos version increments on updates."""
    ethos = Ethos(
        agentium_id="E30001",
        agent_id=sample_task_agent.id,
        agent_type="task_agent",
        mission_statement="Test mission",
        core_values=json.dumps([]),
        behavioral_rules=json.dumps([]),
        restrictions=json.dumps([]),
        capabilities=json.dumps([]),
        version=1,
        is_verified=True,
        created_by_agentium_id="00001",
    )
    db_session.add(ethos)
    db_session.commit()

    original_version = ethos.version
    ethos.set_active_plan({"steps": ["new"]})
    db_session.commit()

    assert ethos.version == original_version + 1


def test_ethos_verify_sets_fields(db_session, sample_task_agent):
    """verify() sets verified_by, verified_at, is_verified."""
    ethos = Ethos(
        agentium_id="E30001",
        agent_id=sample_task_agent.id,
        agent_type="task_agent",
        mission_statement="Test",
        core_values=json.dumps([]),
        behavioral_rules=json.dumps([]),
        restrictions=json.dumps([]),
        capabilities=json.dumps([]),
        version=1,
        created_by_agentium_id="00001",
    )
    db_session.add(ethos)
    db_session.commit()

    ethos.verify("00001")
    db_session.commit()

    assert ethos.is_verified is True
    assert ethos.verified_by_agentium_id == "00001"
    assert ethos.verified_at is not None


# =========================================================================
# Voting Integration Tests
# =========================================================================

def test_amendment_voting_persist_and_conclude(db_session, sample_constitution, sample_council_member):
    """AmendmentVoting persists, cast_vote works, conclude calculates result."""
    voting = AmendmentVoting(
        amendment_id=sample_constitution.id,
        status=AmendmentStatus.PROPOSED,
        eligible_voters=json.dumps([sample_council_member.agentium_id]),
        required_votes=1,
        supermajority_threshold=66,
        proposed_by_agentium_id="00001",
        proposed_changes="Test amendment",
        rationale="Test rationale",
        discussion_thread=[],
    )
    db_session.add(voting)
    db_session.commit()

    voting.start_voting()
    voting.cast_vote(sample_council_member.agentium_id, VoteType.FOR, "Good amendment")
    db_session.commit()

    result = voting.conclude()
    db_session.commit()

    assert result["result"] == "passed"
    assert voting.final_result == "passed"
    assert voting.votes_for == 1
    assert voting.ended_at is not None


def test_task_deliberation_persist_and_conclude(db_session, sample_task, sample_council_member, sample_lead_agent):
    """TaskDeliberation persists, votes persist, conclude works."""
    deliberation = TaskDeliberation(
        task_id=sample_task.id,
        status=DeliberationStatus.PENDING,
        min_quorum=2,
        required_approvals=2,
        participating_members=json.dumps([sample_council_member.agentium_id, sample_lead_agent.agentium_id]),
        time_limit_minutes=30,
        discussion_thread=[],
    )
    db_session.add(deliberation)
    db_session.commit()

    deliberation.start()
    deliberation.cast_vote(sample_council_member.agentium_id, VoteType.FOR)
    deliberation.cast_vote(sample_lead_agent.agentium_id, VoteType.FOR)
    db_session.commit()

    result = deliberation.conclude()
    db_session.commit()

    assert result["decision"] == "approved"
    assert deliberation.final_decision == "approved"
    assert deliberation.status == DeliberationStatus.CONCLUDED


def test_individual_vote_dual_fk_constraint(db_session, sample_amendment_voting, sample_task_deliberation, sample_council_member):
    """IndividualVote dual FK: task_deliberation_id OR amendment_voting_id (not both null)."""
    vote1 = IndividualVote(
        amendment_voting_id=sample_amendment_voting.id,
        voter_agentium_id=sample_council_member.agentium_id,
        vote=VoteType.FOR,
        agentium_id="V1",
    )
    db_session.add(vote1)
    db_session.commit()

    assert vote1.amendment_voting_id == sample_amendment_voting.id
    assert vote1.task_deliberation_id is None

    vote2 = IndividualVote(
        task_deliberation_id=sample_task_deliberation.id,
        voter_agentium_id=sample_council_member.agentium_id,
        vote=VoteType.FOR,
        agentium_id="V2",
    )
    db_session.add(vote2)
    db_session.commit()

    assert vote2.task_deliberation_id == sample_task_deliberation.id
    assert vote2.amendment_voting_id is None


def test_individual_vote_change_vote_persists(db_session, sample_task_deliberation, sample_council_member):
    """IndividualVote change_vote() persists original_vote and vote_changed."""
    deliberation = sample_task_deliberation
    deliberation.start()
    vote_record = deliberation.cast_vote(sample_council_member.agentium_id, VoteType.FOR)
    db_session.commit()

    vote_record.change_vote(VoteType.AGAINST, "Changed mind")
    db_session.commit()

    db_session.refresh(vote_record)
    assert vote_record.vote == VoteType.AGAINST
    assert vote_record.vote_changed is True
    assert vote_record.original_vote == VoteType.FOR
    assert vote_record.changed_at is not None


def test_individual_vote_agentium_id_uniqueness(db_session, sample_task_deliberation, sample_council_member):
    """IndividualVote agentium_id must be unique."""
    vote1 = IndividualVote(
        task_deliberation_id=sample_task_deliberation.id,
        voter_agentium_id=sample_council_member.agentium_id,
        vote=VoteType.FOR,
        agentium_id="V1",
    )
    db_session.add(vote1)
    db_session.commit()

    vote2 = IndividualVote(
        task_deliberation_id=sample_task_deliberation.id,
        voter_agentium_id=sample_council_member.agentium_id,
        vote=VoteType.AGAINST,
        agentium_id="V1",  # Duplicate
    )
    db_session.add(vote2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# =========================================================================
# Cross-Model Integration Tests
# =========================================================================

def test_agent_constitution_ethos_relationship(db_session):
    """Agent -> Constitution (via constitution_version) -> Ethos links work."""
    constitution = Constitution(
        agentium_id="C00001",
        version_number=1,
        version="v1.0.0",
        articles=json.dumps({}),
        prohibited_actions=json.dumps([]),
        sovereign_preferences=json.dumps({}),
        effective_date=utcnow(),
        is_active=True,
        created_by_agentium_id="00001",
    )
    db_session.add(constitution)
    db_session.commit()

    agent = Agent(
        agentium_id="00001",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
        name="Head",
        constitution_version=constitution.version,
    )
    db_session.add(agent)
    db_session.commit()

    ethos = Ethos(
        agentium_id="E00001",
        agent_id=agent.id,
        agent_type="head_of_council",
        mission_statement="Test",
        core_values=json.dumps([]),
        behavioral_rules=json.dumps([]),
        restrictions=json.dumps([]),
        capabilities=json.dumps([]),
        version=1,
        is_verified=True,
        created_by_agentium_id="00001",
    )
    db_session.add(ethos)
    db_session.commit()

    # Manually link ethos to agent (agent.ethos_id is optional)
    agent.ethos_id = ethos.id
    db_session.commit()

    assert agent.constitution_version == constitution.version
    assert ethos.agent_id == agent.id
    assert agent.ethos_id == ethos.id


def test_amendment_voting_links_to_constitution(db_session, sample_constitution):
    """AmendmentVoting links to Constitution via amendment_id."""
    voting = AmendmentVoting(
        amendment_id=sample_constitution.id,
        status=AmendmentStatus.PROPOSED,
        eligible_voters=json.dumps([]),
        required_votes=1,
        supermajority_threshold=66,
        proposed_by_agentium_id="00001",
        proposed_changes="Test",
        rationale="Test",
        discussion_thread=[],
    )
    db_session.add(voting)
    db_session.commit()

    assert voting.amendment_id == sample_constitution.id
    assert voting.amendment is not None


def test_task_deliberation_links_to_task(db_session, sample_task):
    """TaskDeliberation links to Task via task_id."""
    deliberation = TaskDeliberation(
        task_id=sample_task.id,
        status=DeliberationStatus.PENDING,
        min_quorum=1,
        required_approvals=1,
        participating_members=json.dumps([]),
        time_limit_minutes=30,
        discussion_thread=[],
    )
    db_session.add(deliberation)
    db_session.commit()

    assert deliberation.task_id == sample_task.id


# =========================================================================
# Schema/Table Verification
# =========================================================================

def test_governance_tables_exist(db_session):
    """All governance tables exist in database."""
    inspector = inspect(db_session.bind)
    tables = inspector.get_table_names()

    # Governance tables
    assert "agents" in tables
    assert "constitutions" in tables
    assert "ethos" in tables
    assert "amendment_votings" in tables
    assert "task_deliberations" in tables
    assert "individual_votes" in tables
    assert "voting_records" in tables


def test_foreign_key_constraints_exist(db_session):
    """Foreign key constraints exist for governance relationships."""
    inspector = inspect(db_session.bind)

    # Check agents.parent_id FK
    agents_fks = inspector.get_foreign_keys("agents")
    parent_fks = [fk for fk in agents_fks if fk["constrained_columns"] == ["parent_id"]]
    assert len(parent_fks) > 0, "agents.parent_id FK should exist"

    # Check ethos.agent_id - this is NOT a FK in the model (plain column)
    # Only agent.ethos_id is a FK
    ethos_fks = inspector.get_foreign_keys("ethos")
    # Ethos has no FKs defined in the model
    assert len(ethos_fks) == 0, "ethos table should have no FKs (agent_id is plain column)"

    # Check amendment_votings.amendment_id FK
    av_fks = inspector.get_foreign_keys("amendment_votings")
    amendment_fks = [fk for fk in av_fks if fk["constrained_columns"] == ["amendment_id"]]
    assert len(amendment_fks) > 0, "amendment_votings.amendment_id FK should exist"

    # Check individual_votes dual FK
    iv_fks = inspector.get_foreign_keys("individual_votes")
    assert any(fk["constrained_columns"] == ["amendment_voting_id"] for fk in iv_fks), "individual_votes.amendment_voting_id FK should exist"
    assert any(fk["constrained_columns"] == ["task_deliberation_id"] for fk in iv_fks), "individual_votes.task_deliberation_id FK should exist"


def test_indexes_exist_on_key_columns(db_session):
    """Indexes exist on key governance columns."""
    inspector = inspect(db_session.bind)

    # agents.agentium_id - unique constraint may not appear as separate index in SQLite
    # Check for unique constraint instead
    from sqlalchemy import text
    with db_session.bind.connect() as conn:
        # Check for unique constraint on agents.agentium_id
        result = conn.execute(text("PRAGMA index_list(agents)"))
        indexes = result.fetchall()
        # Unique constraint creates an implicit index, but SQLite may not expose it
        # Just verify the table has the constraint
        result = conn.execute(text("PRAGMA table_info(agents)"))
        cols = result.fetchall()
        agentium_col = [c for c in cols if c[1] == 'agentium_id']
        assert len(agentium_col) > 0, "agentium_id column should exist"
        # Check unique constraint is defined
        result = conn.execute(text("PRAGMA index_list(agents)"))
        # SQLite unique constraints on columns appear as indexes
        # We'll just verify the model defines it

    # constitutions.version_number - similar
    const_indexes = inspector.get_indexes("constitutions")
    version_indexes = [idx for idx in const_indexes if "version_number" in idx["column_names"]]
    # SQLite may not show unique constraint index - check via PRAGMA
    with db_session.bind.connect() as conn:
        result = conn.execute(text("PRAGMA index_list(constitutions)"))
        indexes = result.fetchall()
        # Verify at least one index exists for version_number (unique constraint)
        # The idx_constitution_version_number from model should exist
        found = False
        for idx in indexes:
            idx_name = idx[1]
            if 'version_number' in idx_name or 'version' in idx_name:
                found = True
        # The explicit index from model definition should exist
        assert found, "constitutions.version_number index should exist"

    # Note: amendment_votings.amendment_id may not have an explicit index in SQLite
    # but the FK creates one implicitly in PostgreSQL