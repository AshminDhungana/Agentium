# Head of Council Chat Performance — Before / After Benchmark

- **Branch:** `feature/head-chat-perf` (Tasks 1–5 merged)
- **Date:** 2026-07-19
- **Author:** Task 6 (benchmark) agent
- **Headline change:** the **separate blocking `DecisionEngine().decide` call has been
  removed from the chat hot path** — the routing decision is now emitted as a `decide`
  tool call inside the existing generation — and `message_end` is no longer blocked
  by task creation / media interception (those run in background tasks). The LLM
  generation *count* on the primary path is comparable to before (the `decide` tool
  call still executes inside the agentic loop and then runs a finalize generation);
  the real win is (a) eliminating the extra *blocking* decision call on the hot path
  and (b) decoupling `message_end` from task creation + media.

> ## ⚠️ Measurement status
>
> **This document mixes two kinds of evidence, clearly labelled:**
>
> - **STATICALLY VERIFIED** — derived from source code inspection (`grep`/`read`).
>   These claims are authoritative for the code on this branch.
> - **MEASURED** — real wall-clock latency (`t(first delta)`, `t(message_end)`).
>
> A live Docker stack (`make up`) plus a configured LLM API key were **NOT**
> available in the build environment (`make` is absent on this Windows host and
> no API key was configured). Therefore **no MEASURED latency numbers are
> captured here.** The procedure to capture them is documented in
> [Capturing real numbers](#capturing-real-numbers-procedure) so they can be
> filled in when infra is available.

---

## 1. Removal of the blocking decision call from the hot path (STATICALLY VERIFIED)

### Finding: the separate blocking `DecisionEngine().decide` call is gone from the hot path

**Before this branch (legacy `analyze_for_task` path):**
1. `process_message` → `provider.generate(...)` → LLM call #1 (reply)
2. `process_message` → `analyze_for_task(...)` → `DecisionEngine().decide(...)` → **LLM call #2** (a *separate, blocking* routing decision on the hot path)

**After this branch (primary WebSocket path):**
1. `process_message` → `provider.generate(...)` with the `decide` tool injected → the routing action is emitted **inside** this generation (no separate blocking decision call on the hot path)
2. Classification is read for free from the tool call: `classify_action_from_result(result)` — no extra blocking call
3. Task creation is handed to `_create_task_background` via `asyncio.create_task` — no LLM call

> Note: the `decide` tool call still executes within the model's agentic loop, which
> then runs a finalize generation — so the *total* generation count on this path is
> comparable to before. The benefit is removing the **separate blocking**
> `DecisionEngine().decide` call, not a 2→1 reduction in raw generations.

### Evidence

- `backend/services/chat_service.py:523` — `decision = ChatService.classify_action_from_result(result)`
  (reads the `decide` tool call from the single generation; no extra LLM call).
- `backend/services/chat_service.py:544` — task creation scheduled with
  `asyncio.create_task(ChatService._create_task_background(...))` (off the hot path).
- `backend/services/chat_service.py:937` — `DecisionEngine().decide(...)` exists **only
  inside `analyze_for_task`** (the secondary / legacy path), NOT in `process_message`.
- `backend/services/agent_orchestrator.py:307` — the other `DecisionEngine().decide`
  call site is the **orchestrator**, not the chat hot path.
- `backend/api/routes/chat.py:542` — `analyze_for_task(...)` is called **only** from the
  REST streaming endpoint (`_stream_response`), confirming the primary WebSocket path
  no longer invokes it.

```
grep -rn "DecisionEngine().decide" backend/
  backend/services/agent_orchestrator.py:307   (orchestrator — not chat hot path)
  backend/services/chat_service.py:937         (inside analyze_for_task — secondary path)
```

**Conclusion:** On the primary chat path, the **separate blocking**
`DecisionEngine().decide` call is removed (the decision is now a `decide` tool call
within the existing generation), and `message_end` is no longer blocked by task
creation / media. The raw generation count remains comparable to before.

---

## 2. `message_end` decoupling (STATICALLY VERIFIED)

`process_message` does **not** await task creation or media interception inline.

### Evidence

- `backend/services/chat_service.py:494` — `asyncio.create_task(ChatService._media_and_persist_background(...))`
  (media download/rewrite + Head-turn persistence run fire-and-forget).
- `backend/services/chat_service.py:544` — `asyncio.create_task(ChatService._create_task_background(...))`
  for task creation + deliberation startup.
- `backend/services/chat_service.py:553` — `task_info = {"created": True, "task_id": None, "pending": True}`
  is set **immediately**, without awaiting the DB task creation. The real status
  (`task_id`) arrives later via the `task_created` WebSocket event
  (see `backend/services/chat_service.py:833` broadcast).
- `backend/services/chat_service.py:800` — `_create_task_background` opens its **own**
  `SessionLocal()` (the caller's session is already closed) and broadcasts
  `{"type": "task_created", ...}`, so `message_end` is never blocked by task work.

**Conclusion:** `message_end` is decoupled from task creation and media interception.
Real status is delivered asynchronously via the `task_created` event.

---

## 3. Comparison table

| Metric | Before (`main`) | After (`feature/head-chat-perf`) | Source |
|---|---|---|---|
| Separate blocking `DecisionEngine().decide` on chat hot path | Yes (inline 2nd LLM call) | Removed (decision folded into the existing generation as a `decide` tool call); `message_end` no longer blocked by task creation / media | STATICALLY VERIFIED |
| `DecisionEngine().decide` on chat hot path | Yes | No (only in `analyze_for_task`, the REST/`_stream_response` path) | STATICALLY VERIFIED |
| `message_end` blocked by task creation | Yes (awaited inline) | No (`asyncio.create_task`) | STATICALLY VERIFIED |
| `message_end` blocked by media interception | Yes (inline) | No (`asyncio.create_task` `_media_and_persist_background`) | STATICALLY VERIFIED |
| Task still created for execution messages | Yes (inline) | Yes (via `_create_task_background` + `task_created` event) | STATICALLY VERIFIED |
| `t(first delta)` (chit-chat) | — | — | PENDING INFRA (MEASURED) |
| `t(first delta)` (execution) | — | — | PENDING INFRA (MEASURED) |
| `t(message_end)` (chit-chat) | — | — | PENDING INFRA (MEASURED) |
| `t(message_end)` (execution) | — | — | PENDING INFRA (MEASURED) |

---

## 4. Capturing real numbers (procedure)

When a Docker stack + API key are available:

```bash
# Baseline (main)
git checkout main
make up                      # or: docker compose up -d
# Connect to ws://.../ws/chat as the Sovereign, send:
#   - chit-chat: "hello"
#   - execution: "build a scraper"
# Record t(first delta) and t(message_end) from the WS frames per message.

# After (this branch)
git checkout feature/head-chat-perf
make restart
# Repeat the same two messages; record the same two timings.
```

For each message record:
- `t(first delta)` — time from send to first streamed content token.
- `t(message_end)` — time from send to the `message_end` frame.

Expected result (assert): number of LLM round-trips = 1 on this branch, and
`t(message_end)` is not regressed vs baseline while `task_created` still arrives
for the execution message (verified via the new event; check `Task` row +
deliberation started).

> Note: the existing token-context benchmark (`docs/chat-context-benchmark.md`)
> also applies — `estimated_tokens` and `raw_turn_count` are logged by
> `process_message` and returned under `metadata`, so token savings can be
> captured alongside latency.

---

## 5. Summary

The two perf claims are **statically verified** against the source:

1. **Separate blocking `DecisionEngine().decide` removed from the chat hot path**
   (the routing decision is now emitted as a `decide` tool call inside the existing
   generation; `analyze_for_task` / `DecisionEngine().decide` remain only on the
   secondary REST streaming path). The raw generation count is comparable to before.
2. **`message_end` is decoupled** from task creation and media interception, both
   moved to `asyncio.create_task` background coroutines; the real task status is
   delivered via the `task_created` WebSocket event.

**Real wall-clock latency numbers are NOT captured** in this document because the
build environment lacked a runnable stack (`make` unavailable on this host) and a
configured LLM API key. The procedure above should be run when infrastructure is
available to fill in the four PENDING INFRA cells.
