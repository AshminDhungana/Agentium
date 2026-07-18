# backend/tests/integration/test_code_execution_registration.py
from backend.core.tool_registry import tool_registry

ALLOWED = ["0xxxx", "1xxxx", "2xxxx"]
WITHHELD = [f"{i}xxxx" for i in (3, 4, 5, 6, 7, 8, 9)]


def test_code_execution_registered():
    assert "code_execution" in tool_registry.tools
    tool = tool_registry.get_tool("code_execution")
    assert tool["authorized_tiers"] == ALLOWED


def test_code_execution_visible_only_to_allowed_tiers():
    for tier in ALLOWED:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "code_execution" in names
    for tier in WITHHELD:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "code_execution" not in names


def test_code_execution_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("code_execution"))
    assert "code" in required
    assert "language" not in required
