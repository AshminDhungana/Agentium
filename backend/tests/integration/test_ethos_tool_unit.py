"""
Unit tests for backend.tools.ethos_tool (read action).
"""

import json

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


async def test_append_lesson(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    result = await ethos_tool.execute(
        action="append", kind="lesson",
        payload={"key_point": "cache DB sessions"},
        db=db_session, agent_id="30001",
    )
    assert result["success"] is True
    ethos = _load_ethos(db_session, "30001")
    assert ethos.get_lessons_learned()[-1]["key_point"] == "cache DB sessions"
    assert ethos.last_updated_by_agent is True


async def test_append_progress(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    result = await ethos_tool.execute(
        action="append", kind="progress",
        payload={"step2": "done"},
        db=db_session, agent_id="30001",
    )
    assert result["success"] is True
    assert _load_ethos(db_session, "30001").get_task_progress()["step2"] == "done"


async def test_append_invalid_kind(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    result = await ethos_tool.execute(
        action="append", kind="bogus", payload={},
        db=db_session, agent_id="30001",
    )
    assert result["success"] is False
    assert "kind" in (result["error"] or "")


async def test_compress_runs_and_bumps_version(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    ethos = _load_ethos(db_session, "30001")
    for i in range(6):
        ethos.add_lesson_learned({"key_point": f"lesson {i}"})
    for i in range(6):
        arts = ethos.get_reasoning_artifacts()
        arts.append(f"artifact {i}")
        ethos.reasoning_artifacts = json.dumps(arts)
    db_session.flush()
    before_version = ethos.version

    result = await ethos_tool.execute(
        action="compress", completed_steps=["step1"],
        db=db_session, agent_id="30001",
    )
    assert result["success"] is True
    after = _load_ethos(db_session, "30001")
    assert after.version > before_version


async def test_edit_identity_stages_pending(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    result = await ethos_tool.execute(
        action="edit_identity",
        patch={"restrictions": ["do not delete prod"]},
        db=db_session, agent_id="30001",
    )
    assert result["success"] is True
    agent = db_session.query(Agent).filter_by(agentium_id="30001").first()
    assert agent.ethos_action_pending is True
    ethos = _load_ethos(db_session, "30001")
    # Live restrictions must NOT change until verified
    assert ethos.get_restrictions() == []
    pending = json.loads(agent.pending_identity_edit) if agent.pending_identity_edit else {}
    assert pending["restrictions"] == ["do not delete prod"]


async def test_verify_identity_applies(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    await ethos_tool.execute(
        action="edit_identity",
        patch={"restrictions": ["do not delete prod"]},
        db=db_session, agent_id="30001",
    )
    verify = await ethos_tool.execute(
        action="verify_identity",
        db=db_session, agent_id="20001",  # Lead tier
    )
    assert verify["success"] is True
    ethos = _load_ethos(db_session, "30001")
    assert ethos.get_restrictions() == ["do not delete prod"]
    assert ethos.is_verified is True
    agent = db_session.query(Agent).filter_by(agentium_id="30001").first()
    assert agent.ethos_action_pending is False


async def test_verify_identity_denied_for_task(db_session: Session):
    _make_agent_with_ethos(db_session, "30001")
    await ethos_tool.execute(
        action="edit_identity",
        patch={"restrictions": ["x"]},
        db=db_session, agent_id="30001",
    )
    verify = await ethos_tool.execute(
        action="verify_identity",
        db=db_session, agent_id="30001",
    )
    assert verify["success"] is False


def test_ethos_tool_registered_for_all_tiers():
    from backend.core.tool_registry import tool_registry
    desc = tool_registry.get_tool("ethos")
    assert desc is not None, "ethos tool must be registered"
    assert sorted(desc["authorized_tiers"]) == sorted([
        "0xxxx","1xxxx","2xxxx","3xxxx","4xxxx",
        "5xxxx","6xxxx","7xxxx","8xxxx","9xxxx"])
