from backend.core.tool_registry import tool_registry


def test_web_fetch_registered():
    assert "web_fetch" in tool_registry.tools
    tool = tool_registry.get_tool("web_fetch")
    assert set(tool["authorized_tiers"]) == {f"{i}xxxx" for i in range(10)}


def test_web_fetch_in_openai_and_anthropic_all_tiers():
    for tier in [f"{i}xxxx" for i in range(10)]:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "web_fetch" in names
        names_a = [t["name"] for t in tool_registry.to_anthropic_tools(tier)]
        assert "web_fetch" in names_a


def test_web_fetch_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("web_fetch"))
    assert "url" in required
    assert "max_tokens" not in required
