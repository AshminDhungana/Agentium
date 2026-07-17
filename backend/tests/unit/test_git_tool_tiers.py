from backend.core.tool_registry import tool_registry


def test_git_tool_authorized_for_all_tiers():
    desc = tool_registry.get_tool("git")
    assert desc is not None, "git tool must be registered"
    assert desc["authorized_tiers"] == [
        "0xxxx", "1xxxx", "2xxxx", "3xxxx", "4xxxx", "5xxxx", "6xxxx"
    ], "git tool must be available to every agent tier"
