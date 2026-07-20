# Design: Head delegates, never executes — and stays responsive while busy (Issue 8.1)

**Date:** 2026-07-20
**Status:** Approved (prompt-only enforcement)
**Owner:** Agentium backend

## Problem

Two related chat-slowness symptoms were reported against the Head of Council
(`00001`):

1. **(a) Head executes instead of delegating.** When the Sovereign gives the
   Head a task, the Head sometimes performs the work itself (calling execution
   tools inline) instead of handing it to a Lead/Task agent. This blocks the
   Head from chatting and reporting status.
2. **(b) Head can't answer a new message while busy.** A prior in-flight task
   prevents the Head from responding to a subsequent message.

## Root cause (verified in code)

- `backend/services/chat_service.py::ChatService.process_message` (line ~394)
  calls `LLMClient.generate_with_tools(agent_tier="0xxxx", tools=gen_tools,
  tool_choice={"type": "auto"})` where `gen_tools` is the **full** 0xxxx tool
  set. That set includes both governance tools (`create_task`, `cast_vote`,
  `propose_amendment`, `spawn_agent`) **and execution tools** (`execute_command`,
  `read_file`, `write_file`, browser, git, etc.) plus `decide`. With
  `tool_choice="auto"` the model is free to call an execution tool *inline*;
  the LLM client executes it synchronously inside the chat turn, so the Head
  does the work itself and blocks.
- The WebSocket path (`backend/api/routes/websocket.py:724`) already runs each
  message's generation in its own `asyncio.create_task`, so the receive loop is
  not blocked across messages. The defect is the turn itself performing
  execution, not the transport.
- Delegation already works: a `decide` → `create_task` decision is already
  fire-and-forget via `_create_task_background` → Council deliberation →
  Lead/Task (`create_task_from_decision` at `chat_service.py:732`).

So the fix is to stop the Head from calling execution tools *during the chat
turn*, leaving execution entirely to the delegated task lifecycle.

## Decisions (confirmed with user)

- **Enforcement: prompt-only guardrail.** Strengthen the Head's chat system
  prompt to forbid direct execution. The deterministic safety net (intercept
  execution-tool calls at the `generate_with_tools` boundary and convert them to
  a delegated task) was considered but **explicitly excluded** by the user.
- **Head keeps governance/control tools:** `decide`, `create_task`,
  `cast_vote`, `propose_amendment`, `spawn_agent`. It governs and delegates; it
  does not execute.

## Design

### Change 1 — Strengthen Head chat prompt (delegate-only + non-blocking)

Append a "Governance & Delegation Protocol" instruction block to the Head's
chat `full_prompt` in `ChatService.process_message` (the block is added before
the existing `decide` instruction). Mirror the same instruction in
`backend/api/routes/chat.py::_stream_response`'s `full_prompt` for consistency.

The block instructs the model:

- Your role is **control + delegation only**. You are the Head of Council, not
  an execution worker.
- Always classify your action with the `decide` tool.
- For any work that requires execution (running commands, reading/writing
  files, browsing, git), emit a `create_task` / `dispatch_task` / `delegate` /
  `spawn_agent` decision. That work is performed by Lead/Task agents **off your
  critical path** (in the background). Never perform it yourself.
- **You MUST NOT call execution tools** (`execute_command`, `read_file`,
  `write_file`, browser, git) directly during this chat turn.
- Governance tools (`create_task`, `cast_vote`, `propose_amendment`,
  `spawn_agent`) are allowed and encouraged.

No change to `tool_choice` (kept `"auto"`) and no change to the tool registry —
this is purely a prompt-level guardrail, as requested.

### Change 2 — Keep the chat turn non-blocking by construction

Already largely in place:

- `process_message` returns the Head's reply + `task_created` flag immediately;
  the long-running execution lives in the delegated task (`_create_task_background`
  → deliberation → Lead/Task) and is never awaited inline.
- WebSocket spawns a per-message generation task (`websocket.py:724`).

Hardening for this change: confirm the contract that `process_message` never
awaits delegated-task execution, and that the UI receives the immediate
`task_created` WS event so it shows "task started" without waiting for execution
to finish. No new serialization or locking is introduced.

### Change 3 — excluded (deterministic safety net)

The deterministic intercept-and-convert at the `LLMClient.generate_with_tools`
boundary is intentionally **not** implemented (user decision: prompt-only).

### Change 4 — Tests

- **Unit:** An execution-intent message routed through `process_message` (with a
  stubbed/fake LLM that obeys the delegation prompt) yields a
  `create_task`/`dispatch`/`delegate`/`spawn` decision and does **not** invoke
  any execution tool. The Head reply is returned before the (fake) task runs.
- **Concurrency:** Send message #2 while message #1's delegated task is still
  running (fake slow task execution); assert message #2 receives its
  `message_end` / streamed reply *before* message #1's task completes. This
  proves the Head answers a new message while a prior task is in flight.
- Both tests run without the Docker stack (unit/integration-light, using fakes).

## Acceptance criteria mapping

- *Sending Head a task never blocks the chat channel* → execution moved fully to
  the delegated background task; chat turn returns immediately after
  classification + reply.
- *Head's own tool/execution activity does not appear inline in normal chat
  latency* → Head no longer calls execution tools in-chat (prompt guardrail);
  execution happens in Lead/Task agents.
- *Concurrency test confirms Head answers message #2 while task #1 is still
  running* → covered by Change 4 concurrency test.

## Risks / notes

- Prompt-only is best-effort: a model could still emit an execution tool call.
  If the acceptance test flakes in production, the deterministic safety net
  (Change 3) is the guaranteed fallback and can be added later.
- The protocol block is added only to the chat prompt, not to the Head's global
  `get_system_prompt()`, so other Head behaviors (e.g. host access, governance
  commands) are unaffected.
