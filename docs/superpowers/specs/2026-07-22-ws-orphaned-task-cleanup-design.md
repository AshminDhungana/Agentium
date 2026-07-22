# Orphaned Task Cleanup in WebSocket Handler

## Problem

The `ws_client` test fixture (and, in principle, production WebSocket connections)
can hang during shutdown when a background generation task (`_run_generation`,
spawned via `asyncio.create_task`) outlives the WebSocket connection that created
it. The `TestClient.wait_shutdown` blocks indefinitely because the orphaned task
holds the event loop, preventing clean ASGI lifespan shutdown.

## Root Cause

In `backend/api/routes/websocket.py`, every `msg_type == "message"` spawns a
fire-and-forget asyncio task:

```python
asyncio.create_task(_run_generation())
```

When the client disconnects (`WebSocketDisconnect`), the handler exits the
`while True` loop and calls `manager.disconnect(websocket)`.  The orphaned
`_run_generation` task continues running — it eventually fails trying to
`send_json` on a closed WebSocket, but not before the `TestClient` shutdown
sequence has deadlocked on `portal.call(self.wait_shutdown)`.

## Solution

Track every spawned task by its `stream_id` in a dict alongside the existing
`active_streams` dict.  When the WebSocket disconnects, cancel all pending tasks
before cleaning up the connection.

### Changes

**File: `backend/api/routes/websocket.py`**

| What | Where | Change |
|------|-------|--------|
| New dict | line ~513 | `pending_tasks: Dict[str, asyncio.Task] = {}` |
| Store task | line ~724 | `task = asyncio.create_task(...)` + `pending_tasks[stream_id] = task` |
| Clean up task ref | `_run_generation` `finally` | `pending_tasks.pop(sid, None)` |
| Cancel on disconnect | `WebSocketDisconnect` handler | iterate `pending_tasks` and `task.cancel()` |
| Cancel on unexpected error | `except Exception` handler | same cancellation logic |

### Why `task.cancel()` is safe

- `_run_generation` already has `except asyncio.CancelledError: raise` (line 709),
  which lets the cancellation propagate cleanly through the `finally` block.
- The `finally` block already pops `sid` from `active_streams`; the same pattern
  is added for `pending_tasks`.
- `CancelledError` is raised at the next `await` point — guaranteed because
  `_run_generation` makes at least one `await` call (`send_json` or
  `ChatService.process_message`).

### Tests unaffected

No test changes needed. The fix transparently prevents the hang in
`test_ws_card_response_persisted` and any other test that sends a WebSocket
message and then disconnects before the generation task completes.

## Scope

Single file, ~6 lines added across 4 locations.  No new dependencies.
