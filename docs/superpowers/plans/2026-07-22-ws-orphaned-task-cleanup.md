# Orphaned Task Cleanup in WebSocket Handler — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent `TestClient.wait_shutdown` hangs by cancelling orphaned background generation tasks on WebSocket disconnect.

**Architecture:** Track every `_run_generation` task by `stream_id` in a `pending_tasks` dict; cancel all on `WebSocketDisconnect`. Already-handled `CancelledError` in the task body ensures clean unwinding.

**Tech Stack:** Python 3.11+, asyncio, FastAPI/Starlette WebSocket

## Global Constraints

- Single-file change: `backend/api/routes/websocket.py` only
- No new dependencies
- Must preserve existing `cancel` message type behaviour (separate from task cancellation)
- All existing WebSocket tests must pass

---

### Task 1: Track and cancel orphaned generation tasks

**Files:**
- Modify: `backend/api/routes/websocket.py:511-724`

**Interfaces:**
- Consumes: `_run_generation` function (existing), `active_streams: Dict[str, asyncio.Event]` (existing)
- Produces: `pending_tasks: Dict[str, asyncio.Task]` — cleaned up on disconnect and in task `finally`

- [ ] **Step 1: Add `pending_tasks` dict alongside `active_streams`**

At line 513, right after `active_streams`:

```python
    active_streams: Dict[str, asyncio.Event] = {}
    pending_tasks: Dict[str, asyncio.Task] = {}
```

- [ ] **Step 2: Store task reference when spawning `_run_generation`**

At line 724, replace:

```python
                    asyncio.create_task(_run_generation())
```

With:

```python
                    task = asyncio.create_task(_run_generation())
                    pending_tasks[stream_id] = task
```

- [ ] **Step 3: Clean up task reference in `_run_generation` `finally`**

At line 722, add after `active_streams.pop(sid, None)`:

```python
                            pending_tasks.pop(sid, None)
```

- [ ] **Step 4: Cancel tasks on `WebSocketDisconnect`**

At line 734-735, replace:

```python
    except WebSocketDisconnect:
        manager.disconnect(websocket)
```

With:

```python
    except WebSocketDisconnect:
        for t in pending_tasks.values():
            t.cancel()
        pending_tasks.clear()
        manager.disconnect(websocket)
```

- [ ] **Step 5: Cancel tasks in general exception handler**

At line 736-742, replace:

```python
    except Exception as exc:
        logger.error(f"[WebSocket] Unexpected error: {exc}")
        manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
```

With:

```python
    except Exception as exc:
        logger.error(f"[WebSocket] Unexpected error: {exc}")
        for t in pending_tasks.values():
            t.cancel()
        pending_tasks.clear()
        manager.disconnect(websocket)
        try:
            await websocket.close(code=1011, reason="Internal server error")
        except Exception:
            pass
```

- [ ] **Step 6: Verify with integration tests**

```bash
pytest tests/integration/test_structured_input_card.py -v
```

Expected: all 3 tests pass without timeout.

- [ ] **Step 7: Run broader WebSocket-related tests to check for regressions**

```bash
pytest tests/integration/ -k "ws or websocket or chat" -v --timeout=60
```

Expected: all pass within timeout.

- [ ] **Step 8: Commit**

```bash
git add backend/api/routes/websocket.py
git commit -m "fix: cancel orphaned bg tasks on WebSocket disconnect"
```
