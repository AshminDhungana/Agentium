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


import json
import time

from backend.core.tool_runner import (
    ToolCallToken,
    active_tool_runs,
    register_tool_run,
    deregister_tool_run,
    cancel_tool_run,
    run_tool_async,
)
from backend.core.tool_registry import tool_registry


@pytest.mark.asyncio
async def test_run_tool_async_timeout():
    async def slow(**kwargs):
        await asyncio.sleep(10)
        return {"status": "success", "result": "late"}

    tool_registry.register_tool("rt_timeout", "desc", slow, {}, None, timeout=0.05)
    out = await run_tool_async("rt_timeout", {}, timeout=0.05)
    assert out["status"] == "timeout"
    assert out["timed_out"] is True
    assert "timed out" in out["error"].lower()
    assert out["tool_name"] == "rt_timeout"


@pytest.mark.asyncio
async def test_run_tool_async_success_shape():
    def fast(**kwargs):
        return {"status": "success", "data": 1}

    tool_registry.register_tool("rt_fast", "desc", fast, {}, None)
    out = await run_tool_async("rt_fast", {}, timeout=5.0, use_service=False)
    assert out["status"] == "success"
    # result is a dict-with-status -> merged in (not wrapped under "result")
    assert out["data"] == 1
    assert out["elapsed_ms"] >= 0
    assert out["tool_name"] == "rt_fast"


@pytest.mark.asyncio
async def test_run_tool_async_external_cancel():
    started = asyncio.Event()
    done = asyncio.Event()

    async def slow(**kwargs):
        started.set()
        await asyncio.sleep(10)
        return {"status": "success"}

    tool_registry.register_tool("rt_cancel", "desc", slow, {}, None, timeout=30.0)

    async def driver():
        await started.wait()
        cancel_event.set()

    cancel_event = asyncio.Event()
    asyncio.ensure_future(driver())
    out = await run_tool_async("rt_cancel", {}, timeout=30.0, cancel_event=cancel_event, run_id="rt_cancel_run")
    assert out["status"] == "cancelled"
    assert out["cancelled"] is True


@pytest.mark.asyncio
async def test_run_tool_async_per_tool_override():
    async def slow(**kwargs):
        await asyncio.sleep(10)
        return {"status": "success"}

    # register with a small per-tool timeout; do NOT pass explicit timeout
    tool_registry.register_tool("rt_override", "desc", slow, {}, None, timeout=0.05)
    out = await run_tool_async("rt_override", {})
    assert out["status"] == "timeout"


@pytest.mark.asyncio
async def test_run_tool_async_fanout():
    order = []

    def mk(name, delay):
        def fn(**kwargs):
            time.sleep(delay)
            order.append(name)
            return {"status": "success", "name": name}
        return fn

    tool_registry.register_tool("rt_a", "desc", mk("a", 0.1), {}, None)
    tool_registry.register_tool("rt_b", "desc", mk("b", 0.1), {}, None)
    results = await asyncio.gather(
        run_tool_async("rt_a", {}, timeout=5.0, use_service=False),
        run_tool_async("rt_b", {}, timeout=5.0, use_service=False),
        return_exceptions=True,
    )
    assert all(r["status"] == "success" for r in results)
    # both ran (concurrently; ordering not guaranteed but both present)
    assert set(order) == {"a", "b"}


@pytest.mark.asyncio
async def test_cancel_tool_run_sets_event():
    ev = asyncio.Event()
    tok = ToolCallToken(run_id="r1", cancel_event=ev, started_at=0.0)
    register_tool_run(tok)
    assert cancel_tool_run("r1", "user stop") is True
    assert ev.is_set()
    assert active_tool_runs["r1"].cancel_reason == "user stop"
    assert cancel_tool_run("missing") is False
    deregister_tool_run("r1")
