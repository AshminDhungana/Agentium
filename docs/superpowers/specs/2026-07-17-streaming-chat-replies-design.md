# Streaming Assistant Replies (Task 10.1) — Design

**Date:** 2026-07-17
**Status:** Approved (design), pending implementation plan
**Priority:** P1

## Problem

The live chat reply path is fully blocking. A user message travels over the
`/chat` WebSocket to `ChatService.process_message`, which runs an agentic
tool-call loop (`generate_with_tools`, no `stream=True`), waits for the entire
reply, then pushes one complete `{"type":"message"}` event back. The user stares
at a "thinking" state until the full answer lands — unlike standard messaging-app
UX. Legacy SSE code exists in the frontend (`frontend/src/services/chatStream.ts`,
`chatStore.sendStreamingMessage`) but has no backend route and is not wired into
`ChatPage`; it is dead code.

## Goal

Stream assistant replies token-by-token (chunk-by-chunk) end to end — provider
stream → WebSocket → incremental frontend render — matching standard chat-app UX,
with a stop control and graceful fallback for providers that cannot stream.

## Key Constraint

Replies are **not** a single completion: they run a multi-turn agentic tool-call
loop. Only the **final text turn** (after tools resolve) is meaningful to stream.
Tool iterations run silently, as they do today.

## Decisions (from brainstorming)

| Topic | Decision |
|---|---|
| Transport | Reuse the existing `/chat` WebSocket; add new event types |
| What streams | Only the final text answer; tool loops run silently |
| Provider scope | OpenAI-compatible (OpenAI/Groq/Ollama/compatible) + Anthropic; graceful blocking fallback for the rest |
| Persistence / side-effects | Stream deltas live; persist + log tokens/cost + emit metadata only on completion (unchanged logic) |
| Frontend UX | Live markdown + blinking caret, finalize on end; auto-scroll when near bottom; typing indicator during thinking phase |
| Stop control | Yes — Send button becomes Stop; cancel over WebSocket aborts stream, persists partial, emits end |
| Non-LLM replies (governance fast-path, cards) | Delivered whole as `message_start` + `message_end`, zero deltas (atomic, no fake typing) |

## Chosen Approach: A — Callback-based streaming through the existing loop

Add an optional async `on_delta` callback (and an `asyncio.Event` `cancel_event`)
threaded down through the call chain. The tool loop is untouched; on the final
text turn the provider is called with `stream=True` and each chunk is forwarded to
`on_delta`. When `on_delta is None`, behavior is byte-for-byte identical to today,
so blocking callers (agents, tests, non-chat flows) are unaffected. Persistence
and metadata run after the stream completes, reusing the existing code verbatim.

Rejected: **B** (separate `stream_message` method) — duplicates `process_message`
logic, high drift risk. **C** (async generators all the way up) — large refactor
of signatures shared by non-streaming callers, highest blast radius.

## Architecture

### Event Contract (over `/chat` WebSocket)

Each reply is keyed by a server-generated `stream_id` (UUID). Every reply emits
exactly one `message_start` and one `message_end`; `message_delta` count is 0..N.

**Server → client:**

```jsonc
// once, when a reply begins
{ "type": "message_start", "stream_id": "uuid", "role": "head_of_council",
  "message_id": "server-id", "timestamp": "ISO" }

// repeatedly — one per token/chunk of the FINAL text turn
{ "type": "message_delta", "stream_id": "uuid", "delta": "partial text" }

// once at the end — full content + all metadata/side-effects
{ "type": "message_end", "stream_id": "uuid", "content": "full final text",
  "metadata": { "model": "...", "tokens_used": 0, "task_created": false,
                "task_id": null, "card": null, "media_urls": [] },
  "finish_reason": "stop | stopped_by_user | error", "timestamp": "ISO" }
```

**Client → server (new):**

```jsonc
{ "type": "cancel", "stream_id": "uuid" }
```

Rules:
- `message_id` is server-assigned in `message_start` so frontend dedup
  (`processedMessageIds`) and history reconcile cleanly.
- Non-LLM replies: `message_start` immediately followed by `message_end` with full
  content, zero deltas.
- Non-streaming / fallback providers: same contract, zero deltas, `message_end`
  carries the full blocking result.
- Mid-stream error: `message_end` with `finish_reason:"error"` and whatever partial
  `content` exists.
- Only `message_start` / `message_end` are buffered to the Redis replay buffer;
  `message_delta` events are NOT buffered (a reconnecting client gets the final
  message, not a token replay).

### Backend Streaming Path (Approach A seam)

```
websocket.py (/chat handler)
  └─ ChatService.process_message(..., on_delta, cancel_event)
       └─ LLMClient.generate_with_tools(..., on_delta, cancel_event)
            └─ ModelService.generate_with_agent_tools(..., on_delta, cancel_event)
                 └─ Provider.generate_with_tools(..., on_delta, cancel_event)
```

- Signature additions: `on_delta: Optional[Callable[[str], Awaitable[None]]] = None`,
  `cancel_event: Optional[asyncio.Event] = None`. `on_delta is None` ⇒ current
  blocking behavior, unchanged.
- Inside `Provider.generate_with_tools` (`backend/services/model_provider.py`,
  OpenAI-compatible at ~line 547; Anthropic path in `AnthropicProvider`):
  - Tool-call loop iterations run as now (blocking; tools resolve silently).
  - When `on_delta` is provided, call the API with `stream=True` and accumulate
    chunks into `content` while `await on_delta(chunk_text)` per chunk.
  - Forward deltas only for **text** content; tool-call-only turns produce no text
    deltas, so the user sees nothing until the real answer streams. This satisfies
    "final text only" without pre-detecting which turn is final.
  - Read token/usage from the final stream chunk; if the provider omits usage on
    streamed responses, estimate from accumulated content via the existing cost
    util so logging/budget are not skipped.
  - If `on_delta is None`, use the existing non-streaming `create()` call.
- Cancellation: check `cancel_event.is_set()` while iterating stream chunks; if set,
  stop consuming, break the loop, return accumulated `content` with
  `finish_reason="stopped_by_user"`.
- After the stream, `ChatService.process_message` runs its existing logic
  unchanged: persist the full assistant turn, log tokens/cost/latency, compute
  metadata (task_created, cards, media_urls), return the same dict as today.
- Fallback: if a provider/model can't stream (or streaming raises before any delta),
  catch and fall back to the blocking `create()`, delivered as a single
  `message_end` (zero deltas). Anthropic uses its own SDK streaming path but the
  same callback contract.

### WebSocket Handler Orchestration (`backend/api/routes/websocket.py`)

The `message` handler (currently ~lines 602–612) changes from "await full response,
send one event" to orchestrating the stream lifecycle:

```
on receive {"type":"message", ...}:
  stream_id  = uuid4()
  message_id = server-assigned id
  active_streams[stream_id] = asyncio.Event()          # per-connection dict
  send message_start(stream_id, message_id, role)

  async def on_delta(text):
      await websocket.send_json(message_delta(stream_id, text))

  # run reply as a task so the receive loop can process `cancel` concurrently
  task = create_task(ChatService.process_message(
             head, enriched_message, db,
             on_delta=on_delta, cancel_event=active_streams[stream_id]))
  try:
      response = await task
      send message_end(stream_id, content=response.content,
                       metadata=response.metadata,
                       finish_reason=<stop|stopped_by_user>)
  except Exception:
      send message_end(stream_id, content=<partial or "">, finish_reason="error")
  finally:
      active_streams.pop(stream_id, None)

on receive {"type":"cancel", stream_id}:
  ev = active_streams.get(stream_id)
  if ev: ev.set()
```

- `active_streams` is scoped to the single WebSocket connection (local dict), so
  cancel only affects that user's own reply.
- The one structural change: reply generation becomes an `asyncio.create_task` so
  the receive loop keeps reading `cancel`/`ping` while the task runs.
- Preserved: auth gate, Redis event buffer/replay (start/end only), dedup via
  `message_id`, `system_not_ready` guard.
- Governance fast-path / cards: `process_message` returns without ever calling
  `on_delta`, so the handler naturally emits `message_start` + `message_end` with
  zero deltas.

### Frontend (`frontend/src/`)

**`store/chatStore.ts`** — activate the existing streaming fields:
- Reuse `currentStreamingMessage` (already present, ~line 47).
- Add `beginStream(message_id, role)`, `appendDelta(text)`, `endStream(finalMessage)`.
- `beginStream` inserts a placeholder assistant `Message` with `status:'streaming'`
  and empty content.
- `appendDelta` mutates that message's `content += delta` (in-place by id).
- `endStream` sets final `content`, `metadata`, `status:'complete'`; dedup via
  server `message_id`.

**`pages/ChatPage.tsx`** — WS subscriber (replaces the single-`message` handler
at ~lines 280–326):
- `message_start` → `beginStream`; keep `isAwaitingReply` true until first delta;
  register active `stream_id`.
- `message_delta` → `appendDelta`; on first delta set `isAwaitingReply(false)`.
- `message_end` → `endStream`; attach metadata (fire `registerCard` / task toast as
  today); clear active `stream_id`.
- Backward-compat: keep handling legacy `type:'message'` as an atomic start+end.

**Rendering (`components/chat/MarkdownMessage.tsx`):**
- Live markdown rendering during stream; tolerate unterminated code fences / bold
  (render best-effort, finalize cleanly on `message_end`).
- Blinking caret (`▍`) while `status === 'streaming'`, CSS blink ~1s, removed on
  complete. Respects `prefers-reduced-motion` (solid caret, no blink).

**Typing indicator:** between `message_start` and the first `message_delta` (the
thinking / tool phase), show the existing typing indicator in the placeholder
bubble — satisfies "feedback within 300ms."

**Auto-scroll:** follow the stream to bottom on each delta only if the user is
already near the bottom; if scrolled up, do not yank them down.

**Stop button:** while a `stream_id` is active, the Send button becomes a Stop
button (square icon, ≥44px target, clear pressed state). Click →
`sendWsMessage({type:'cancel', stream_id})`. On `message_end` with
`finish_reason:'stopped_by_user'`, partial content stays rendered, caret removed,
button reverts to Send.

## Error Handling & Edge Cases

- **Provider stream error mid-flight** → backend attempts blocking fallback if
  nothing streamed yet; if partial content exists, stops and emits `message_end`
  with `finish_reason:"error"` + partial content. Frontend renders partial, removes
  caret, shows a subtle inline error affordance.
- **Provider doesn't support streaming** → blocking fallback; `message_start` +
  `message_end`, zero deltas. Transparent to the frontend.
- **WebSocket disconnect mid-stream** → deltas are lost (not buffered); on reconnect
  the client gets the final persisted message via history/replay. No partial-DB rows
  (persistence only at completion).
- **Cancel after completion** → `stream_id` already popped; no-op.
- **Concurrent replies on one connection** → each has its own `stream_id` +
  `cancel_event`; frontend keys streaming state by `stream_id`.
- **Empty final content** (all output was tool calls) → zero deltas, `message_end`
  with empty content — same as today.
- **`prefers-reduced-motion`** → no blinking caret / typewriter smoothing; text
  still updates on deltas.

## Testing

- **Backend unit:** `provider.generate_with_tools` with a mocked streaming client —
  asserts `on_delta` called per chunk, accumulated `content` correct, `cancel_event`
  halts consumption, `on_delta=None` path byte-identical to blocking, fallback path
  when stream raises.
- **Backend integration** (extend `backend/tests/integration/test_provider_mock_wiring.py`):
  `ChatService.process_message` with `on_delta` collects deltas; persistence + token
  logging still run once at end; governance fast-path emits zero deltas.
- **WebSocket handler:** simulate `message` then `cancel`; assert
  `message_start` → deltas → `message_end` ordering and that cancel yields
  `finish_reason:"stopped_by_user"`.
- **Frontend:** store reducer tests for `beginStream/appendDelta/endStream` (content
  accrual, dedup, status transitions); component test that caret shows during
  `streaming` and clears on complete.
- Respect the repo's `pytest --cov-fail-under` threshold; run frontend lint/typecheck.

## Out of Scope (YAGNI)

- Incremental DB persistence of partial content.
- Token-replay on reconnect (only final message is replayed).
- Streaming intermediate tool-turn text.
- Fake-typewriter animation for canned/non-LLM responses.
- Streaming for Google and other SDKs beyond the blocking fallback.

## Key File References

| Concern | File | Location |
|---|---|---|
| WS chat endpoint / reply event | `backend/api/routes/websocket.py` | 488, 602–612 |
| ChatService.process_message | `backend/services/chat_service.py` | 71, 190, 274, 454 |
| Governance fast-path short-circuit | `backend/services/chat_service.py` | 157–187 |
| LLMClient.generate_with_tools | `backend/core/llm_client.py` | 350, 398 |
| ModelService.generate_with_agent_tools | `backend/services/model_provider.py` | 1146, 1270 |
| Provider.generate_with_tools (loop, no stream) | `backend/services/model_provider.py` | 547–712 |
| Existing streaming provider method (unused by chat) | `backend/services/model_provider.py` | 378, 512, 800 |
| ChatPage WS listener | `frontend/src/pages/ChatPage.tsx` | 280–326, 497 |
| chatStore Message / streaming fields | `frontend/src/store/chatStore.ts` | 34, 47, 99 |
| Legacy SSE (dead code, to remove/repurpose) | `frontend/src/services/chatStream.ts` | 28–114 |
