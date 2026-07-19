# Async, Cancellable, Timeout-Bounded Agent Tool Calls

- **Date:** 2026-07-19
- **Status:** approved
- **Domain:** backend / agent tool execution
- **Scope:** agentic loop only (see Scope)

## Problem

Today an agent calling a tool can hang forever. In the agentic loop:

- `backend/services/model_provider.py::generate_with_agent_tools` (the `tool_executor`
  at ~line 1526) runs `ToolCreationService.execute_tool` inside
  `loop.run_in_executor(None, ...)` with **no timeout** and no way to abort.
- `backend/core/tool_registry.py::execute_tool_async` `await`s async tools directly
  (no timeout) and runs sync tools in an executor (no timeout).

A stuck browser, remote executor, or MCP server therefore blocks the agent
indefinitely. There is **no cancellation mechanism anywhere** in the tool path.

Timeouts exist only on the *sync* `ThreadPoolExecutor` wrappers
(`tool_registry.execute_tool` 60s, `tool_creation_service.execute_tool` 120s),
which are not on the agentic-loop path.

## Goals

1. Agent tool calls run **non-blocking** with a **per-tool, configurable timeout**.
2. A tool call can be **cancelled** from four sources, all funneling into one mechanism:
   auto-on-timeout, agent self-abort, external/user/Head stop, supervisor (Lead→subordinate) abort.
3. The agent can fire **multiple tool calls concurrently** (fan-out) when the model requests them.
4. After a timeout/cancel the **agent decides** what to do (retry / change args / move on).
   The execution layer does no automatic retry.

## Non-goals

- Changing direct API execution paths (`api/routes/tools.py`, `tool_creation.py`).
- Adding timeouts to `AgentOrchestrator._execute_tool_directly` (sync routing path).
- Hard-killing synchronous tools (process isolation). Cancellation of sync tools is
  best-effort (we stop awaiting; the worker thread may finish in the background).
- Building a full UI "stop" button; the *mechanism* is provided, the button is optional/minimal.

## Approach

**A. Asyncio-native** (chosen over process-isolation and hybrid):

Wrap every tool call in `asyncio.wait_for(..., timeout)` and watch an
`asyncio.Event` for cancellation. Async tools (browser/nodriver, MCP, remote executor
are async or subprocess-based) get genuine interruption. Sync tools run in a thread and
we stop awaiting on cancel (best-effort). Fan-out via `asyncio.gather`.

Rationale: the tools that actually hang in Agentium are external/async I/O, so this
delivers real cancellation for the dangerous cases with minimal risk to the large
sync-tool ecosystem.

## Design

### 1. Core runner + cancellation model

New module `backend/core/tool_runner.py`:

```python
async def run_tool_async(
    name: str,
    kwargs: Dict[str, Any],
    *,
    timeout: Optional[float] = None,
    cancel_event: Optional[asyncio.Event] = None,
    called_by: str = "system",
    task_id: Optional[str] = None,
    db=None,
) -> Dict[str, Any]:
    ...
```

Execution goes through `ToolCreationService.execute_tool` (not `tool_registry`
directly) so ToolUsageLog, version lookup, audit, and `db`/`agent_id` injection are all
preserved exactly as today. `ToolCreationService.execute_tool` is synchronous, so
`run_tool_async` runs it in `loop.run_in_executor` and bounds it with `wait_for`.

Behavior:
- Resolve timeout: per-tool override (`tool_registry.get_tool_timeout(name)`) else
  global default `settings.TOOL_TIMEOUT_DEFAULT` (60s).
- Run non-blocking: execute `ToolCreationService.execute_tool(name, called_by, kwargs,
  task_id)` inside `loop.run_in_executor(None, ...)` (covers both async and sync tools
  via the service's existing async-aware dispatch).
- Wrap the executor future in `asyncio.wait_for(call, timeout=resolved_timeout)`.
- Concurrently watch `cancel_event`; if set, cancel the running task.
- On `asyncio.TimeoutError` → `{status:"timeout", timed_out:True, ...}`.
- On `asyncio.CancelledError` caused by the event → `{status:"cancelled", cancelled:True, cancel_reason:...}`.

`ToolCallToken` dataclass:
```python
@dataclass
class ToolCallToken:
    run_id: str
    cancel_event: asyncio.Event
    started_at: float
```

Module-level registry (process-local, single event loop):
```python
active_tool_runs: Dict[str, ToolCallToken] = {}

def register_tool_run(run_id, token) -> None
def cancel_tool_run(run_id, reason) -> bool   # sets token.cancel_event; returns False if unknown
```

All four cancellation sources call `cancel_tool_run(run_id, reason)`:
- **auto on timeout** — handled internally by `wait_for`, no token needed but still recorded.
- **agent self-abort** — the agentic loop sets its own run's `cancel_event`.
- **external/user/Head stop** — `cancel_tool_run(run_id, reason)` from an API/WS hook.
- **supervisor abort** — Lead/Head cancels a subordinate's `run_id` (same call, with authority check at the caller).

### 2. Concurrency / fan-out

In `model_provider.generate_with_agent_tools`, replace the per-tool sequential
`tool_executor` invocation with concurrent dispatch of all tool calls returned in a turn:

```python
results = await asyncio.gather(
    *(run_tool_async(c.name, c.args,
                     timeout=..., cancel_event=run_event,
                     called_by=agent_id, task_id=task_id, db=db)
      for c in tool_calls),
    return_exceptions=True,
)
```

Each call gets its own timeout and shares the run-scoped `cancel_event`. Works for both
OpenAI (`tool_calls` list) and Anthropic (parallel `tool_use` blocks).

### 3. Config + result shape

- Add optional `timeout: Optional[float]` to tool registration metadata.
- `tool_registry.get_tool_timeout(name) -> float` returns the override or the global default.
- `run_tool_async` always returns a structured dict:

```python
{
    "status": "success" | "error" | "timeout" | "cancelled",
    "result": ...,                 # present on success
    "error": str,                  # present on error/timeout/cancelled
    "timed_out": bool,
    "cancelled": bool,
    "cancel_reason": str | None,
    "elapsed_ms": float,
    "tool_name": str,
}
```

The `tool_executor` serializes this to the JSON string the model receives. On
`timeout`/`cancelled` the model sees a clear message (e.g. `"tool X timed out after
60s"` / `"tool X was cancelled: <reason>"`) and decides whether to retry, change args,
or continue. This is the agent-managed retry.

### 4. Integration points (scope: agentic loop only)

- `tool_registry.execute_tool_async` → delegate to `run_tool_async` (adds timeout + cancel
  while preserving the existing return shape on success/error).
- `model_provider.generate_with_agent_tools.tool_executor` → use `run_tool_async`, fan-out
  via `asyncio.gather`, propagate the run's `cancel_event`.
- A `run_id` + `cancel_event` is created in `AgentOrchestrator.execute_task` (or the
  entry that calls `generate_with_agent_tools`) and threaded into the tool executor so
  external cancellation can reach the loop.
- `cancel_tool_run` is exposed as a small helper; wiring a UI "stop" control or a
  Head-veto WS message is a thin caller (optional in this change).

### 5. Error handling & race

- Timeout → structured `timeout` result, logged; analytics records `timed_out`.
- Cancel → structured `cancelled` result, logs `cancel_reason`.
- MCP-style race: if a tool result lands after its cancel, the result is discarded
  gracefully (no double-response, no error).
- Tool exceptions are still caught and returned as `error` (existing behavior preserved).
- Sync-tool cancel is best-effort: the awaited future is dropped, but the underlying
  worker thread may continue; documented as a known limitation of Approach A.

### 6. Testing

- **Unit** (`backend/tests/core/test_tool_runner.py`):
  - `run_tool_async` honors timeout (async tool that sleeps past timeout → `timed_out`).
  - honors external `cancel_event` set mid-run → `cancelled` with reason.
  - per-tool timeout override is respected over the global default.
  - fan-out `gather` returns all results and respects individual timeouts.
- **Integration** (`backend/tests/integration/`):
  - agentic loop with a slow fake tool times out and the agent continues (no hang).
  - concurrent tool calls in one turn execute in parallel (wall time < sum of durations).

## Success criteria

- A hung tool in the agentic loop can no longer block an agent forever.
- Every tool call has a bounded timeout; slow tools return a `timeout` result the agent can act on.
- Cancellation works from timeout, agent self-abort, external, and supervisor sources via one `cancel_tool_run`.
- Multiple tool calls in a turn run concurrently.
- No automatic retry inside the execution layer; the agent drives retries.
- Existing sync/async tool behavior and analytics are preserved.
