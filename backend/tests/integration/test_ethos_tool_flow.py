# backend/tests/integration/test_ethos_tool_flow.py
import pytest
from sqlalchemy.orm import Session
from backend.core.tool_registry import tool_registry
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.constitution import Ethos
from backend.tools.ethos_tool import _load_ethos


def _seed(db, agentium_id, ethos_id_suffix):
    agent = Agent(
        agentium_id=agentium_id,
        agent_type=AgentType.TASK_AGENT,
        name=f"Agent {agentium_id}",
        status=AgentStatus.ACTIVE,
    )
    db.add(agent)
    db.flush()
    ethos = Ethos(
        agentium_id=f"E{ethos_id_suffix}",
        agent_type="task_agent",
        mission_statement="x",
        core_values="[]",
        behavioral_rules="[]",
        restrictions="[]",
        capabilities="[]",
        created_by_agentium_id="00001",
        agent_id=agent.id,
    )
    db.add(ethos)
    db.flush()
    agent.ethos_id = ethos.id
    db.flush()
    return agent


@pytest.mark.asyncio
async def test_task_agent_full_flow(db_session):
    _seed(db_session, "30001", "30001")
    r = await tool_registry.execute_tool_async("ethos", action="read", db=db_session, agent_id="30001")
    assert r["success"] is True
    r = await tool_registry.execute_tool_async("ethos", action="append", kind="lesson",
                                              payload={"key_point": "keep it idempotent"},
                                              db=db_session, agent_id="30001")
    assert r["success"] is True
    r = await tool_registry.execute_tool_async("ethos", action="compress",
                                              db=db_session, agent_id="30001")
    assert r["success"] is True
    r = await tool_registry.execute_tool_async("ethos", action="edit_identity",
                                              patch={"restrictions": ["no prod deletes"]},
                                              db=db_session, agent_id="30001")
    assert r["success"] is True
    r = await tool_registry.execute_tool_async("ethos", action="verify_identity",
                                              db=db_session, agent_id="30001")
    assert r["success"] is False
    _seed(db_session, "20001", "20001")
    r = await tool_registry.execute_tool_async("ethos", action="verify_identity",
                                              db=db_session, agent_id="20001")
    assert r["success"] is True
    ethos = _load_ethos(db_session, "30001")
    assert ethos.get_restrictions() == ["no prod deletes"]


@pytest.mark.asyncio
async def test_critic_tier_can_use_ethos(db_session):
    _seed(db_session, "70001", "70001")
    r = await tool_registry.execute_tool_async("ethos", action="read",
                                              db=db_session, agent_id="70001")
    assert r["success"] is True
    r = await tool_registry.execute_tool_async("ethos", action="append", kind="reasoning",
                                              payload="checked plan for DAG soundness",
                                              db=db_session, agent_id="70001")
    assert r["success"] is True
