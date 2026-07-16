import pytest
from unittest.mock import patch, MagicMock
from backend.tools.governance_tool import spawn_agent, liquidate_agent


def _agent(agentium_id="00001", prefix="0"):
    a = MagicMock()
    a.agentium_id = agentium_id
    return a


def test_spawn_agent_unauthorized_returns_error():
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=False):
        res = spawn_agent(agent_type="task", name="T", description="D",
                          db=MagicMock(), agent_id="30001")
        assert res["success"] is False
        assert "not authorized" in res["error"].lower()


def test_spawn_agent_task_happy_path():
    fake = MagicMock(); fake.agentium_id = "30001"; fake.agent_type.value = "task_agent"; fake.name = "T"
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=True), \
         patch("backend.tools.governance_tool.reincarnation_service.spawn_task_agent", return_value=fake):
        res = spawn_agent(agent_type="task", name="T", description="D",
                          db=MagicMock(), agent_id="00001")
        assert res["success"] is True
        assert res["data"]["agentium_id"] == "30001"


def test_liquidate_agent_unauthorized_returns_error():
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=False):
        res = liquidate_agent(target_agentium_id="30001", reason="x",
                              db=MagicMock(), agent_id="30001")
        assert res["success"] is False
        assert "not authorized" in res["error"].lower()
