import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from backend.models.database import Base
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.voting import AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord, VoteType


@pytest.fixture(scope="function")
def db_session():
    """In-memory SQLite session for fast unit tests."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _create_agent(db_session, agentium_id: str, agent_type: AgentType, status: AgentStatus = AgentStatus.ACTIVE, parent=None):
    """Helper to create agent with proper ID generation."""
    agent = Agent(
        agentium_id=agentium_id,
        agent_type=agent_type,
        status=status,
        name=f"Test {agent_type.value}",
    )
    if parent:
        agent.parent_id = parent.id
    db_session.add(agent)
    db_session.commit()
    db_session.refresh(agent)
    return agent


@pytest.fixture
def sample_head_of_council(db_session):
    """Agent with agentium_id='00001', HEAD_OF_COUNCIL type."""
    return _create_agent(db_session, "00001", AgentType.HEAD_OF_COUNCIL)


@pytest.fixture
def sample_council_member(db_session, sample_head_of_council):
    """Agent with agentium_id='10001', COUNCIL_MEMBER type, parent=head."""
    return _create_agent(db_session, "10001", AgentType.COUNCIL_MEMBER, parent=sample_head_of_council)


@pytest.fixture
def sample_lead_agent(db_session, sample_head_of_council):
    """Agent with agentium_id='20001', LEAD_AGENT type."""
    return _create_agent(db_session, "20001", AgentType.LEAD_AGENT, parent=sample_head_of_council)


@pytest.fixture
def sample_task_agent(db_session, sample_lead_agent):
    """Agent with agentium_id='30001', TASK_AGENT type."""
    return _create_agent(db_session, "30001", AgentType.TASK_AGENT, parent=sample_lead_agent)


@pytest.fixture
def sample_constitution(db_session):
    """Active Constitution with articles, prohibited_actions, sovereign_preferences."""
    constitution = Constitution(
        version_number=1,
        version_string="v1.0.0",
        articles_json={
            "article_1": {"title": "Sovereign Authority", "content": "The sovereign holds ultimate authority."},
            "article_2": {"title": "Council Governance", "content": "Council members govern by consensus."},
        },
        prohibited_actions_json=["unauthorized_tool_use", "constitution_modification"],
        sovereign_preferences_json={"theme": "dark", "notifications": True},
        effective_date=datetime.now(timezone.utc),
        is_active=True,
    )
    db_session.add(constitution)
    db_session.commit()
    db_session.refresh(constitution)
    return constitution


@pytest.fixture
def sample_ethos(db_session, sample_task_agent):
    """Ethos linked to agent with working memory populated."""
    from backend.models.entities.constitution import Ethos
    ethos = Ethos(
        agent_id=sample_task_agent.id,
        current_objective="Test objective",
        active_plan_json={"steps": ["step1", "step2"]},
        constitutional_references_json=["article_1", "article_2"],
        task_progress_markers_json={"step1": "completed"},
        reasoning_artifacts_json=[{"thought": "Initial reasoning"}],
        outcome_summary="Initial summary",
        lessons_learned_json=["Lesson 1: Test lesson"],
        version=1,
        verified=True,
    )
    db_session.add(ethos)
    db_session.commit()
    db_session.refresh(ethos)
    return ethos


@pytest.fixture
def sample_amendment_voting(db_session, sample_constitution, sample_council_member):
    """AmendmentVoting with council members as eligible voters."""
    from backend.models.entities.voting import AmendmentVoting
    voting = AmendmentVoting(
        amendment_id=sample_constitution.id,
        status="active",
        eligible_voter_ids=[sample_council_member.id],
        quorum_threshold=0.6,
        supermajority_threshold=0.66,
        discussion_thread_json=[],
    )
    db_session.add(voting)
    db_session.commit()
    db_session.refresh(voting)
    return voting


@pytest.fixture
def sample_task_deliberation(db_session, sample_council_member, sample_lead_agent, sample_task_agent):
    """TaskDeliberation with council members as participants."""
    from backend.models.entities.voting import TaskDeliberation
    deliberation = TaskDeliberation(
        task_id="test-task-id",
        status="active",
        min_quorum=2,
        required_approvals=2,
        participant_ids=[sample_council_member.id, sample_lead_agent.id, sample_task_agent.id],
    )
    db_session.add(deliberation)
    db_session.commit()
    db_session.refresh(deliberation)
    return deliberation