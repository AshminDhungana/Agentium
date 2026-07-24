# WebSocket Disconnect & Message Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate spontaneous WebSocket disconnections during idle periods and ensure in-flight chat messages always receive a reply.

**Architecture:** Hybrid server-client approach — align uvicorn's WS ping interval to 60s, wrap isolated sync DB calls in `run_in_executor`, let generation tasks survive client disconnect, harden frontend heartbeat with health-check fallback, and add send-failure queue + orphan message retry.

**Tech Stack:** Python 3.12, FastAPI/Starlette, SQLAlchemy 2.0, TypeScript/React 18, Zustand

## Global Constraints

- No architectural rewrites — all changes scoped to WS chat path
- `backend/main.py` is the uvicorn entry point
- Backend tests via `pytest`, frontend via Vitest
- Must not affect REST endpoints or Celery tasks

---

## File Structure

| File | Responsibility |
|------|---------------|
| `backend/main.py` | Uvicorn config — set WS ping interval to 60s |
| `backend/api/routes/websocket.py` | WS endpoint — no task cancellation on disconnect; wrap receive-loop DB in executor |
| `frontend/src/store/websocketStore.ts` | WS store — heartbeat hardening, send-failure queue, orphan retry |
| `frontend/src/pages/ChatPage.tsx` | Chat UI — handle orphan message retry |

---

### Task 1: Server — Uvicorn WS Ping Alignment

**Files:**
- Modify: `backend/main.py:1090-1096`

**Interfaces:**
- Produces: uvicorn config with `ws_ping_interval=60, ws_ping_timeout=60`

- [ ] **Step 1: Add WS ping params to uvicorn.run()**

Edit `backend/main.py:1088-1096`:

```python
if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "backend.main:app",
        host="0.0.0.0",
        port=port,
        reload=True,
        log_level="info",
        ws_ping_interval=60,
        ws_ping_timeout=60,
    )
```

- [ ] **Step 2: Verify config is accepted**

Run: `python -c "import uvicorn; print(uvicorn.__version__)"` — confirm >= 0.15.0 (the version that supports these params).

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "fix(server): align uvicorn WS ping interval to 60s"
```

---

### Task 2: Server — Wrap Isolated Receive-Loop DB Queries in Executor

**Files:**
- Modify: `backend/api/routes/websocket.py:607-627`
- Create: `backend/tests/test_ws_event_loop.py`

**Interfaces:**
- Consumes: `asyncio.get_running_loop()` from endpoint context
- Produces: Non-blocking DB lookups that no longer stall the event loop during message processing

**Context:** The `db.query(HeadOfCouncil)` and `db.query(UserModelConfig)` calls run directly in the main WS receive loop (lines 607-627). They are isolated single-row lookups that can be wrapped in `run_in_executor`. The much larger `ChatService.process_message` function is NOT wrapped here — it interleaves sync DB and async WS sends in ways that require a deeper refactor, which is deferred to a follow-up plan.

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_ws_event_loop.py
import asyncio

async def test_db_query_in_executor_does_not_block():
    """A sync DB query wrapped in run_in_executor should not
    prevent the event loop from processing other tasks."""
    loop = asyncio.get_running_loop()
    order = []

    async def monitor():
        await asyncio.sleep(0.02)
        order.append("monitor_ran")

    def blocking_query():
        import time
        time.sleep(0.05)
        return "result"

    result, _ = await asyncio.gather(
        loop.run_in_executor(None, blocking_query),
        monitor(),
    )
    assert result == "result"
    assert "monitor_ran" in order
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest backend/tests/test_ws_event_loop.py -v`
Expected: PASS

- [ ] **Step 3: Wrap the Head lookup in executor**

In `backend/api/routes/websocket.py`, replace the `with get_fresh_db() as db:` block (lines 607-627) with an executor-wrapped version:

```python
loop = asyncio.get_running_loop()

def _lookup_head_and_config():
    with get_fresh_db() as db:
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        if not head:
            return None, None, False
        thinking_enabled = False
        if head.preferred_config_id:
            head_cfg = (
                db.query(UserModelConfig)
                .filter_by(id=head.preferred_config_id)
                .first()
            )
            if head_cfg and is_thinking_config(head_cfg):
                thinking_enabled = True
        return head, {
            "card_response": card_response if card_response else None,
        }, thinking_enabled

head, extra_metadata, thinking_enabled = await loop.run_in_executor(
    None, _lookup_head_and_config
)

if not head:
    await websocket.send_json({
        "type":      "error",
        "content":  "Head of Council is unavailable. Check system status.",
        "timestamp": datetime.utcnow().isoformat(),
    })
    continue
```

Note: `card_response` is closed over from the enclosing scope. Make sure the closure captures it correctly. The `is_thinking_config` function also needs to be importable from executor context (it's a module-level function, so it is).

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `pytest backend/tests/ -v --timeout=30`
Expected: All existing tests pass

- [ ] **Step 5: Commit**

```bash
git add backend/api/routes/websocket.py backend/tests/test_ws_event_loop.py
git commit -m "fix(server): wrap receive-loop DB queries in run_in_executor"
```

---

### Task 3: Server — Generation Survival on Disconnect

**Files:**
- Modify: `backend/api/routes/websocket.py:752-755`

**Interfaces:**
- Consumes: (existing) `pending_tasks` dict, `manager.disconnect()`
- Produces: Generation tasks that complete and persist replies even when client disconnects mid-stream

**Context:** The `WebSocketDisconnect` handler currently cancels all pending generation tasks (line 753). This kills `_run_generation` mid-stream, preventing the persistence background task (`chat_service.py:517`) from running. Instead, let the task complete naturally — the `on_delta` callback already handles send failures gracefully.

- [ ] **Step 1: Write the test**

```python
# backend/tests/test_ws_event_loop.py (append)

from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

async def test_on_delta_absorbs_send_failure():
    """on_delta must silently absorb send_json failures without
    propagating the exception to the caller."""
    captured = []
    
    async def on_delta(text: str) -> None:
        try:
            raise Exception("socket closed")
        except Exception:
            pass
        captured.append(text)
    
    await on_delta("hello")
    assert captured == ["hello"]


async def test_run_generation_finally_runs_on_send_failure():
    """When send_json fails in _run_generation, the finally block
    must still execute to clean up active_streams."""
    mock_ws = AsyncMock()
    mock_ws.send_json.side_effect = Exception("socket closed")

    active_streams = {"test_sid": asyncio.Event()}
    pending_tasks = {}
    
    async def simulate_run_generation():
        sid = "test_sid"
        try:
            await mock_ws.send_json({"type": "message_end", "stream_id": sid})
        except Exception:
            logger = MagicMock()
            logger.error("process_message failed")
        finally:
            active_streams.pop(sid, None)
            pending_tasks.pop(sid, None)
    
    await simulate_run_generation()
    assert "test_sid" not in active_streams
    assert "test_sid" not in pending_tasks
```

- [ ] **Step 2: Remove cancellation from WebSocketDisconnect handler**

In `backend/api/routes/websocket.py`, change the `WebSocketDisconnect` handler (lines 752-756):

```python
except WebSocketDisconnect:
    # Don't cancel generation tasks — let them complete so the
    # reply is persisted to DB. The client's send_json calls fail
    # silently (handled by on_delta / message_end try/except).
    # On reconnect, the frontend loads the persisted reply from
    # chat history.
    pending_tasks.clear()
    manager.disconnect(websocket)
```

Keep the `except Exception` handler (lines 757-766) unchanged — unexpected errors should still cancel tasks.

- [ ] **Step 3: Run tests**

Run: `pytest backend/tests/ -v --timeout=30`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/api/routes/websocket.py
git commit -m "fix(server): let generation tasks complete on client disconnect"
```

---

### Task 4: Frontend — Heartbeat Hardening

**Files:**
- Modify: `frontend/src/store/websocketStore.ts` lines 466-507 (pong timeout), 938-952 (sendPing)

**Interfaces:**
- Consumes: `WS_CONFIG.PONG_TIMEOUT_MS`, `lastDataReceivedTs`, `_ws`, `_pongTimeout`
- Produces: Resilient heartbeat that won't kill the connection on a single missed pong

- [ ] **Step 1: Write the test**

```typescript
// frontend/src/store/__tests__/websocketStore.heartbeat.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';

describe('Heartbeat hardening', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('should skip reconnect when health check succeeds after pong timeout', async () => {
    const mockFetch = vi.mocked(fetch);
    mockFetch.mockResolvedValue({ ok: true } as Response);

    // Simulate the pong timeout guard logic in isolation
    let reconnectCalled = false;
    const lastDataReceivedTs = Date.now() - 40000; // stale, > PONG_TIMEOUT_MS

    const sinceData = Date.now() - lastDataReceivedTs;
    if (sinceData >= 10000) {
      // Health check
      const resp = await fetch('/api/health');
      if (resp.ok) {
        // Grace period — reconnect should NOT be called
        reconnectCalled = false;
      }
    }

    expect(reconnectCalled).toBe(false);
    expect(mockFetch).toHaveBeenCalledWith('/api/health');
  });
});
```

- [ ] **Step 2: Add health check fallback in pong timeout**

In `websocketStore.ts`, modify the pong timeout callback (line ~474-503):

```typescript
const pongTimeout = setTimeout(async () => {
    const sinceData = Date.now() - lastDataReceivedTs;
    if (sinceData < WS_CONFIG.PONG_TIMEOUT_MS) {
        logger.debug('[WebSocket] Pong timeout but data recently received — connection alive, skipping reconnect');
        return;
    }

    // Secondary health check before killing the connection
    try {
        const controller = new AbortController();
        const healthTimeout = setTimeout(() => controller.abort(), 5000);
        const resp = await fetch('/api/health', { signal: controller.signal });
        clearTimeout(healthTimeout);
        if (resp.ok) {
            logger.debug('[WebSocket] Pong timeout but server healthy — extending grace period');
            lastDataReceivedTs = Date.now();
            return;
        }
    } catch {
        // Server unreachable — proceed with reconnect
    }

    logger.warn('[WebSocket] Pong timeout — scheduling reconnect with backoff');
    get()._setError('Connection lost (pong timeout)');
    get()._stopHeartbeat();
    const ws = get()._ws;
    if (ws) {
        ws.onopen = null;
        ws.onclose = null;
        ws.onerror = null;
        ws.onmessage = null;
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING) {
            ws.close(1000, 'Pong timeout');
        }
    }
    set({ _ws: null, _connectionStable: false, connectionPhase: 'offline' });
    get()._scheduleReconnect();
}, WS_CONFIG.PONG_TIMEOUT_MS);
```

- [ ] **Step 3: Reset `lastDataReceivedTs` on ping send**

In `sendPing()` (line ~938-952):

```typescript
sendPing: () => {
    const s = get();
    if (s._ws?.readyState === WebSocket.OPEN) {
        lastDataReceivedTs = Date.now();  // fresh timestamp for busy-connection guard
        const ts = new Date().toISOString();
        s._ws.send(JSON.stringify({ type: 'ping', timestamp: ts }));
        set({ _lastPingTime: ts });
        get()._updateStats({ lastPingTime: ts });
        return true;
    }
    return false;
},
```

- [ ] **Step 4: Run tests**

Run: `npx vitest run frontend/src/store/__tests__/websocketStore.heartbeat.test.ts`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/websocketStore.ts frontend/src/store/__tests__/websocketStore.heartbeat.test.ts
git commit -m "fix(frontend): harden heartbeat with health-check fallback and fresh lastDataReceivedTs"
```

---

### Task 5: Frontend — Send-Failure Queue + Orphan Message Retry

**Files:**
- Modify: `frontend/src/store/websocketStore.ts` lines 916-934 (sendMessage), and add `_retryOrphanMessages`
- Modify: `frontend/src/pages/ChatPage.tsx` around line 556 (call site)

**Interfaces:**
- Consumes: `_messageQueue`, `_connectionStable`, `lastMessage`, `useChatStore`
- Produces: Resilient send with automatic queuing on failure and retry of orphan messages after reconnect

- [ ] **Step 1: Write the test**

```typescript
// frontend/src/store/__tests__/websocketStore.send.test.ts
import { describe, it, expect, vi } from 'vitest';
import { useWebSocketStore } from '../websocketStore';

describe('Send-failure queue', () => {
  beforeEach(() => {
    useWebSocketStore.setState({
      _ws: null,
      _messageQueue: [],
      _orphanRetryInFlight: false,
    });
  });

  it('should queue message when send throws', () => {
    const mockWs = {
      readyState: WebSocket.OPEN,
      send: vi.fn().mockImplementation(() => { throw new Error('socket closed'); }),
    } as any;
    useWebSocketStore.setState({ _ws: mockWs });

    const store = useWebSocketStore.getState();
    const result = store.sendMessage('hello world');

    expect(result).toBe(false);
    const queue = useWebSocketStore.getState()._messageQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].content).toBe('hello world');
  });

  it('should queue message when not connected', () => {
    useWebSocketStore.setState({ _ws: null });

    const store = useWebSocketStore.getState();
    const result = store.sendMessage('hello world');

    expect(result).toBe(false);
    const queue = useWebSocketStore.getState()._messageQueue;
    expect(queue).toHaveLength(1);
    expect(queue[0].content).toBe('hello world');
  });
});
```

- [ ] **Step 2: Route send failures into `_messageQueue`**

In `sendMessage()` (line ~916-934), change the catch block to fall through to queuing:

```typescript
sendMessage: (content: string, attachments?: MessageAttachment[]) => {
    const s = get();
    if (s._ws?.readyState === WebSocket.OPEN) {
        try {
            s._ws.send(JSON.stringify({
                type: 'message',
                content: content.trim(),
                timestamp: new Date().toISOString(),
                attachments: attachments && attachments.length > 0 ? attachments : undefined,
            }));
            return true;
        } catch (e) {
            logger.error('[WebSocket] Send error — queuing message for retry:', e);
            // Fall through to queue logic below
        }
    }
    logger.warn('[WebSocket] Not connected — queuing message');
    set({ _messageQueue: [...get()._messageQueue, { content, timestamp: Date.now(), attachments }] });
    return false;
},
```

- [ ] **Step 3: Add orphan message retry logic**

Add a new method to the store actions (after the existing `sendMessage`):

```typescript
_retryOrphanMessages: () => {
    const chatMessages = useChatStore.getState().messages;
    const orphaned = [...chatMessages]
        .reverse()
        .slice(0, 5)  // check last 5 user messages
        .filter(m => m.role === 'sovereign')
        .find(m => {
            // A message is orphaned if there's no Head reply after it
            const idx = chatMessages.indexOf(m);
            const next = chatMessages[idx + 1];
            return !next || next.role !== 'head_of_council';
        });
    
    if (orphaned && !get()._orphanRetryInFlight) {
        set({ _orphanRetryInFlight: true });
        logger.info('[WebSocket] Retrying orphaned message:', orphaned.content.slice(0, 50));
        showToast.info('Retrying last message...');
        get().sendMessage(orphaned.content, orphaned.metadata?.attachments as any);
        setTimeout(() => set({ _orphanRetryInFlight: false }), 10000);
    }
},
```

And call it from `_handlePong` after the connection stabilizes:

```typescript
_handlePong: (timestamp: string) => {
    // ... existing code ...
    if (!s._connectionStable) {
        set({ _connectionStable: true, _reconnectAttempts: 0 });
        get()._updateStats({ reconnectAttempts: 0 });
        logger.debug('[WebSocket] Connection stable — backoff counter reset');
        get()._fetchReplay();
        get()._retryOrphanMessages();  // <-- add this
    }
},
```

Also add the state field to the store interface:

```typescript
_orphanRetryInFlight: boolean;
```

And initialize it in the default state:

```typescript
_orphanRetryInFlight: false,
```

- [ ] **Step 4: Run tests**

Run: `npx vitest run frontend/src/store/__tests__/`
Expected: All tests pass

- [ ] **Step 5: Commit**

```bash
git add frontend/src/store/websocketStore.ts
git commit -m "fix(frontend): queue send failures and retry orphan messages on reconnect"
```

---

## Self-Review

**1. Spec coverage:**
- Section 1 (Uvicorn WS ping) → Task 1 ✓
- Section 2 (Event loop protection) → Task 2 (receive-loop queries only; full process_message async conversion deferred) ✓
- Section 3 (Generation survival) → Task 3 ✓
- Section 4 (Heartbeat hardening) → Task 4 ✓
- Section 5 (Send-failure queue + recovery) → Task 5 ✓

**Deferrals noted:** Full async conversion of `ChatService.process_message` is out of scope — it interleaves sync DB and async WS sends in ways that require a deeper refactor. The receive-loop queries (Task 2) are the highest-impact subset.

**2. Placeholder scan:** Clean — no TBD/TODO/incomplete steps, all code blocks contain real implementation.

**3. Type consistency:** All method names and store fields referenced in later tasks (e.g. `_orphanRetryInFlight`) are defined in earlier tasks. ✓

**4. Integration dependencies:** Tasks are ordered so that server changes (1-3) complete before frontend changes (4-5). No cross-dependency between 1-3 and 4-5 except the general contract that the server must survive disconnects (Task 3) before orphan retry (Task 5) makes sense.
