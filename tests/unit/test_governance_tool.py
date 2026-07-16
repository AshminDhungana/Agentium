import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from backend.tools.governance_tool import spawn_agent, liquidate_agent, create_task, dispatch_task, complete_task, propose_amendment, open_vote, cast_vote, conclude_vote
from backend.core.tool_registry import tool_registry


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


@pytest.mark.asyncio
async def test_propose_amendment_unauthorized():
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=False):
        res = await propose_amendment(title="T", description="D", proposed_text="X",
                                      db=MagicMock(), agent_id="30001")
        assert res["success"] is False
        assert "not authorized" in res["error"].lower()


@pytest.mark.asyncio
async def test_cast_vote_happy_path():
    svc = MagicMock()
    svc.cast_vote = AsyncMock(return_value={"tally": {"for": 1}})
    with patch("backend.tools.governance_tool.CapabilityRegistry.can_agent", return_value=True), \
         patch("backend.tools.governance_tool.AmendmentService", return_value=svc):
        res = await cast_vote(amendment_id="a1", vote="for", rationale="ok",
                              db=MagicMock(), agent_id="10001")
        assert res["success"] is True
        assert res["data"]["tally"]["for"] == 1


def test_governance_tools_registered_with_tiers():
    expected = {
        "spawn_agent": ["0xxxx", "1xxxx", "2xxxx"],
        "liquidate_agent": ["0xxxx", "2xxxx"],
        "create_task": ["0xxxx", "1xxxx", "2xxxx"],
        "dispatch_task": ["0xxxx", "1xxxx", "2xxxx"],
        "complete_task": ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"],
        "propose_amendment": ["0xxxx", "1xxxx"],
        "open_vote": ["0xxxx", "1xxxx"],
        "cast_vote": ["0xxxx", "1xxxx"],
        "conclude_vote": ["0xxxx"],
    }
    for name, tiers in expected.items():
        desc = tool_registry.get_tool(name)
        assert desc is not None, f"{name} not registered"
        assert desc["authorized_tiers"] == tiers, f"{name} tiers wrong: {desc['authorized_tiers']}"


def test_existing_tool_tier_changes():
    assert tool_registry.get_tool("read_file")["authorized_tiers"] == ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"]
    assert tool_registry.get_tool("write_file")["authorized_tiers"] == ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"]
    assert tool_registry.get_tool("text_editor")["authorized_tiers"] == ["0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"]
    assert tool_registry.get_tool("execute_command")["authorized_tiers"] == ["0xxxx", "1xxxx", "2xxxx"]
