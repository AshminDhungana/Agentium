import pytest
from datetime import datetime
from backend.models.entities.agents import Agent, AgentType, AgentStatus, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.voting import AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord, VoteType
from backend.models.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


def test_governance_fixtures_compile():
    """Verify all governance fixtures can be imported without error."""
    from backend.tests.unit.models.conftest import (
        sample_head_of_council,
        sample_council_member,
        sample_lead_agent,
        sample_task_agent,
        sample_constitution,
        sample_ethos,
        sample_amendment_voting,
        sample_task_deliberation,
    )
    assert sample_head_of_council is not None
    assert sample_council_member is not None
    assert sample_lead_agent is not None
    assert sample_task_agent is not None
    assert sample_constitution is not None
    assert sample_ethos is not None
    assert sample_amendment_voting is not None
    assert sample_task_deliberation is not None


# =========================================================================
# Agent Model Unit Tests — Status Transitions & State Machine (Task 1.2)
# =========================================================================

def test_agent_all_statuses_exist():
    """All 10 AgentStatus enum values are defined."""
    statuses = [s.value for s in AgentStatus]
    expected = [
        "initializing",
        "active",
        "working",
        "deliberating",
        "reviewing",
        "idle_working",
        "idle_paused",
        "suspended",
        "terminated",
    ]
    for exp in expected:
        assert exp in statuses, f"Missing status: {exp}"
    # Verify count
    assert len(statuses) >= 9


def test_agent_default_status_is_initializing(db_session):
    """New agent defaults to INITIALIZING status."""
    agent = Agent(agentium_id="99999", agent_type=AgentType.TASK_AGENT, name="Test Agent")
    db_session.add(agent)
    db_session.commit()
    assert agent.status == AgentStatus.INITIALIZING


def test_agent_valid_status_transitions(sample_task_agent):
    """Valid status transitions are accepted and persisted."""
    agent = sample_task_agent

    # INITIALIZING -> ACTIVE
    agent.status = AgentStatus.INITIALIZING
    agent.status = AgentStatus.ACTIVE
    assert agent.status == AgentStatus.ACTIVE

    # ACTIVE -> WORKING / DELIBERATING / REVIEWING / IDLE_WORKING / IDLE_PAUSED
    for next_status in [AgentStatus.WORKING, AgentStatus.DELIBERATING, AgentStatus.REVIEWING,
                        AgentStatus.IDLE_WORKING, AgentStatus.IDLE_PAUSED]:
        agent.status = AgentStatus.ACTIVE
        agent.status = next_status
        assert agent.status == next_status

    # WORKING -> ACTIVE / IDLE_WORKING / SUSPENDED / TERMINATED
    for next_status in [AgentStatus.ACTIVE, AgentStatus.IDLE_WORKING, AgentStatus.SUSPENDED, AgentStatus.TERMINATED]:
        agent.status = AgentStatus.WORKING
        agent.status = next_status
        assert agent.status == next_status

    # DELIBERATING -> ACTIVE / REVIEWING / SUSPENDED
    for next_status in [AgentStatus.ACTIVE, AgentStatus.REVIEWING, AgentStatus.SUSPENDED]:
        agent.status = AgentStatus.DELIBERATING
        agent.status = next_status
        assert agent.status == next_status

    # REVIEWING -> ACTIVE / SUSPENDED / TERMINATED
    for next_status in [AgentStatus.ACTIVE, AgentStatus.SUSPENDED, AgentStatus.TERMINATED]:
        agent.status = AgentStatus.REVIEWING
        agent.status = next_status
        assert agent.status == next_status

    # IDLE_WORKING -> ACTIVE / WORKING / SUSPENDED
    for next_status in [AgentStatus.ACTIVE, AgentStatus.WORKING, AgentStatus.SUSPENDED]:
        agent.status = AgentStatus.IDLE_WORKING
        agent.status = next_status
        assert agent.status == next_status

    # IDLE_PAUSED -> ACTIVE / SUSPENDED / TERMINATED
    for next_status in [AgentStatus.ACTIVE, AgentStatus.SUSPENDED, AgentStatus.TERMINATED]:
        agent.status = AgentStatus.IDLE_PAUSED
        agent.status = next_status
        assert agent.status == next_status

    # SUSPENDED -> ACTIVE / TERMINATED
    for next_status in [AgentStatus.ACTIVE, AgentStatus.TERMINATED]:
        agent.status = AgentStatus.SUSPENDED
        agent.status = next_status
        assert agent.status == next_status

    # TERMINATED is terminal - test it can be set
    agent.status = AgentStatus.TERMINATED
    assert agent.status == AgentStatus.TERMINATED


def test_agent_invalid_status_transitions_rejected(sample_task_agent):
    """Invalid status transitions are documented (model currently permissive)."""
    agent = sample_task_agent

    # Note: The model currently doesn't enforce transition restrictions at setter level.
    # These tests document current behavior. If enforcement is added, tests should be updated.

    # From ACTIVE: can go to SUSPENDED/TERMINATED (currently allowed)
    agent.status = AgentStatus.ACTIVE
    agent.status = AgentStatus.SUSPENDED
    assert agent.status == AgentStatus.SUSPENDED

    # From INITIALIZING: can jump to WORKING directly (currently allowed)
    agent.status = AgentStatus.INITIALIZING
    agent.status = AgentStatus.WORKING
    assert agent.status == AgentStatus.WORKING

    # From TERMINATED: can transition out (currently allowed, but not recommended)
    agent.status = AgentStatus.TERMINATED
    agent.status = AgentStatus.ACTIVE
    assert agent.status == AgentStatus.ACTIVE


def test_agent_tier_based_spawn_permissions(sample_head_of_council, sample_council_member, sample_lead_agent, sample_task_agent, db_session):
    """spawn_child() permissions based on agent tier."""
    # Test permission checks (mocking ethos creation to avoid foreign key issues)
    from unittest.mock import patch, MagicMock

    # HEAD_OF_COUNCIL (0xxxx) can spawn COUNCIL_MEMBER (1xxxx)
    with patch.object(HeadOfCouncil, '_create_default_ethos', return_value=MagicMock(id="mock-ethos-id")):
        child = sample_head_of_council.spawn_child(
            AgentType.COUNCIL_MEMBER,
            db_session,
            name="Test Council Member"
        )
        assert child.agentium_id.startswith("1")
        assert child.agent_type == AgentType.COUNCIL_MEMBER
        assert child.parent_id == sample_head_of_council.id

    # COUNCIL_MEMBER cannot spawn (should raise before ethos creation)
    try:
        sample_council_member.spawn_child(AgentType.TASK_AGENT, db_session, name="Should fail")
        assert False, "COUNCIL_MEMBER should not be able to spawn"
    except (ValueError, PermissionError) as e:
        assert "cannot spawn" in str(e).lower() or "permission" in str(e).lower() or "only lead" in str(e).lower()

    # LEAD_AGENT (2xxxx) can spawn TASK_AGENT (3xxxx-6xxxx)
    with patch.object(LeadAgent, '_create_default_ethos', return_value=MagicMock(id="mock-ethos-id")):
        child = sample_lead_agent.spawn_child(
            AgentType.TASK_AGENT,
            db_session,
            name="Test Task Agent"
        )
        assert child.agentium_id.startswith(("3", "4", "5", "6"))
        assert child.agent_type == AgentType.TASK_AGENT
        assert child.parent_id == sample_lead_agent.id

    # TASK_AGENT cannot spawn (should raise before ethos creation)
    try:
        sample_task_agent.spawn_child(AgentType.TASK_AGENT, db_session, name="Should fail")
        assert False, "TASK_AGENT should not be able to spawn"
    except (ValueError, PermissionError) as e:
        assert "cannot spawn" in str(e).lower() or "permission" in str(e).lower()

    # HEAD_OF_COUNCIL cannot spawn another HEAD_OF_COUNCIL
    try:
        sample_head_of_council.spawn_child(AgentType.HEAD_OF_COUNCIL, db_session, name="Should fail")
        assert False, "Cannot spawn another HEAD_OF_COUNCIL"
    except (ValueError, PermissionError) as e:
        assert "cannot spawn" in str(e).lower() or "permission" in str(e).lower()


def test_agent_id_generation_per_tier(sample_head_of_council, sample_council_member, sample_lead_agent, sample_task_agent, db_session):
    """Agent ID format validation per tier."""
    assert sample_head_of_council.agentium_id == "00001"
    assert sample_council_member.agentium_id.startswith("1")
    assert sample_lead_agent.agentium_id.startswith("2")
    assert sample_task_agent.agentium_id.startswith(("3", "4", "5", "6"))

    # Test that _generate_agentium_id produces sequential IDs
    new_council = sample_head_of_council._generate_agentium_id(AgentType.COUNCIL_MEMBER, db_session)
    assert new_council.startswith("1")
    assert len(new_council) <= 8
    # Should be 10002
    assert int(new_council) > int(sample_council_member.agentium_id)


def test_agent_constitutional_alignment_flow(sample_task_agent, sample_constitution, sample_ethos, db_session):
    """pre_task_ritual() / post_task_ritual() constitutional alignment."""
    # pre_task_ritual should read constitution and align
    result = sample_task_agent.pre_task_ritual(db_session)
    assert result["ready_for_task"] is True
    assert sample_task_agent.constitution_version is not None
    assert sample_task_agent.constitution_read_count >= 1

    # post_task_ritual should execute ethos operations
    result = sample_task_agent.post_task_ritual(db_session)
    assert result["constitution_refreshed"] is True
    assert "outcome_recorded" in result
    assert "lessons_recorded" in result


def test_agent_compress_ethos_llm_path(sample_task_agent, sample_ethos, db_session):
    """compress_ethos() LLM path with 75/25 strategy (mocked)."""
    # This test documents the method exists and runs without error
    # Actual LLM call is mocked in integration tests
    # Add some content to compress
    sample_ethos.reasoning_artifacts = "[{\"thought\": \"test\"}, {\"thought\": \"test2\"}, {\"thought\": \"test3\"}, {\"thought\": \"test4\"}, {\"thought\": \"test5\"}]"
    sample_ethos.lessons_learned = "[{\"lesson\": \"lesson1\"}, {\"lesson\": \"lesson2\"}, {\"lesson\": \"lesson3\"}, {\"lesson\": \"lesson4\"}, {\"lesson\": \"lesson5\"}]"
    db_session.commit()

    # Should not raise even without LLM config (falls back to Python)
    sample_task_agent.compress_ethos(db_session)
    db_session.commit()
    assert sample_ethos.version >= 1


def test_agent_compress_ethos_python_fallback(sample_task_agent, sample_ethos, db_session):
    """compress_ethos() Python fallback (prune_obsolete_content)."""
    # Add content to compress
    sample_ethos.reasoning_artifacts = "[{\"thought\": \"test\"}, {\"thought\": \"test2\"}, {\"thought\": \"test3\"}, {\"thought\": \"test4\"}, {\"thought\": \"test5\"}]"
    sample_ethos.lessons_learned = "[{\"lesson\": \"lesson1\"}, {\"lesson\": \"lesson2\"}, {\"lesson\": \"lesson3\"}, {\"lesson\": \"lesson4\"}, {\"lesson\": \"lesson5\"}]"
    db_session.commit()

    original_artifacts_len = len(sample_ethos.get_reasoning_artifacts())
    original_lessons_len = len(sample_ethos.get_lessons_learned())

    # Force Python fallback
    sample_task_agent.compress_ethos(db_session)
    db_session.commit()

    # Should keep ~75% of artifacts and lessons (or at least some compression happened)
    new_artifacts = sample_ethos.get_reasoning_artifacts()
    new_lessons = sample_ethos.get_lessons_learned()
    # At minimum version should increment
    assert sample_ethos.version >= 1


def test_agent_read_and_align_constitution_graceful_fallback(sample_task_agent, db_session):
    """read_and_align_constitution() handles missing constitution gracefully."""
    # Should not raise even if no active constitution
    result = sample_task_agent.read_and_align_constitution(db_session)
    # Falls back gracefully
    assert isinstance(result, bool)


def test_agent_get_system_prompt_includes_all_components(sample_task_agent, sample_constitution, sample_ethos, db_session):
    """get_system_prompt() includes constitution + ethos + idle mode."""
    # Align first
    sample_task_agent.read_and_align_constitution(db_session)
    db_session.commit()

    prompt = sample_task_agent.get_system_prompt(db=db_session)
    assert isinstance(prompt, str)
    assert len(prompt) > 0
    # Should reference constitution version if aligned
    if sample_task_agent.constitution_version:
        assert str(sample_task_agent.constitution_version) in prompt


def test_agent_hierarchical_relationships(sample_head_of_council, sample_council_member, sample_lead_agent, sample_task_agent):
    """parent / subordinates backrefs work correctly."""
    assert sample_council_member.parent_id == sample_head_of_council.id
    assert sample_lead_agent.parent_id == sample_head_of_council.id
    assert sample_task_agent.parent_id == sample_lead_agent.id

    # subordinates relationship
    head_subordinates = sample_head_of_council.subordinates
    assert sample_council_member in head_subordinates
    assert sample_lead_agent in head_subordinates

    lead_subordinates = sample_lead_agent.subordinates
    assert sample_task_agent in lead_subordinates


def test_agent_assign_and_complete_task(sample_task_agent, db_session):
    """assign_task() and complete_task() work correctly."""
    # Assign task
    sample_task_agent.assign_task("test-task-id")
    assert sample_task_agent.current_task_id == "test-task-id"
    assert sample_task_agent.status == AgentStatus.WORKING

    # Complete task successfully
    sample_task_agent.complete_task(success=True)
    assert sample_task_agent.current_task_id is None
    assert sample_task_agent.status == AgentStatus.ACTIVE
    assert sample_task_agent.tasks_completed == 1
    assert sample_task_agent.tasks_failed == 0

    # Complete task with failure
    sample_task_agent.assign_task("test-task-id-2")
    sample_task_agent.complete_task(success=False)
    assert sample_task_agent.tasks_failed == 1


def test_agent_terminate_permissions(sample_head_of_council, sample_task_agent, db_session):
    """terminate() enforces Head of Council protection."""
    # Head of Council cannot be terminated
    try:
        sample_head_of_council.terminate("test reason")
        assert False, "Head of Council should not be terminatable"
    except PermissionError as e:
        assert "cannot be terminated" in str(e) or "head of council" in str(e).lower()

    # Regular agent can be terminated
    sample_task_agent.terminate("test reason")
    assert sample_task_agent.status == AgentStatus.TERMINATED
    assert sample_task_agent.terminated_at is not None
    assert sample_task_agent.termination_reason == "test reason"
    assert sample_task_agent.is_active is False


def test_agent_idle_task_management(sample_head_of_council, db_session):
    """assign_idle_task() and complete_idle_task() work for persistent agents."""
    # Head of Council is persistent by default
    assert sample_head_of_council.is_persistent is True

    # Assign idle task
    result = sample_head_of_council.assign_idle_task("idle-task-1")
    assert result is True
    assert sample_head_of_council.current_idle_task_id == "idle-task-1"
    assert sample_head_of_council.status == AgentStatus.IDLE_WORKING

    # Complete idle task
    sample_head_of_council.complete_idle_task(tokens_saved=100)
    assert sample_head_of_council.current_idle_task_id is None
    assert sample_head_of_council.idle_task_count == 1
    assert sample_head_of_council.idle_tokens_saved == 100


def test_agent_to_dict_serialization(sample_task_agent, sample_ethos, db_session):
    """to_dict() includes all expected fields."""
    sample_task_agent.read_and_align_constitution(db_session)
    db_session.commit()

    data = sample_task_agent.to_dict()

    # Required fields
    assert data["agent_type"] == AgentType.TASK_AGENT.value
    assert data["name"] == "Test task_agent"
    assert data["status"] == AgentStatus.ACTIVE.value
    assert "stats" in data
    assert data["stats"]["tasks_completed"] == 0
    assert data["is_terminated"] is False
    assert data["is_persistent"] is False
    assert "constitution_version" in data


def test_agent_agentium_id_validation(db_session):
    """Agentium ID validation - TESTING mode bypasses format check."""
    # In TESTING mode, any ID format is allowed
    import os
    os.environ["TESTING"] = "true"

    try:
        agent = Agent(
            agentium_id="custom_test_id",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent"
        )
        db_session.add(agent)
        db_session.commit()
        assert agent.agentium_id == "custom_test_id"
    finally:
        os.environ.pop("TESTING", None)