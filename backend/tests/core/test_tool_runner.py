import asyncio
import pytest


@pytest.mark.asyncio
async def test_register_tool_timeout_metadata():
    from backend.core.tool_registry import tool_registry

    def noop(**kwargs):
        return {"status": "success"}

    tool_registry.register_tool("timeout_meta_test", "desc", noop, {}, None, timeout=12.0)
    assert tool_registry.get_tool_timeout("timeout_meta_test") == 12.0

    # No override -> None (run_tool_async falls back to default)
    tool_registry.register_tool("timeout_meta_none", "desc", noop, {}, None)
    assert tool_registry.get_tool_timeout("timeout_meta_none") is None
