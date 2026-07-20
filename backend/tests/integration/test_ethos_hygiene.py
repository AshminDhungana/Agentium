"""
Ethos Hygiene (audit spec workstream D4) — integration test.

Verifies that liquidating an agent removes its linked Ethos row from
PostgreSQL, leaving no orphaned working-memory record behind.
"""

import json

from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.constitution import Ethos
from backend.services.reincarnation_service import ReincarnationService


def _make_agent_with_ethos(db_session):
    agent = Agent(
        agentium_id="30001",
        name="Hygiene Test Task Agent",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
    )
    db_session.add(agent)
    db_session.flush()

    ethos = Ethos(
        agentium_id="E30001",
        agent_id=agent.id,
        agent_type="task_agent",
        mission_statement="Execute assigned tasks constitutionally.",
        core_values=json.dumps([]),
        behavioral_rules=json.dumps([]),
        restrictions=json.dumps([]),
        capabilities=json.dumps(["execute_task"]),
        created_by_agentium_id="00001",
    )
    db_session.add(ethos)
    db_session.flush()
    agent.ethos_id = ethos.id
    db_session.commit()
    return agent


def test_liquidation_deletes_linked_ethos(db_session):
    agent = _make_agent_with_ethos(db_session)

    # Sanity: Ethos exists and is linked before liquidation.
    assert db_session.query(Ethos).filter_by(agentium_id="E30001").first() is not None
    assert agent.ethos_id is not None

    liquidator = Agent(
        agentium_id="00001",
        name="Liquidator",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
    )

    summary = ReincarnationService.liquidate_agent(
        "30001", liquidator, "ethos hygiene test", db_session, force=True
    )

    # Ethos row must be gone — no orphan left behind.
    assert db_session.query(Ethos).filter_by(agentium_id="E30001").first() is None
    assert summary.get("ethos_deleted") is True

    # The agent's FK pointer is detached.
    db_session.refresh(agent)
    assert agent.ethos_id is None
    assert agent.status == AgentStatus.TERMINATED
