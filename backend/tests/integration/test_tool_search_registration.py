# backend/tests/integration/test_tool_search_registration.py
from backend.core.tool_registry import tool_registry


def test_tool_search_registered():
    assert "tool_search" in tool_registry.tools
    tool = tool_registry.get_tool("tool_search")
    assert set(tool["authorized_tiers"]) == {f"{i}xxxx" for i in range(10)}


def test_tool_search_in_openai_all_tiers():
    for tier in [f"{i}xxxx" for i in range(10)]:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "tool_search" in names


def test_tool_search_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("tool_search"))
    assert "query" in required
    assert "limit" not in required
