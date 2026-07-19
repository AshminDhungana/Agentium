# Async, Cancellable, Timeout-Bounded Agent Tool Calls — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make agent tool calls in the agentic loop run non-blocking with a per-tool timeout, be cancellable from four sources, and support concurrent fan-out — without the agent ever hanging on a stuck tool.

**Architecture:** A new `backend/core/tool_runner.py` provides `run_tool_async`, which wraps every tool call in `asyncio.wait_for` + an `asyncio.Event` cancel watch and returns a structured result (success/error/timeout/cancelled). A process-local `active_tool_runs` token registry lets timeout, agent self-abort, external/user/Head stop, and supervisor abort all funnel into one `cancel_tool_run` call. `model_provider.generate_with_agent_tools` routes its per-tool `tool_executor` through `run_tool_async` (the provider loops already fan out via `asyncio.gather`). Sync tools get best-effort cancel (we stop awaiting; the worker may finish in the background). No automatic retry — the agent decides.

**Tech Stack:** Python 3.11+, asyncio, FastAPI/pytest (`asyncio_mode = auto`), SQLAlchemy (existing).

## Global Constraints

- Scope is the **agentic loop only** (`model_provider.generate_with_agent_tools` → `tool_executor` and `tool_registry.execute_tool_async`). Direct API execution, `AgentOrchestrator._execute_tool_directly`, and the MCP bridge are out of scope.
- Cancellation triggers supported by the mechanism: auto-on-timeout, agent self-abort, external/user/Head stop, supervisor (Lead→subordinate) abort.
- All four sources call `cancel_tool_run(run_id, reason)` — one mechanism.
- Retry is **agent-driven only**; the execution layer performs no automatic retry.
- Existing sync/async tool behavior and analytics/audit (`ToolCreationService.execute_tool`) are preserved.
- Sync-tool cancellation is best-effort (await dropped; worker thread may continue) — documented limitation.
- `pytest` config: `asyncio_mode = auto`; run unit tests with `pytest backend/tests/core/test_tool_runner.py -o addopts=""` style; integration tests need the docker test stack (`make test-integration`).
- Repo policy: `docs/superpowers/` is gitignored — do **not** force-add plan/spec files.

---

## File Structure

- **Create** `backend/core/tool_runner.py` — `run_tool_async`, `ToolCallToken`, `active_tool_runs`, `register_tool_run`, `deregister_tool_run`, `cancel_tool_run`. The single cancellable execution primitive.
- **Modify** `backend/core/config.py` — add `TOOL_TIMEOUT_DEFAULT` setting (~line 44).
- **Modify** `backend/core/tool_registry.py` — `register_tool` gains optional `timeout` param (line 1801); add `get_tool_timeout(name)` after `get_tool` (line 1819); `execute_tool_async` (line 1869) delegates to `run_tool_async` preserving legacy return shape.
- **Modify** `backend/services/model_provider.py` — extract `tool_executor` into module-level `build_tool_executor` (replacing inline def at line 1526); in `generate_with_agent_tools` register/deregister a `ToolCallToken` and pass `run_event` to the provider (lines 1523–1586).
- **Create** `backend/tests/core/test_tool_runner.py` — unit tests for timeout, cancel, per-tool override, fan-out, legacy `execute_tool_async` shape.
- **Create** `backend/tests/core/test_model_provider_tool_executor.py` — unit test that `build_tool_executor` returns a timeout JSON via `run_tool_async`.

---

### Task 1: Add `TOOL_TIMEOUT_DEFAULT` setting

**Files:**
- Modify: `backend/core/config.py:44` (after `REDIS_TIMEOUT`)

**Interfaces:**
- Produces: `settings.TOOL_TIMEOUT_DEFAULT: float` (used by `run_tool_async`).

- [ ] **Step 1: Add the field**

In `backend/core/config.py`, inside the `Settings` class after `REDIS_TIMEOUT: int = 5  # seconds` (line 44), add:

```python
    # Tool execution — default per-call timeout for agent tool calls (seconds)
    TOOL_TIMEOUT_DEFAULT: float = Field(default=60.0, env="TOOL_TIMEOUT_DEFAULT")
```

- [ ] **Step 2: Verify it imports**

Run: `cd "E:/Ongoing Projects/Agentium" && python -c "from backend.core.config import settings; print(settings.TOOL_TIMEOUT_DEFAULT)"`
Expected: `60.0`

- [ ] **Step 3: Commit**

```bash
git add backend/core/config.py
git commit -m "feat(tools): add TOOL_TIMEOUT_DEFAULT setting for agent tool calls"
```

---

### Task 2: Per-tool timeout metadata on the registry

**Files:**
- Modify: `backend/core/tool_registry.py:1801` (`register_tool`)
- Modify: `backend/core/tool_registry.py:1819` (add `get_tool_timeout` after `get_tool`)

**Interfaces:**
- Consumes: `settings.TOOL_TIMEOUT_DEFAULT` (Task 1).
- Produces: `tool_registry.get_tool_timeout(name) -> Optional[float]` (used by `run_tool_async` and `build_tool_executor`).

- [ ] **Step 1: Write the failing test**

Create `backend/tests/core/test_tool_runner.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_tool_runner.py::test_register_tool_timeout_metadata -v -o addopts=""`
Expected: FAIL (`get_tool_timeout` not defined / `register_tool` got unexpected `timeout`).

- [ ] **Step 3: Add `timeout` param and `get_tool_timeout`**

In `backend/core/tool_registry.py`, change `register_tool` (line 1801):

```python
    def register_tool(
        self,
        name: str,
        description: str,
        function: Callable,
        parameters: Dict[str, Any],
        authorized_tiers: Optional[List[str]] = None,
        timeout: Optional[float] = None,
    ) -> None:
        self.tools[name] = {
            "name":             name,
            "description":      description,
            "function":         function,
            "parameters":       parameters,
            "authorized_tiers": authorized_tiers or [],
            "timeout":          timeout,
        }
```

After `get_tool` (line 1819), add:

```python
    def get_tool_timeout(self, name: str) -> Optional[float]:
        """Per-tool timeout override, or None to use the global default."""
        tool = self.tools.get(name)
        if tool and tool.get("timeout") is not None:
            return float(tool["timeout"])
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_tool_runner.py::test_register_tool_timeout_metadata -v -o addopts=""`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/tool_registry.py backend/tests/core/test_tool_runner.py
git commit -m "feat(tools): add per-tool timeout metadata + get_tool_timeout"
```

---

### Task 3: `run_tool_async` — cancellable, timeout-bounded execution primitive

**Files:**
- Create: `backend/core/tool_runner.py`
- Modify: `backend/tests/core/test_tool_runner.py` (append tests)

**Interfaces:**
- Consumes: `tool_registry.get_tool_timeout` (Task 2), `settings.TOOL_TIMEOUT_DEFAULT` (Task 1), `ToolCreationService.execute_tool` (existing).
- Produces: `run_tool_async(name, kwargs, *, timeout, cancel_event, called_by, task_id, db, use_service, run_id) -> Dict[str, Any]`; `ToolCallToken`; `register_tool_run`; `deregister_tool_run`; `cancel_tool_run`.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/core/test_tool_runner.py`:

```python
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
    assert out["result"] == {"status": "success", "data": 1}
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_tool_runner.py -v -o addopts=""`
Expected: FAIL (module `backend.core.tool_runner` not found).

- [ ] **Step 3: Implement `backend/core/tool_runner.py`**

```python
import asyncio
import inspect
import time
from dataclasses import dataclass
from typing import Any, Dict, Optional

from backend.core.config import settings


@dataclass
class ToolCallToken:
    """A live tool-call run, addressable for cancellation."""

    run_id: str
    cancel_event: asyncio.Event
    started_at: float
    cancel_reason: Optional[str] = None


# Process-local registry of live runs, keyed by run_id (e.g. task_id).
active_tool_runs: Dict[str, ToolCallToken] = {}


def register_tool_run(token: ToolCallToken) -> None:
    active_tool_runs[token.run_id] = token


def deregister_tool_run(run_id: str) -> None:
    active_tool_runs.pop(run_id, None)


def cancel_tool_run(run_id: str, reason: str = "cancelled") -> bool:
    """Set the cancel event for a live run. Returns False if unknown.

    Single funnel for all four cancel sources: timeout (automatic, handled
    inside run_tool_async), agent self-abort, external/user/Head stop, and
    supervisor (Lead->subordinate) abort.
    """
    token = active_tool_runs.get(run_id)
    if token is None:
        return False
    token.cancel_reason = reason
    token.cancel_event.set()
    return True


async def run_tool_async(
    name: str,
    kwargs: Dict[str, Any],
    *,
    timeout: Optional[float] = None,
    cancel_event: Optional[asyncio.Event] = None,
    called_by: str = "system",
    task_id: Optional[str] = None,
    db: Any = None,
    use_service: bool = True,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute a registered tool non-blocking, with a timeout and cancel watch.

    Returns a structured dict:
        {status, result?, error?, timed_out, cancelled, cancel_reason?,
         elapsed_ms, tool_name}
    status is one of: success | error | timeout | cancelled.
    """
    from backend.core.tool_registry import tool_registry

    if timeout is None:
        timeout = tool_registry.get_tool_timeout(name) or settings.TOOL_TIMEOUT_DEFAULT

    start = time.monotonic()
    elapsed_ms = lambda: (time.monotonic() - start) * 1000

    async def _call() -> Any:
        if use_service and db is not None:
            from backend.services.tool_creation_service import ToolCreationService
            return ToolCreationService(db).execute_tool(
                tool_name=name, called_by=called_by, kwargs=kwargs, task_id=task_id
            )
        fn = tool_registry.get_tool_function(name)
        if fn is None:
            return {"status": "error", "error": f"Tool '{name}' not found"}
        if inspect.iscoroutinefunction(fn):
            return await fn(**kwargs)
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, lambda: fn(**kwargs))

    async def _wait_race(call_task: asyncio.Task) -> None:
        if cancel_event is None:
            await call_task
            return
        watch = asyncio.ensure_future(cancel_event.wait())
        try:
            await asyncio.wait({call_task, watch}, return_when=asyncio.FIRST_COMPLETED)
        finally:
            watch.cancel()

    call_task = asyncio.ensure_future(_call())
    try:
        try:
            await asyncio.wait_for(_wait_race(call_task), timeout=timeout)
        except asyncio.TimeoutError:
            call_task.cancel()  # best-effort: async tools stop; sync threads may linger
            return {
                "status": "timeout",
                "timed_out": True,
                "error": f"Tool '{name}' timed out after {timeout}s",
                "elapsed_ms": elapsed_ms(),
                "tool_name": name,
            }

        # No timeout fired. Either the call finished or cancellation did.
        if cancel_event is not None and cancel_event.is_set():
            call_task.cancel()
            reason = None
            if run_id:
                tok = active_tool_runs.get(run_id)
                if tok:
                    reason = tok.cancel_reason
            return {
                "status": "cancelled",
                "cancelled": True,
                "cancel_reason": reason,
                "error": "Tool call cancelled",
                "elapsed_ms": elapsed_ms(),
                "tool_name": name,
            }

        result = call_task.result()  # raises if _call raised -> caught below
        if isinstance(result, dict) and "status" in result:
            return {**result, "elapsed_ms": elapsed_ms(), "tool_name": name}
        return {
            "status": "success",
            "result": result,
            "elapsed_ms": elapsed_ms(),
            "tool_name": name,
        }
    except Exception as exc:  # noqa: BLE001 - normalize all tool failures
        return {
            "status": "error",
            "error": str(exc),
            "elapsed_ms": elapsed_ms(),
            "tool_name": name,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_tool_runner.py -v -o addopts=""`
Expected: PASS (all 7 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/core/tool_runner.py backend/tests/core/test_tool_runner.py
git commit -m "feat(tools): add run_tool_async cancellable execution primitive + token registry"
```

---

### Task 4: Route the agentic-loop `tool_executor` through `run_tool_async`

**Files:**
- Modify: `backend/services/model_provider.py:24` (imports), `:1523` (remove `svc = ToolCreationService(db)`), `:1526` (replace inline `tool_executor` def with module-level `build_tool_executor`), `:1572`–`1586` (register/deregister token, pass `run_event`).
- Create: `backend/tests/core/test_model_provider_tool_executor.py`

**Interfaces:**
- Consumes: `run_tool_async`, `ToolCallToken`, `register_tool_run`, `deregister_tool_run` (Task 3); `tool_registry.get_tool_timeout` (Task 2).
- Produces: `build_tool_executor(agent_id, task_id, db, cancel_event, run_id) -> Callable[[str, dict], Awaitable[str]]`.

- [ ] **Step 1: Write the failing test**

Create `backend/tests/core/test_model_provider_tool_executor.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_model_provider_tool_executor.py -v -o addopts=""`
Expected: FAIL (`build_tool_executor` not defined).

- [ ] **Step 3: Add imports + `build_tool_executor`**

In `backend/services/model_provider.py`, ensure these imports exist near the top (add if missing):

```python
import asyncio
import json
import time
import uuid
from typing import Dict, Any, Optional
from backend.core.tool_runner import (
    run_tool_async,
    ToolCallToken,
    register_tool_run,
    deregister_tool_run,
)
```

Add a module-level function (e.g. right before `class ModelService` or near the top of the module):

```python
def build_tool_executor(
    agent_id: str,
    task_id: Optional[str],
    db: Any,
    cancel_event: asyncio.Event,
    run_id: str,
) -> Any:
    """Build the per-turn tool executor used by the agentic loop.

    Routes every call through run_tool_async so each tool gets its own
    timeout (per-tool override or global default) and is cancellable via
    ``cancel_event``. Returns a JSON string (the model's tool_result).
    """
    from backend.core.tool_registry import tool_registry

    async def tool_executor(name: str, args: Dict[str, Any]) -> str:
        result = await run_tool_async(
            name,
            args,
            timeout=tool_registry.get_tool_timeout(name),
            cancel_event=cancel_event,
            called_by=agent_id,
            task_id=task_id,
            db=db,
            use_service=True,
            run_id=run_id,
        )
        return json.dumps(result)

    return tool_executor
```

- [ ] **Step 4: Wire token registration into `generate_with_agent_tools`**

Replace the block at lines 1523–1540 (the `svc = ToolCreationService(db)` and the inline `async def tool_executor`) with nothing — `build_tool_executor` replaces it. Then modify the call region (lines ~1572–1586) from:

```python
        from backend.services.api_key_manager import api_key_manager

        try:
            result = await provider.generate_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                max_iterations=max_tool_iterations,
                agentium_id=agent_id,
                on_delta=on_delta,
                cancel_event=cancel_event,
                **({"tool_choice": caller_tool_choice} if caller_tool_choice else {}),
                **kwargs,
            )
```

to:

```python
        from backend.services.api_key_manager import api_key_manager

        run_id = task_id or f"run_{uuid.uuid4().hex}"
        run_event = cancel_event or asyncio.Event()
        register_tool_run(
            ToolCallToken(run_id=run_id, cancel_event=run_event, started_at=time.time())
        )
        try:
            tool_executor = build_tool_executor(
                agent_id=agent_id, task_id=task_id, db=db,
                cancel_event=run_event, run_id=run_id,
            )
            result = await provider.generate_with_tools(
                system_prompt=system_prompt,
                messages=messages,
                tools=tools,
                tool_executor=tool_executor,
                max_iterations=max_tool_iterations,
                agentium_id=agent_id,
                on_delta=on_delta,
                cancel_event=run_event,
                **({"tool_choice": caller_tool_choice} if caller_tool_choice else {}),
                **kwargs,
            )
            api_key_manager.mark_key_success(provider.config.id, db=db)
            cost = result.get("cost_usd", 0.0)
            tokens = result.get("tokens_used", 0)
            api_key_manager.record_spend(provider.config.id, cost, tokens, db=db)
            return result
        finally:
            deregister_tool_run(run_id)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_model_provider_tool_executor.py -v -o addopts=""`
Expected: PASS (both tests).

- [ ] **Step 6: Commit**

```bash
git add backend/services/model_provider.py backend/tests/core/test_model_provider_tool_executor.py
git commit -m "feat(tools): route agentic-loop tool_executor through run_tool_async with per-run cancel token"
```

---

### Task 5: Delegate `execute_tool_async` to `run_tool_async` (preserve legacy shape)

**Files:**
- Modify: `backend/core/tool_registry.py:1869` (`execute_tool_async`)
- Modify: `backend/tests/core/test_tool_runner.py` (append tests)

**Interfaces:**
- Consumes: `run_tool_async` (Task 3), `settings.TOOL_TIMEOUT_DEFAULT` (Task 1).
- Produces: unchanged public return shape (`{status:"error",...}` on failure, raw tool result on success) — now timeout-bounded.

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/core/test_tool_runner.py`:

```python
@pytest.mark.asyncio
async def test_execute_tool_async_timeout_legacy_shape():
    async def slow(**kwargs):
        await asyncio.sleep(10)
        return {"status": "success"}

    tool_registry.register_tool("eta_slow", "desc", slow, {}, None, timeout=0.05)
    out = await tool_registry.execute_tool_async("eta_slow")
    assert out["status"] == "error"
    assert "timed out" in out["error"].lower()


@pytest.mark.asyncio
async def test_execute_tool_async_success_legacy_shape():
    def fast(**kwargs):
        return {"status": "success", "data": 42}

    tool_registry.register_tool("eta_fast", "desc", fast, {}, None)
    out = await tool_registry.execute_tool_async("eta_fast")
    # Legacy shape: raw tool result returned on success.
    assert out == {"status": "success", "data": 42}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_tool_runner.py::test_execute_tool_async_timeout_legacy_shape tests/core/test_tool_runner.py::test_execute_tool_async_success_legacy_shape -v -o addopts=""`
Expected: FAIL (existing `execute_tool_async` has no timeout → hangs until 10s then returns raw result, assertions fail).

- [ ] **Step 3: Implement delegation**

Replace `execute_tool_async` (line 1869) with:

```python
    async def execute_tool_async(self, name: str, **kwargs) -> Dict[str, Any]:
        """Async execution with a timeout, preserving the legacy return shape.

        Delegates to run_tool_async (no service layer, no DB needed here) so a
        hung tool cannot block forever. On success returns the raw tool result;
        on failure/timeout returns {"status": "error", "error": ...}.
        """
        from backend.core.config import settings
        from backend.core.tool_runner import run_tool_async

        structured = await run_tool_async(
            name, kwargs, timeout=settings.TOOL_TIMEOUT_DEFAULT, use_service=False
        )
        if structured["status"] == "success":
            return structured.get("result", structured)
        return {"status": "error", "error": structured.get("error", "unknown error")}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd "E:/Ongoing Projects/Agentium" && python -m pytest tests/core/test_tool_runner.py -v -o addopts=""`
Expected: PASS (all tests including the two new ones).

- [ ] **Step 5: Commit**

```bash
git add backend/core/tool_registry.py backend/tests/core/test_tool_runner.py
git commit -m "feat(tools): make execute_tool_async timeout-bounded, preserve legacy shape"
```

---

### Task 6 (optional): Expose external/supervisor cancellation via API

**Note:** The cancellation *mechanism* (`cancel_tool_run`) already supports all four sources and is in place from Task 3. The agentic loop registers a token keyed by `run_id` (= `task_id`). This task adds a thin HTTP hook so an external caller (user "stop" button, Head veto, Lead supervisor) can reach it. Skip if the UI wiring is deferred.

**Files:**
- Modify: `backend/api/routes/tasks.py` (add a cancel route)

**Interfaces:**
- Consumes: `cancel_tool_run` (Task 3).
- Produces: `POST /api/v1/tasks/{task_id}/cancel` → `{cancelled: bool}`.

- [ ] **Step 1: Add the route**

In `backend/api/routes/tasks.py`, add:

```python
from backend.core.tool_runner import cancel_tool_run


@router.post("/tasks/{task_id}/cancel")
async def cancel_task_run(task_id: str, reason: str = "user stop"):
    """Cancel a running agent tool-call loop by its task_id (run_id)."""
    cancelled = cancel_tool_run(task_id, reason)
    return {"cancelled": cancelled}
```

- [ ] **Step 2: Smoke-test the import**

Run: `cd "E:/Ongoing Projects/Agentium" && python -c "import backend.api.routes.tasks"`
Expected: no traceback.

- [ ] **Step 3: Commit**

```bash
git add backend/api/routes/tasks.py
git commit -m "feat(tools): expose cancel_tool_run via POST /tasks/{id}/cancel"
```

---

## Self-Review Notes

- **Spec coverage:** per-tool timeout (Tasks 1–2), cancellable primitive + 4 sources funnel (Task 3), agentic-loop wiring with per-run token (Task 4), legacy `execute_tool_async` timeout (Task 5), external reachability (Task 6 optional), fan-out (provider loops already `asyncio.gather` at `model_provider.py:778/844/1201` — Task 4 only changes `tool_executor` internals), agent-driven retry (no auto-retry; structured timeout/cancel returned to model). All spec sections mapped.
- **Placeholder scan:** no TBD/TODO; every code step shows the code; tests include assertions and expected outcomes.
- **Type consistency:** `run_tool_async` signature used identically in `build_tool_executor` (Task 4) and `execute_tool_async` (Task 5); `get_tool_timeout` defined Task 2 and consumed Task 3/4; `settings.TOOL_TIMEOUT_DEFAULT` defined Task 1 and consumed Task 3/5; `ToolCallToken`/`cancel_tool_run` defined Task 3 and consumed Task 4/6.
- **Known limitation documented:** sync-tool cancel is best-effort (await dropped; worker thread may linger). The agent is unblocked at `timeout` regardless, which satisfies the core requirement.
