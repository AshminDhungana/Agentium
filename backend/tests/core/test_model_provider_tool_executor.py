import asyncio
import json

import pytest


@pytest.mark.asyncio
async def test_build_tool_executor_timeout_json(monkeypatch):
    from backend.services.model_provider import build_tool_executor
    from backend.services.tool_creation_service import ToolCreationService
    from backend.core.tool_registry import tool_registry

    async def slow(**kwargs):
        await asyncio.sleep(10)
        return {"status": "success"}

    tool_registry.register_tool("mpe_slow", "desc", slow, {}, None, timeout=0.05)

    # Fake the service call so no real DB is needed; simulate a slow tool.
    def fake_execute(*args, **kwargs):
        import time as _t
        _t.sleep(10)
        return {"status": "success", "result": "late"}

    monkeypatch.setattr(ToolCreationService, "execute_tool", staticmethod(fake_execute))

    executor = build_tool_executor(
        agent_id="30001", task_id="t1", db=object(),
        cancel_event=asyncio.Event(), run_id="t1",
    )
    out = await executor("mpe_slow", {})
    parsed = json.loads(out)
    assert parsed["status"] == "timeout"
    assert parsed["timed_out"] is True
    assert parsed["tool_name"] == "mpe_slow"


@pytest.mark.asyncio
async def test_build_tool_executor_success_json(monkeypatch):
    from backend.services.model_provider import build_tool_executor
    from backend.services.tool_creation_service import ToolCreationService
    from backend.core.tool_registry import tool_registry

    def fast(**kwargs):
        return {"status": "success", "result": {"ok": True}}

    tool_registry.register_tool("mpe_fast", "desc", fast, {}, None)

    def fake_execute(*args, **kwargs):
        return {"status": "success", "result": {"ok": True}}

    monkeypatch.setattr(ToolCreationService, "execute_tool", staticmethod(fake_execute))

    executor = build_tool_executor(
        agent_id="30001", task_id="t2", db=object(),
        cancel_event=asyncio.Event(), run_id="t2",
    )
    out = await executor("mpe_fast", {})
    parsed = json.loads(out)
    assert parsed["status"] == "success"
    assert parsed["result"] == {"ok": True}
