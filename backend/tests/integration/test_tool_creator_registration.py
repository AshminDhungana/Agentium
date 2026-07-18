"""Registration test for tool_creator (needs full tool graph → integration)."""
from backend.core.tool_registry import tool_registry


def test_tool_creator_registered():
    assert tool_registry.get_tool("tool_creator") is not None


def test_tool_creator_listed_for_head_and_council():
    assert "tool_creator" in tool_registry.list_tools("0xxxx")
    assert "tool_creator" in tool_registry.list_tools("1xxxx")


def test_tool_creator_hidden_from_task_tier():
    assert "tool_creator" not in tool_registry.list_tools("3xxxx")


def test_tool_creator_exported_to_openai_schema():
    names = [t["function"]["name"] for t in tool_registry.to_openai_tools("0xxxx")]
    assert "tool_creator" in names
    spec = next(t for t in tool_registry.to_openai_tools("0xxxx")
                if t["function"]["name"] == "tool_creator")
    assert "action" in spec["function"]["parameters"]["required"]
