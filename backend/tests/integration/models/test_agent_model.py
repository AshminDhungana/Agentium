"""
Integration tests for Agent model (3.3.1).
Verifies all statuses (INITIALIZING, ACTIVE, SUSPENDED, TERMINATED, etc.) and agent types work correctly.
"""
import pytest
from datetime import datetime, timezone
from backend.models.entities.agents import Agent, AgentType, AgentStatus


def test_agent_all_statuses_persist(db_session):
    """Verify all AgentStatus values round-trip through the DB."""
    for idx, status in enumerate(AgentStatus):
        agentium_id = f"300{idx:02d}"
        agent = Agent(
            agentium_id=agentium_id,
            agent_type=AgentType.TASK_AGENT,
            status=status,
            name=f"Agent {status.value}",
        )
        db_session.add(agent)
    db_session.commit()

    for idx, status in enumerate(AgentStatus):
        agentium_id = f"300{idx:02d}"
        fetched = db_session.query(Agent).filter_by(agentium_id=agentium_id).first()
        assert fetched is not None
        assert fetched.status == status


def test_agent_status_transitions(db_session):
    """Verify state transition flow from INITIALIZING -> ACTIVE -> WORKING -> ACTIVE."""
    agent = Agent(
        agentium_id="30099",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.INITIALIZING,
        name="Transition Agent",
    )
    db_session.add(agent)
    db_session.commit()

    assert agent.status == AgentStatus.INITIALIZING

    # Transition to ACTIVE
    agent.status = AgentStatus.ACTIVE
    db_session.commit()
    fetched = db_session.query(Agent).filter_by(agentium_id="30099").first()
    assert fetched.status == AgentStatus.ACTIVE

    # Transition to WORKING
    agent.status = AgentStatus.WORKING
    agent.current_task_id = "task-uuid-123"
    db_session.commit()
    fetched = db_session.query(Agent).filter_by(agentium_id="30099").first()
    assert fetched.status == AgentStatus.WORKING
    assert fetched.current_task_id == "task-uuid-123"

    # Transition back to ACTIVE
    agent.status = AgentStatus.ACTIVE
    agent.current_task_id = None
    db_session.commit()
    fetched = db_session.query(Agent).filter_by(agentium_id="30099").first()
    assert fetched.status == AgentStatus.ACTIVE
    assert fetched.current_task_id is None


def test_agent_suspended_and_terminated(db_session):
    """Verify SUSPENDED and TERMINATED status behavior and metadata."""
    agent = Agent(
        agentium_id="30088",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.SUSPENDED,
        name="Suspended Agent",
    )
    db_session.add(agent)
    db_session.commit()

    assert agent.status == AgentStatus.SUSPENDED

    # Terminate agent
    now = datetime.now(timezone.utc)
    agent.status = AgentStatus.TERMINATED
    agent.terminated_at = now
    agent.termination_reason = "Constitution violation breach"
    db_session.commit()

    fetched = db_session.query(Agent).filter_by(agentium_id="30088").first()
    assert fetched.status == AgentStatus.TERMINATED
    assert fetched.terminated_at is not None
    assert fetched.termination_reason == "Constitution violation breach"


def test_agent_idle_working_status(db_session):
    """Verify persistent agent idle statuses (IDLE_WORKING, IDLE_PAUSED)."""
    persistent_agent = Agent(
        agentium_id="30077",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.IDLE_WORKING,
        name="Persistent Optimizer",
        is_persistent=True,
        idle_mode_enabled=True,
        persistent_role="system_optimizer",
    )
    db_session.add(persistent_agent)
    db_session.commit()

    fetched = db_session.query(Agent).filter_by(agentium_id="30077").first()
    assert fetched.is_persistent is True
    assert fetched.idle_mode_enabled is True
    assert fetched.status == AgentStatus.IDLE_WORKING

    # Pause idle mode
    fetched.status = AgentStatus.IDLE_PAUSED
    db_session.commit()
    refetched = db_session.query(Agent).filter_by(agentium_id="30077").first()
    assert refetched.status == AgentStatus.IDLE_PAUSED


def test_agent_polymorphic_types(db_session):
    """Verify all 7 AgentType values round-trip."""
    types_to_ids = {
        AgentType.HEAD_OF_COUNCIL: "00002",
        AgentType.COUNCIL_MEMBER: "10002",
        AgentType.LEAD_AGENT: "20002",
        AgentType.TASK_AGENT: "30002",
        AgentType.CODE_CRITIC: "70002",
        AgentType.OUTPUT_CRITIC: "80002",
        AgentType.PLAN_CRITIC: "90002",
    }
    for agent_type, agentium_id in types_to_ids.items():
        agent = Agent(
            agentium_id=agentium_id,
            agent_type=agent_type,
            status=AgentStatus.ACTIVE,
            name=f"Test {agent_type.value}",
        )
        db_session.add(agent)
    db_session.commit()

    for agent_type, agentium_id in types_to_ids.items():
        fetched = db_session.query(Agent).filter_by(agentium_id=agentium_id).first()
        assert fetched is not None
        assert fetched.agent_type == agent_type


def test_agent_agentium_id_validation(monkeypatch):
    """Verify validate_agentium_id_format raises ValueError for invalid formats when testing mode allows."""
    monkeypatch.setenv("TESTING", "false")
    agent = Agent()

    # Digits out of range or non-digit
    with pytest.raises(ValueError, match="must start with 0-9"):
        agent.validate_agentium_id_format("agentium_id", "ABCDE")  # non digit

    with pytest.raises(ValueError, match="between 5 and 8 digits"):
        agent.validate_agentium_id_format("agentium_id", "12")  # too short (< 5)

    with pytest.raises(ValueError, match="must start with 0-9"):
        agent.validate_agentium_id_format("agentium_id", "X12345")  # invalid prefix


def test_agent_parent_child_hierarchy(db_session, sample_head_of_council):
    """Verify parent/child hierarchy traversal."""
    lead = Agent(
        agentium_id="20099",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        name="Lead Agent",
        parent_id=sample_head_of_council.id,
    )
    db_session.add(lead)
    db_session.commit()

    worker = Agent(
        agentium_id="30098",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        name="Worker Agent",
        parent_id=lead.id,
    )
    db_session.add(worker)
    db_session.commit()

    db_session.refresh(sample_head_of_council)
    db_session.refresh(lead)

    assert lead.parent.id == sample_head_of_council.id
    assert worker.parent.id == lead.id
    assert lead in sample_head_of_council.subordinates
    assert worker in lead.subordinates
