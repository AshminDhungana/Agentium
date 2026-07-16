import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.tools.governance_tool import spawn_agent, liquidate_agent, create_task, dispatch_task, complete_task


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


def test_create_task_unauthorized():
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=False):
        res = create_task(title="T", description="D", db=MagicMock(), agent_id="30001")
        assert res["success"] is False
        assert "not authorized" in res["error"].lower()


def test_complete_task_happy_path():
    task = MagicMock(); task.agentium_id = "t1"; task.status.value = "completed"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = task
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=True):
        res = complete_task(task_id="t1", result_summary="done", db=db, agent_id="30001")
        assert res["success"] is True
        task.complete.assert_called_once_with(result_summary="done", result_data={})
        db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_task_happy_path():
    caller = MagicMock(); caller.agentium_id = "00001"
    task = MagicMock(); task.id = "db-t1"; task.agentium_id = "t1"
    task.task_type.value = "execution"; task.description = "do it"; task.tools_allowed = []
    lead = MagicMock(); lead.agentium_id = "20001"; lead.status = "active"
    db = MagicMock()
    db.query.return_value.filter.return_value.first.side_effect = [caller, task, lead]
    orch = MagicMock()
    orch.delegate_to_task = AsyncMock(return_value=MagicMock(success=True))
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=True), \
         patch("backend.tools.governance_tool.AgentOrchestrator", return_value=orch):
        res = await dispatch_task(task_id="t1", db=db, agent_id="00001")
        assert res["success"] is True
        orch.delegate_to_task.assert_awaited_once()
