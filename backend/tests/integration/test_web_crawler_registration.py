from backend.core.tool_registry import tool_registry


def test_web_crawler_registered():
    assert "web_crawler" in tool_registry.tools
    tool = tool_registry.get_tool("web_crawler")
    assert set(tool["authorized_tiers"]) == {f"{i}xxxx" for i in range(10)}


def test_web_crawler_in_openai_and_anthropic_all_tiers():
    for tier in [f"{i}xxxx" for i in range(10)]:
        names = [t["function"]["name"] for t in tool_registry.to_openai_tools(tier)]
        assert "web_crawler" in names
        names_a = [t["name"] for t in tool_registry.to_anthropic_tools(tier)]
        assert "web_crawler" in names_a


def test_web_crawler_required_param():
    props, required = tool_registry._build_props(tool_registry.get_tool("web_crawler"))
    assert "url" in required
    assert "max_depth" not in required
    assert "max_pages" not in required
