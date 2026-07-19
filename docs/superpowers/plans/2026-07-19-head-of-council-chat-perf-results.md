# Head of Council Chat Performance — Before / After Benchmark

- **Branch:** `feature/head-chat-perf` (Tasks 1–5 merged)
- **Date:** 2026-07-19
- **Author:** Task 6 (benchmark) agent
- **Headline change:** the primary WebSocket chat path (`ChatService.process_message`)
  now performs **ONE** LLM round-trip — the model emits the `decide` routing action
  in the same generation call — and `message_end` is no longer blocked by task
  creation / media interception (those run in background tasks).

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

## 1. Round-trip reduction (STATICALLY VERIFIED)

### Finding: before = 2 round-trips, after = 1 on the primary path

**Before this branch (legacy `analyze_for_task` path):**
1. `process_message` → `provider.generate(...)` → **LLM call #1** (reply)
2. `process_message` → `analyze_for_task(...)` → `DecisionEngine().decide(...)` → **LLM call #2** (routing decision)

**After this branch (primary WebSocket path):**
1. `process_message` → `provider.generate(...)` with the `decide` tool injected → **LLM call #1** (reply **and** routing action in one generation)
2. Classification is read for free from the tool call: `classify_action_from_result(result)` — **no LLM call**
3. Task creation is handed to `_create_task_background` via `asyncio.create_task` — **no LLM call**

### Evidence

- `backend/services/chat_service.py:522` — `decision = ChatService.classify_action_from_result(result)`
  (reads the `decide` tool call from the single generation; no extra LLM call).
- `backend/services/chat_service.py:533` — task creation scheduled with
  `asyncio.create_task(ChatService._create_task_background(...))` (off the hot path).
- `backend/services/chat_service.py:902` — `DecisionEngine().decide(...)` exists **only
  inside `analyze_for_task`** (the secondary / legacy path), NOT in `process_message`.
- `backend/services/agent_orchestrator.py:307` — the other `DecisionEngine().decide`
  call site is the **orchestrator**, not the chat hot path.
- `backend/api/routes/chat.py:542` — `analyze_for_task(...)` is called **only** from the
  REST streaming endpoint (`_stream_response`), confirming the primary WebSocket path
  no longer invokes it.

```
grep -rn "DecisionEngine().decide" backend/
  backend/services/agent_orchestrator.py:307   (orchestrator — not chat hot path)
  backend/services/chat_service.py:902         (inside analyze_for_task — secondary path)
```

**Conclusion:** On the primary chat path, LLM round-trips dropped from **2 → 1**.

---

## 2. `message_end` decoupling (STATICALLY VERIFIED)

`process_message` does **not** await task creation or media interception inline.

### Evidence

- `backend/services/chat_service.py:492` — `asyncio.create_task(ChatService._media_and_persist_background(...))`
  (media download/rewrite + Head-turn persistence run fire-and-forget).
- `backend/services/chat_service.py:532` — `asyncio.create_task(ChatService._create_task_background(...))`
  for task creation + deliberation startup.
- `backend/services/chat_service.py:542` — `task_info = {"created": True, "task_id": None, "pending": True}`
  is set **immediately**, without awaiting the DB task creation. The real status
  (`task_id`) arrives later via the `task_created` WebSocket event
  (see `backend/services/chat_service.py:812` broadcast).
- `backend/services/chat_service.py:780` — `_create_task_background` opens its **own**
  `SessionLocal()` (the caller's session is already closed) and broadcasts
  `{"type": "task_created", ...}`, so `message_end` is never blocked by task work.

**Conclusion:** `message_end` is decoupled from task creation and media interception.
Real status is delivered asynchronously via the `task_created` event.

---

## 3. Comparison table

| Metric | Before (`main`) | After (`feature/head-chat-perf`) | Source |
|---|---|---|---|
| LLM round-trips / chat message (primary WebSocket path) | 2 (generate + `DecisionEngine().decide`) | 1 (generate only; `decide` emitted as tool call) | STATICALLY VERIFIED |
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

1. **LLM round-trips on the primary chat path reduced 2 → 1** (routing decision
   now emitted as a `decide` tool call in the single generation; `analyze_for_task` /
   `DecisionEngine().decide` remain only on the secondary REST streaming path).
2. **`message_end` is decoupled** from task creation and media interception, both
   moved to `asyncio.create_task` background coroutines; the real task status is
   delivered via the `task_created` WebSocket event.

**Real wall-clock latency numbers are NOT captured** in this document because the
build environment lacked a runnable stack (`make` unavailable on this host) and a
configured LLM API key. The procedure above should be run when infrastructure is
available to fill in the four PENDING INFRA cells.
