"""
Unit tests for backend.tools.ethos_tool (read action).
"""

import pytest
from sqlalchemy.orm import Session

from backend.tools.ethos_tool import ethos_tool, EthosTool, _load_ethos
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.constitution import Ethos


def _make_agent_with_ethos(db: Session, agentium_id: str) -> Agent:
    agent = Agent(
        agentium_id=agentium_id,
        agent_type=AgentType.TASK_AGENT,
        name=f"Agent {agentium_id}",
        status=AgentStatus.ACTIVE,
    )
    db.add(agent)
    db.flush()
    ethos = Ethos(
        agentium_id=f"E{agentium_id[1:]}",
        agent_type="task_agent",
        mission_statement="Do tasks.",
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


async def test_read_returns_working_memory(db_session: Session):
    agent = _make_agent_with_ethos(db_session, "30001")
    ethos = db_session.query(Ethos).filter_by(id=agent.ethos_id).first()
    ethos.current_objective = "Build the widget"
    ethos.set_task_progress({"step1": "done"})
    ethos.add_lesson_learned({"key_point": "use transactions"})
    db_session.flush()

    result = await ethos_tool.execute(action="read", db=db_session, agent_id="30001")

    assert result["success"] is True
    data = result["data"]
    assert data["current_objective"] == "Build the widget"
    assert data["task_progress"]["step1"] == "done"
    assert data["lessons_learned"][0]["key_point"] == "use transactions"


async def test_read_unknown_agent(db_session: Session):
    result = await ethos_tool.execute(action="read", db=db_session, agent_id="39999")

    assert result["success"] is False
    assert result["error"] is not None
