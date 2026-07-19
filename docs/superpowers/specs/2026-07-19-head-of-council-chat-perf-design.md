# Optimize Head of Council Chat Performance — Design

**Date:** 2026-07-19
**Status:** Approved (design)
**Domain:** Backend / Chat (Sovereign ↔ Head of Council)

## 1. Problem & Principle

The Head of Council (agent `00001`) is the Sovereign's direct representative. Per the
documented architecture (`README.md`, `docs/documents/architectural_breakdown.md`) the
Head's role is:

> "Head validates intent + constitutional compliance" → "Council/Lead/Task execute" →
> "Results aggregated → Head → Sovereign (2–3 line response only)".

The Head is an **interpreter / delegator**, never an executor.

The current chat path (`ChatService.process_message`,
`backend/services/chat_service.py:119`) violates this in two ways:

1. It generates a **full conversational reply inline for every message**, including
   execution-type requests where the docs say it should return only a 2–3 line ack and
   hand off.
2. After generation it performs a **second full LLM round-trip** (`analyze_for_task` →
   `DecisionEngine.decide` → `llm.decide`, `backend/services/decision_engine.py:53`) to
   decide whether to create a task, and the final `message_end` frame waits for all of
   this before returning.

Task *execution* itself is already delegated (async via Celery
`task_executor.execute_task_async`), so the work is to remove the Head's own
synchronous overhead on the critical path, not to re-plumb execution.

## 2. Current Request Flow (and where time is spent)

Primary path is the WebSocket endpoint
(`backend/api/routes/websocket.py:489`); the REST `/chat/send` streaming path
(`backend/api/routes/chat.py:459`) mirrors it.

Inside `ChatService.process_message`:

| # | Step | Location | Cost on critical path |
|---|------|----------|-----------------------|
| 1 | model config load + fallback | chat_service.py:124–156 | DB, light |
| 2 | load chat history / build context | chat_service.py:182–213 | DB |
| 3 | persist inbound turn | chat_service.py:215–230 | DB |
| 4 | governance-command fast-path | chat_service.py:238–272 | DB + service (short-circuits LLM) |
| 5 | **full system-context scan** (all agents + tasks) | `get_system_context` chat_service.py:621 → prompt at :342 | DB full scan, per message |
| 6 | **main LLM generation** (streams deltas) | `generate_with_tools` chat_service.py:369 | **dominant** |
| 7 | media interception (download URLs) | chat_service.py:461–477 | network, on path |
| 8 | persist Head turn | chat_service.py:484–505 | DB |
| 9 | channel broadcast | chat_service.py:507–515 | fire-and-forget (create_task) |
| 10 | **2nd LLM call** for task decision | `analyze_for_task` → `DecisionEngine.decide` chat_service.py:518 | **+1 full round-trip** |
| 11 | reincarnation check / trigger | chat_service.py:528–578 | DB + possible spawn |

`message_end` (websocket.py:645 / chat.py:542) is not sent until `process_message`
fully returns, so steps 7–11 delay the final frame and its `task_created` metadata.

## 3. Proposed Changes

### 3.1 Single-pass intent classification (removes the 2nd LLM call)
Fold the `REPLY` vs `DELEGATE/CREATE_TASK` decision into the **main** generation. The
Head already calls `generate_with_agent_tools`, which supports tool/structured output.
The model both produces the conversational reply (streamed as deltas) and emits a
classification action (`reply` | `create_task` | `delegate` | `dispatch_task`) in the
same call.

- Replace the post-generation `analyze_for_task` → `DecisionEngine.decide` second call
  with parsing the action already returned by the main generation.
- Keep `DecisionEngine` as the canonical decision *representation*; callers that need a
  standalone decision (no streaming reply) can still use it directly.
- Net effect: one model round-trip per message instead of two.

### 3.2 Decouple task creation from `message_end`
When the generation yields a delegation action, create the Task **in a background task**
(the async task machinery already exists) and report `task_created` / `task_id` /
progress via a **follow-up WebSocket event** rather than blocking `message_end`.

- `message_end` is sent as soon as the streamed reply + classification are complete.
- A new `task_created` / `task_progress` WebSocket event (reusing `ConnectionManager`
  broadcast) carries the delegation result when the background task commits.
- The Head's on-screen reply for execution requests is capped to the 2–3 line ack
  (already partially enforced at chat.py:544); apply it specifically on the delegate path.

### 3.3 Trim pre-generation overhead
- **Cache `get_system_context`** with a 20 s TTL. System state (agent
  counts, pending task counts) changes slowly relative to chat cadence; a stale-by-a-few-
  seconds snapshot is acceptable for the prompt.
- **Parallelize** the history/context build (step 2) with config + provider setup
  (steps 1, 5) so they run concurrently before the generation call.
- No full-table scan on the critical path before the first token.

### 3.4 Boundaries (what the Head does vs delegates)

**Head does directly**
- Interpret the Sovereign's request.
- Constitutional-compliance check (via existing Constitutional Guard).
- Route decision (REPLY vs DELEGATE/CREATE_TASK/DISPATCH).
- Short ack / summary (2–3 lines on delegate path).
- Monitor execution status and report results back.

**Always delegated to sub-agents (existing async machinery)**
- Task execution, code generation, DAG planning (Lead), research/RAG.
- Council deliberation / voting, resource allocation.
- Critic review (Plan/Code/Output).

### 3.5 Move non-essential work off the critical path
- Media interception (URL download + store): already fire-and-forget-friendly; ensure it
  never blocks `message_end`. If it must rewrite content, do it before streaming starts
  or as a background rewrite that updates the stored message.
- Channel broadcast: already `asyncio.create_task` (chat_service.py:507) — confirm it is
  not awaited on the critical path.
- Audit logging: schedule off the critical path where possible.

## 4. Acceptance Criteria

- End-to-end `message_start → first delta` latency is not regressed and ideally reduced
  (no full system-context scan or second LLM call before first token).
- `message_end` arrives as soon as the reply is streamed + classified (task creation no
  longer blocks it).
- Execution-type requests still create a Task and route to the async execution machinery
  (no functional regression).
- The 2nd LLM call for task classification is eliminated for the normal chat path.
- Head reply for delegation requests is concise (2–3 lines) with a follow-up task event.

## 5. Testing & Measurement

- Reuse the harness in `docs/chat-context-benchmark.md` to measure, **before vs after**:
  - `message_start → first delta` (time to first token)
  - `message_start → message_end` (full turn latency)
  - number of LLM round-trips per message
- Unit tests:
  - single-pass classification emits correct action for REPLY and DELEGATE prompts
  - `message_end` no longer awaits task creation
- Integration tests (extend `tests/integration/test_ws_stream.py`,
  `tests/integration/test_chat_spawn_command.py`):
  - execution request still creates + dispatches a task
  - `task_created` arrives via a follow-up event, not inside `message_end`

## 6. Risks / Non-goals

- **Non-goal:** changing the agentic execution loop or Council/Lead orchestration — only
  the Head's *chat* critical path.
- **Risk:** caching system context could show slightly stale agent counts in the prompt —
  mitigated by short TTL and the fact that this is descriptive context, not a control
  signal.
- **Risk:** media interception rewrite timing — mitigated by persisting original content
  immediately and rewriting asynchronously.
