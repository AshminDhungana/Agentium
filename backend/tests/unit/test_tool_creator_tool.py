"""Unit tests for tool_creator_tool — mock ToolCreationService."""
from unittest.mock import patch, MagicMock
import pytest


def _make_tool():
    from backend.tools.tool_creator_tool import ToolCreatorTool
    return ToolCreatorTool()


def _good_request(agent_id="00001"):
    return {
        "action": "create",
        "tool_name": "my_tool",
        "description": "does a thing",
        "parameters": [{"name": "x", "type": "string", "description": "input", "required": True}],
        "code_template": "result = {'ok': kwargs.get('x')}",
        "rationale": "needed for task",
        "agent_id": agent_id,
    }


def test_guard_rejects_task_tier():
    tool = _make_tool()
    out = tool.execute(**_good_request(agent_id="30001"))
    assert out["success"] is False
    assert "Head" in out["error"] and "Council" in out["error"]


def test_guard_rejects_lead_tier():
    tool = _make_tool()
    out = tool.execute(**_good_request(agent_id="20001"))
    assert out["success"] is False


def test_head_auto_activates():
    tool = _make_tool()
    with patch("backend.tools.tool_creator_tool.ToolCreationService") as Svc:
        svc = Svc.return_value
        svc.propose_tool.return_value = {
            "proposed": True, "status": "activated",
            "activated": True, "tool_name": "my_tool",
        }
        out = tool.execute(**_good_request(agent_id="00001"))
    assert out["success"] is True
    assert out["tool_name"] == "my_tool"
    assert out["status"] == "activated"
    svc.propose_tool.assert_called_once()


def test_council_returns_pending_vote():
    tool = _make_tool()
    with patch("backend.tools.tool_creator_tool.ToolCreationService") as Svc:
        svc = Svc.return_value
        svc.propose_tool.return_value = {
            "proposed": True, "status": "pending_vote",
            "voting_id": "abc", "tool_name": "my_tool",
        }
        out = tool.execute(**_good_request(agent_id="10023"))
    assert out["success"] is True
    assert out["status"] == "pending_vote"
    svc.propose_tool.assert_called_once()


def test_authorized_tiers_clamped():
    tool = _make_tool()
    captured = {}
    with patch("backend.tools.tool_creator_tool.ToolCreationService") as Svc:
        svc = Svc.return_value
        svc.propose_tool.side_effect = lambda req: captured.update({"req": req}) or {
            "proposed": True, "status": "activated", "activated": True,
            "tool_name": req.tool_name,
        }
        tool.execute(
            action="create", tool_name="t", description="d",
            parameters=[], code_template="result={}", rationale="r",
            authorized_tiers=["3xxxx"], agent_id="00001",
        )
    assert captured["req"].authorized_tiers == ["0xxxx", "1xxxx"]


def test_help_returns_skill_path():
    tool = _make_tool()
    out = tool.execute(action="help")
    assert out["success"] is True
    assert "SKILL.md" in out["help"]
