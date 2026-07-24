# WebSocket Disconnect & Message Recovery Design

**Date:** 2026-07-24
**Status:** Draft
**Domain:** project
**Tags:** websocket, chat, session, heartbeat, reconnect, message-delivery

## Overview

The Head of Council WebSocket connection drops spontaneously during idle periods. When this happens during an in-flight generation, the reply is never persisted and the user's message is left with no response. This design addresses all three layers: connection stability, message survival, and message recovery.

## Root Cause Analysis

Three independent factors combine to produce the bug:

1. **Uvicorn WS ping interval** (default 20s) operates at the RFC 6455 frame level. It races with the app-level JSON ping (30s) and can preemptively close the server-side socket if its protocol-level pong is delayed.

2. **Synchronous SQLAlchemy calls** (`db.commit()`, `db.query()`) inside the async WS handler (`_run_generation` / `ChatService.process_message`) block the asyncio event loop for 10-50ms per call. If a client ping arrives during this window, pong processing is delayed. Over hours of connection, these collisions accumulate and eventually overlap the 10s pong timeout window.

3. **No recovery mechanism** for in-flight messages after disconnect. The generation task is cancelled on `WebSocketDisconnect`, the background persistence task (`chat_service.py:517`) never runs, and the reply is lost permanently.

## Design Decisions

### Approach Chosen: Hybrid Client-Server Hardening (A+B)

Both server-side connection stability and client-side heartbeat/recovery fixes. All changes scoped to the WebSocket chat path — no architectural rewrites.

## Section 1: Server — Uvicorn WS Ping Aligned

**File:** `backend/main.py:1090-1096`

Change: Pass `ws_ping_interval=60, ws_ping_timeout=60` to `uvicorn.run()`.

Rationale: Setting to 0 via the CLI flag `--ws-ping-interval 0` does not reliably disable the feature in all uvicorn versions (GitHub issue encode/uvicorn#1609 — `None` falls back to defaults). A high aligned value gives the app-level 30s ping/pong three round-trips of slack without interference.

## Section 2: Server — Event Loop Protection

**Files:** `backend/api/routes/websocket.py`, `backend/services/chat_service.py`

Wrap synchronous SQLAlchemy calls in the WS-critical path with `loop.run_in_executor(None, ...)`:

- `get_fresh_db()` / `db.query()` for Head-of-Council lookup inside `_run_generation` (`websocket.py:~685`)
- `db.add()` / `db.commit()` for user message persistence (`chat_service.py:~222-235`)
- `db.add()` / `db.commit()` for Head-turn persistence (`chat_service.py:~928-940`)

Scope: Only the WS-handler-adjacent path. REST endpoints and Celery tasks are unaffected (run in separate threads/processes). Full async SQLAlchemy migration is a separate project.

## Section 3: Server — Generation Survival on Disconnect

**File:** `backend/api/routes/websocket.py:752-755`

Remove the `for t in pending_tasks.values(): t.cancel()` loop from the `WebSocketDisconnect` handler. Let the generation task complete normally:

- The `on_delta` callback already catches `send_json` failures silently (`except Exception: pass` at line 661)
- The `message_end` send (line 704) is inside a `try` block — if it fails, the `except Exception` handler (line 727) attempts an error `message_end`
- Even if both fail, the background persistence task (`chat_service.py:517`) runs and persists the Head's reply
- The task naturally frees itself when done via `finally` (line 737)

On reconnect, the frontend loads chat history via REST and sees the completed reply (which was persisted by the background task).

## Section 4: Frontend — Heartbeat Hardening

**File:** `frontend/src/store/websocketStore.ts:466-507`

Two-part mitigation:

**4a. Secondary health check before killing.** When the pong timeout fires, before tearing down the socket, make a lightweight HTTP GET to `/api/health` (5s timeout). If it succeeds, the server is alive — extend the grace period and skip the reconnect. Only kill when both WS pong AND HTTP health check fail.

**4b. Reset `lastDataReceivedTs` on ping send.** In `sendPing()`, update `lastDataReceivedTs` to `Date.now()` before sending. This gives the busy-connection guard a fresh timestamp even before the pong arrives, preventing the guard from using a 30s-stale timestamp during idle periods.

## Section 5: Frontend — Send-Failure Queue + Message Recovery

**File:** `frontend/src/store/websocketStore.ts:916-934`

**5a. Route send failures into `_messageQueue`.** In `sendMessage()`, when the `ws.send()` throws (socket closes between `readyState` check and actual send), fall through to the queuing logic instead of just logging and returning `false`.

**5b. Retry orphan messages on reconnect.** After reconnection stabilizes (first successful pong), scan the last N user messages in chat history. If any have no corresponding Head reply, emit a toast and auto-retry the message via `sendMessage()`. Track retries with `_orphanRetryInFlight` to prevent duplicate retry loops.

## Testing

- Unit test: heartbeat health check fallback (mock fetch, verify reconnect is skipped on 200)
- Integration: simulate WS disconnect mid-generation, verify reply appears in history after reconnect
- Integration: verify no duplicate generation after reconnect (old task completed, new task not spawned for same message)
- Manual: long-idle WebSocket (5+ minutes), verify no spontaneous disconnection

## Files Changed

| File | Change |
|------|--------|
| `backend/main.py` | Add `ws_ping_interval=60, ws_ping_timeout=60` to uvicorn |
| `backend/api/routes/websocket.py` | Remove task cancellation on disconnect; wrap sync DB in executor |
| `backend/services/chat_service.py` | Wrap sync DB calls in executor |
| `frontend/src/store/websocketStore.ts` | Heartbeat hardening, send-failure queue, orphan retry |
| `frontend/src/pages/ChatPage.tsx` | Handle orphan message retry UI |
