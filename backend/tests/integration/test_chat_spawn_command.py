"""
Integration tests for authority-aware GovernanceCommandService execution.

These require a running postgres + redis + chromadb stack (docker-compose.test).
They are marked `integration` and use the `seeded_db` fixture (genesis protocol).
"""

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    AgentType,
    LeadAgent,
    HeadOfCouncil,
    CouncilMember,
)
from backend.models.entities.audit import AuditLog, AuditCategory
from backend.models.entities.task import Task
from backend.services.reincarnation_service import reincarnation_service
from backend.services.governance_command_service import GovernanceCommandService
from backend.services.agent_orchestrator import AgentOrchestrator

pytestmark = pytest.mark.integration


@pytest.mark.asyncio
async def test_head_spawns_task_agent(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None

    cmd = GovernanceCommandService.detect_command("spawn a task agent named Scout")
    assert cmd is not None and cmd.kind == "spawn_task_agent"

    result = GovernanceCommandService.execute(cmd, head, seeded_db)
    assert result["action"] == "spawn_task_agent"

    agent = seeded_db.query(Agent).filter_by(agentium_id=result["agentium_id"]).first()
    assert agent is not None
    assert agent.agent_type == AgentType.TASK_AGENT


@pytest.mark.asyncio
async def test_council_spawns_lead_agent(seeded_db: Session):
    council = seeded_db.query(CouncilMember).first()
    assert council is not None

    cmd = GovernanceCommandService.detect_command("spawn a lead agent named Ops")
    assert cmd is not None and cmd.kind == "spawn_lead_agent"

    result = GovernanceCommandService.execute(cmd, council, seeded_db)
    assert result["action"] == "spawn_lead_agent"

    lead = seeded_db.query(Agent).filter_by(agentium_id=result["agentium_id"]).first()
    assert isinstance(lead, LeadAgent)

    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert lead.parent_id == head.id


@pytest.mark.asyncio
async def test_lead_spawns_task_agent_under_itself(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    lead = reincarnation_service.spawn_lead_agent(
        parent=head,
        name="Delegating Lead",
        description="Lead for task-agent spawning test.",
        db=seeded_db,
    )
    seeded_db.commit()

    cmd = GovernanceCommandService.detect_command("spawn a task agent named W")
    assert cmd is not None and cmd.kind == "spawn_task_agent"

    result = GovernanceCommandService.execute(cmd, lead, seeded_db)
    assert result["action"] == "spawn_task_agent"

    agent = seeded_db.query(Agent).filter_by(agentium_id=result["agentium_id"]).first()
    assert agent is not None
    assert agent.parent_id == lead.id


@pytest.mark.asyncio
async def test_task_agent_cannot_spawn(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    lead = reincarnation_service.spawn_lead_agent(
        parent=head,
        name="Lead For Denial Test",
        description="Lead used to spawn a task agent that must be denied.",
        db=seeded_db,
    )
    seeded_db.commit()

    task_agent = reincarnation_service.spawn_task_agent(
        parent=lead,
        name="Powerless Worker",
        description="Task agent without spawn authority.",
        capabilities=None,
        db=seeded_db,
    )
    seeded_db.commit()

    cmd = GovernanceCommandService.detect_command("spawn a task agent named X")
    assert cmd is not None and cmd.kind == "spawn_task_agent"

    with pytest.raises(PermissionError):
        GovernanceCommandService.execute(cmd, task_agent, seeded_db)


@pytest.mark.asyncio
async def test_create_task_allowed_for_any(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

    cmd = GovernanceCommandService.detect_command("create a task: write runbook")
    assert cmd is not None and cmd.kind == "create_task"

    result = GovernanceCommandService.execute(cmd, head, seeded_db)
    assert result["action"] == "create_task"

    task = seeded_db.query(Task).filter_by(agentium_id=result["task_id"]).first()
    assert task is not None


@pytest.mark.asyncio
async def test_spawn_audit_log_written(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

    cmd = GovernanceCommandService.detect_command("spawn a task agent named Audited")
    result = GovernanceCommandService.execute(cmd, head, seeded_db)

    audit = seeded_db.query(AuditLog).filter(
        AuditLog.action == "agent_spawned",
        AuditLog.target_id == result["agentium_id"],
    ).first()
    assert audit is not None
    assert audit.category == AuditCategory.GOVERNANCE


from backend.services.chat_service import ChatService


@pytest.mark.asyncio
async def test_chat_process_message_spawns_without_llm(seeded_db):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    result = await ChatService.process_message(head, "spawn a task agent named Scout", seeded_db)
    assert result["model"] == "governance-command"
    assert result["agent_spawned"] is not None
    agent = seeded_db.query(Agent).filter_by(agentium_id=result["agent_spawned"]).first()
    assert agent.agent_type == AgentType.TASK_AGENT


@pytest.mark.asyncio
async def test_process_intent_executes_directive_for_lead(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    lead = reincarnation_service.spawn_lead_agent(parent=head, name="L", description="x", db=seeded_db)
    seeded_db.commit()

    orch = AgentOrchestrator(db=seeded_db)
    result = await orch.process_intent(
        raw_input="spawn a task agent named ViaOrchestrator",
        source_id=lead.agentium_id,
    )
    assert result.success is True
    assert result.metadata["action"] == "spawn_task_agent"
    agent = seeded_db.query(Agent).filter_by(agentium_id=result.metadata["agentium_id"]).first()
    assert agent.parent_id == lead.id


@pytest.mark.asyncio
async def test_process_intent_denies_task_agent_directive(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    lead = reincarnation_service.spawn_lead_agent(parent=head, name="L", description="x", db=seeded_db)
    seeded_db.commit()
    task_agent = reincarnation_service.spawn_task_agent(parent=lead, name="T", description="x", db=seeded_db)
    seeded_db.commit()

    orch = AgentOrchestrator(db=seeded_db)
    result = await orch.process_intent(
        raw_input="spawn a task agent named Nope",
        source_id=task_agent.agentium_id,
    )
    assert not (result.success and result.metadata.get("action") == "spawn_task_agent")
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    before = seeded_db.query(Agent).count()
    try:
        await ChatService.process_message(head, "hello there", seeded_db)
    except Exception:
        pass
    assert seeded_db.query(Agent).count() == before
