import pytest
from datetime import datetime, timezone
from sqlalchemy import create_engine, JSON
from sqlalchemy.orm import sessionmaker

# CRITICAL: Patch JSONB in postgresql dialect BEFORE any model imports
# This ensures any model importing JSONB gets the SQLite-compatible version
import sqlalchemy.dialects.postgresql as pg_dialect
pg_dialect.JSONB = lambda **kwargs: JSON(**kwargs)
# Also patch the class to be instantiable
class _JSONBCompat(JSON):
    pass
pg_dialect.JSONB = _JSONBCompat

# Also patch the imported name in task module when it loads
import sys
original_import = sys.modules.copy()

from backend.models.database import Base
from backend.models.entities.agents import (
    Agent, AgentType, AgentStatus,
    HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent
)
from backend.models.entities.constitution import Constitution, Ethos
from backend.models.entities.voting import AmendmentVoting, TaskDeliberation, IndividualVote, VotingRecord, VoteType
from sqlalchemy import event as sa_event


AGENT_CLASS_MAP = {
    AgentType.HEAD_OF_COUNCIL: HeadOfCouncil,
    AgentType.COUNCIL_MEMBER: CouncilMember,
    AgentType.LEAD_AGENT: LeadAgent,
    AgentType.TASK_AGENT: TaskAgent,
}


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
    """Helper to create agent with proper ID generation using correct subclass."""
    agent_class = AGENT_CLASS_MAP.get(agent_type, Agent)
    agent = agent_class(
        agentium_id=agentium_id,
        agent_type=agent_type,
        status=status,
        name=f"Test {agent_type.value}",
    )
    if parent:
        agent.parent_id = parent.id
    db_session.add(agent)
    db_session.flush()
    # Force id generation for polymorphic subclasses
    db_session.refresh(agent)
    return agent


# Ensure agent IDs are generated before commit for polymorphic classes
@sa_event.listens_for(Agent, 'before_insert')
def ensure_agent_id(mapper, connection, target):
    if target.id is None:
        import uuid
        target.id = str(uuid.uuid4())


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
    import json
    constitution = Constitution(
        agentium_id="C00001",
        version_number=1,
        version="v1.0.0",
        articles=json.dumps({
            "article_1": {"title": "Sovereign Authority", "content": "The sovereign holds ultimate authority."},
            "article_2": {"title": "Council Governance", "content": "Council members govern by consensus."},
        }),
        prohibited_actions=json.dumps(["unauthorized_tool_use", "constitution_modification"]),
        sovereign_preferences=json.dumps({"theme": "dark", "notifications": True}),
        effective_date=datetime.now(timezone.utc),
        is_active=True,
        created_by_agentium_id="00001",
    )
    db_session.add(constitution)
    db_session.commit()
    db_session.refresh(constitution)
    return constitution


@pytest.fixture
def sample_ethos(db_session, sample_task_agent):
    """Ethos linked to agent with working memory populated."""
    from backend.models.entities.constitution import Ethos
    import json
    ethos = Ethos(
        agentium_id=f"E{sample_task_agent.agentium_id[1:]}",  # E + rest of agent id
        agent_id=sample_task_agent.id,
        agent_type=sample_task_agent.agent_type.value,
        mission_statement="Test mission",
        core_values=json.dumps([]),
        behavioral_rules=json.dumps([]),
        restrictions=json.dumps([]),
        capabilities=json.dumps([]),
        current_objective="Test objective",
        active_plan=json.dumps({"steps": ["step1", "step2"]}),
        constitutional_references=json.dumps([]),
        task_progress_markers=json.dumps({"step1": "completed"}),
        reasoning_artifacts=json.dumps([{"thought": "Initial reasoning"}]),
        outcome_summary="Initial summary",
        lessons_learned=json.dumps(["Lesson 1: Test lesson"]),
        version=1,
        is_verified=True,
        created_by_agentium_id=sample_task_agent.agentium_id,
        working_method="Test working method",
        environment_context="Test environment",
    )
    db_session.add(ethos)
    db_session.commit()
    db_session.refresh(ethos)
    # Link ethos to agent
    sample_task_agent.ethos_id = ethos.id
    db_session.commit()
    return ethos


@pytest.fixture
def sample_amendment_voting(db_session, sample_constitution, sample_council_member):
    """AmendmentVoting with council members as eligible voters."""
    from backend.models.entities.voting import AmendmentVoting, AmendmentStatus
    import json
    voting = AmendmentVoting(
        amendment_id=sample_constitution.id,
        status=AmendmentStatus.PROPOSED,
        eligible_voters=json.dumps([sample_council_member.agentium_id]),
        required_votes=3,
        supermajority_threshold=66,
        proposed_by_agentium_id="00001",
        proposed_changes="Test amendment",
        rationale="Test rationale",
        discussion_thread=[],
    )
    db_session.add(voting)
    db_session.commit()
    db_session.refresh(voting)
    return voting


@pytest.fixture
def sample_task_deliberation(db_session, sample_council_member, sample_lead_agent, sample_task_agent):
    """TaskDeliberation with council members as participants."""
    from backend.models.entities.voting import TaskDeliberation, DeliberationStatus
    import json
    deliberation = TaskDeliberation(
        task_id="test-task-id",
        status=DeliberationStatus.PENDING,
        min_quorum=2,
        required_approvals=2,
        participating_members=json.dumps([sample_council_member.agentium_id, sample_lead_agent.agentium_id, sample_task_agent.agentium_id]),
        time_limit_minutes=30,
        discussion_thread=[],
    )
    db_session.add(deliberation)
    db_session.commit()
    db_session.refresh(deliberation)
    return deliberation