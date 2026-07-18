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
