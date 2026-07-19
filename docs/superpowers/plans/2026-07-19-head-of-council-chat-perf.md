# Head of Council Chat Performance — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Head of Council chat path fast by eliminating the second LLM round-trip for task classification, decoupling task creation from the final response frame, and trimming pre-generation overhead — without changing execution delegation.

**Architecture:** The Head already delegates task *execution* asynchronously (Celery `task_executor.execute_task_async`). This plan keeps that, but (1) folds the REPLY/DELEGATE decision into the single existing generation call (the model already emits tool calls; we add the `decide` tool), (2) creates the Task in a background task and reports it via a follow-up WebSocket `task_created` event so `message_end` returns as soon as the reply is streamed, and (3) caches the per-message system-context scan and moves media interception off the critical path.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2 (async session via `SessionLocal`), asyncio, existing `LLMClient` / `ModelService.generate_with_agent_tools`, `ConnectionManager` (WebSocket broadcast), `DecisionEngine`.

## Global Constraints

- File `backend/services/chat_service.py` is the central file; changes there must preserve the existing return-dict shape (`content`, `model`, `tokens_used`, `task_created`, `task_id`, `reincarnated`, …) consumed by `backend/api/routes/websocket.py:637` and `backend/api/routes/chat.py:391`.
- The Head must still create + route a Task for execution-type requests — no functional regression in task creation.
- System-context cache TTL = 20 s (exact value from spec).
- Keep `DecisionEngine` as the canonical decision representation; do not delete it.
- Follow existing patterns: fire-and-forget background work uses `asyncio.create_task(...)` with its **own** `SessionLocal()` (never reuse the caller's session after it closes).

---

### Task 1: Cache the per-message system-context scan

**Files:**
- Modify: `backend/services/chat_service.py` (add module-level cache + `get_cached_system_context`; change the call site at line ~304)
- Test: `tests/unit/test_chat_system_context_cache.py`

**Interfaces:**
- Consumes: `ChatService.get_system_context(db)` (existing, chat_service.py:621)
- Produces: `ChatService.get_cached_system_context(db)` — returns the same `str` as `get_system_context` but cached for 20 s.

- [ ] **Step 1: Write the failing test**

```python
import asyncio
import pytest
from backend.services import chat_service as cs


@pytest.mark.asyncio
async def test_system_context_cache_avoids_second_query(monkeypatch):
    calls = {"n": 0}

    async def fake_context(db):
        calls["n"] += 1
        return "- Head of Council: Active"

    monkeypatch.setattr(cs.ChatService, "get_system_context", staticmethod(fake_context))

    # First call hits the source.
    await cs.ChatService.get_cached_system_context(None)
    # Second call within TTL must be served from cache.
    await cs.ChatService.get_cached_system_context(None)
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_system_context_cache_expires(monkeypatch):
    calls = {"n": 0}

    async def fake_context(db):
        calls["n"] += 1
        return "- Head of Council: Active"

    monkeypatch.setattr(cs.ChatService, "get_system_context", staticmethod(fake_context))
    monkeypatch.setattr(cs, "_SYSTEM_CONTEXT_TTL", -1.0)  # force expiry

    await cs.ChatService.get_cached_system_context(None)
    await cs.ChatService.get_cached_system_context(None)
    assert calls["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_chat_system_context_cache.py -v`
Expected: FAIL (`get_cached_system_context` not defined / `_SYSTEM_CONTEXT_TTL` missing).

- [ ] **Step 3: Write minimal implementation**

In `backend/services/chat_service.py`, near the top (after imports, before `class ChatService`), add:

```python
import time

_SYSTEM_CONTEXT_TTL = 20.0
_system_context_cache: dict = {"ts": 0.0, "value": None}
```

Inside `class ChatService`, add (as a `@staticmethod`):

```python
@staticmethod
async def get_cached_system_context(db: Session) -> str:
    """
    Return the descriptive system context used in the Head's prompt, cached
    for 20 s. System state (agent counts, pending tasks) changes slowly
    relative to chat cadence, so a slightly stale snapshot is acceptable and
    removes a full table scan from every chat message's critical path.
    """
    now = time.monotonic()
    cached = _system_context_cache
    if cached["value"] is not None and (now - cached["ts"]) < _SYSTEM_CONTEXT_TTL:
        return cached["value"]
    value = await ChatService.get_system_context(db)
    cached["ts"] = now
    cached["value"] = value
    return value
```

Then change the call site in `process_message` (currently `context = await ChatService.get_system_context(db)`) to:

```python
context = await ChatService.get_cached_system_context(db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_chat_system_context_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/unit/test_chat_system_context_cache.py
git commit -m "perf(chat): cache system-context for 20s to skip per-message table scan"
```

---

### Task 2: Single-pass classification (remove the 2nd LLM call)

**Files:**
- Modify: `backend/services/chat_service.py` (`analyze_for_task` refactor + new `classify_action_from_result`, `create_task_from_decision`)
- Test: `tests/unit/test_chat_classify.py`

**Interfaces:**
- Consumes: `DecisionEngine._parse` (backend/services/decision_engine.py:100) and `DecisionAction` enum.
- Produces:
  - `ChatService.classify_action_from_result(result: Dict[str, Any]) -> Decision` — parses a `decide` tool call from the generation result; defaults to `REPLY` if absent.
  - `ChatService.create_task_from_decision(head, decision, prompt, db) -> Dict[str, Any]` — the DB task-creation half of the old `analyze_for_task` (no LLM call).
  - `ChatService.analyze_for_task(head, prompt, response, db)` — kept for backward compatibility; now calls `DecisionEngine().decide` then `create_task_from_decision`.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from backend.services import chat_service as cs
from backend.services.decision_engine import DecisionAction


def test_classify_action_from_result_reads_decide_tool():
    result = {
        "tool_calls": [
            {
                "function": {
                    "name": "decide",
                    "arguments": '{"action": "create_task", "rationale": "build", '
                                 '"task_brief": "Build a scraper", "confidence": 0.9}',
                }
            }
        ]
    }
    decision = cs.ChatService.classify_action_from_result(result)
    assert decision.action is DecisionAction.CREATE_TASK
    assert decision.task_brief == "Build a scraper"


def test_classify_action_from_result_defaults_to_reply():
    decision = cs.ChatService.classify_action_from_result({"tool_calls": []})
    assert decision.action is DecisionAction.REPLY
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_chat_classify.py -v`
Expected: FAIL (`classify_action_from_result` not defined).

- [ ] **Step 3: Write minimal implementation**

In `backend/services/chat_service.py`, add a new `@staticmethod` next to `analyze_for_task`:

```python
@staticmethod
def classify_action_from_result(result: Dict[str, Any]):
    """
    Extract the routing decision from the SAME generation call that produced
    the Head's reply (no second LLM round-trip). Looks for a `decide` tool
    call in the result; if the model didn't emit one, default to REPLY so we
    never create a spurious task.
    """
    from backend.services.decision_engine import DecisionEngine, DecisionAction

    calls = result.get("tool_calls") or []
    for call in calls:
        if call.get("function", {}).get("name") == "decide":
            return DecisionEngine._parse({"tool_calls": [call]})
    return Decision(
        action=DecisionAction.REPLY,
        rationale="no_decide_tool_call",
        confidence=0.0,
    )


@staticmethod
async def create_task_from_decision(
    head: HeadOfCouncil,
    decision,
    prompt: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Create + route a Task from an already-computed Decision. No LLM call.
    Extracted from analyze_for_task so the hot path can reuse a decision that
    was obtained for free from the main generation.
    """
    from backend.services.decision_engine import DecisionAction

    if decision.action is not DecisionAction.CREATE_TASK:
        if decision.action not in (
            DecisionAction.DISPATCH_TASK,
            DecisionAction.DELEGATE,
            DecisionAction.SPAWN_AGENT,
        ):
            return {"created": False}

    task = Task(
        title=prompt[:100] + "..." if len(prompt) > 100 else prompt,
        description=decision.task_brief or prompt,
        task_type=TaskType.EXECUTION,
        priority=TaskPriority.NORMAL,
        created_by="sovereign",
        head_of_council_id=head.id,
        requires_deliberation=True,
    )
    db.add(task)
    db.commit()

    task.decision_id = decision.decision_id
    db.commit()

    plan = {
        "objective": (decision.task_brief or prompt)[:200],
        "title": task.title,
        "task_id": task.agentium_id,
        "steps": ["deliberation", "delegation", "execution", "review"],
        "created_at": datetime.utcnow().isoformat(),
    }
    try:
        head.update_ethos_with_plan(plan, db, max_retries=3)
        db.commit()
    except RuntimeError as e:
        logger.warning(
            "Ethos update failed for Head %s during plan write: %s",
            head.agentium_id, e,
        )

    council = db.query(Agent).filter(
        Agent.agent_type == AgentType.COUNCIL_MEMBER,
        Agent.is_active == True,
    ).all()
    if council:
        task.start_deliberation([c.agentium_id for c in council])
        db.commit()

    return {"created": True, "task_id": task.agentium_id}
```

Then refactor the existing `analyze_for_task` (chat_service.py:648) so its body becomes:

```python
@staticmethod
async def analyze_for_task(
    head: HeadOfCouncil,
    prompt: str,
    response: str,
    db: Session,
) -> Dict[str, Any]:
    """
    Standalone path: make a fresh Decision via the DecisionEngine (its own LLM
    call) and create the task. Retained for non-chat callers / tests. The chat
    hot path uses classify_action_from_result + create_task_from_decision
    instead, so it performs zero extra LLM calls.
    """
    from backend.services.decision_engine import DecisionEngine

    decision = await DecisionEngine().decide(head, prompt, db)
    return await ChatService.create_task_from_decision(head, decision, prompt, db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_chat_classify.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/unit/test_chat_classify.py
git commit -m "perf(chat): classify routing decision from main generation result (no 2nd LLM call)"
```

---

### Task 3: Inject the `decide` tool into the Head's generation

**Files:**
- Modify: `backend/services/chat_service.py` (build `tools` + `tool_choice` and pass to `llm_client.generate_with_tools`; append a classify instruction to `full_prompt`)
- Test: `tests/unit/test_chat_decide_tool.py`

**Interfaces:**
- Consumes: `LLMClient.DECISION_TOOL` (backend/core/llm_client.py:465), `ToolRegistry` (backend/core/tool_registry.py), `classify_action_from_result` (Task 2).
- Produces: the Head's `generate_with_tools` call now surfaces a `decide` tool call in `result["tool_calls"]`, enabling Task 2's parser.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services import chat_service as cs


@pytest.mark.asyncio
async def test_head_generation_receives_decide_tool(monkeypatch):
    captured = {}

    async def fake_generate_with_tools(agent, user_message, *, db, **kwargs):
        captured.update(kwargs)
        return {"content": "On it.", "tool_calls": [], "model": "x"}

    fake_llm = MagicMock()
    fake_llm.generate_with_tools = fake_generate_with_tools
    monkeypatch.setattr(cs.LLMClient, "__init__", lambda self, **k: None)
    monkeypatch.setattr(cs.LLMClient, "generate_with_tools", fake_generate_with_tools)

    head = MagicMock()
    head.agentium_id = "00001"
    db = MagicMock()
    await cs.ChatService.process_message(head, "build a scraper", db)

    assert "tools" in captured, "decide tool was not injected"
    names = [t.get("function", {}).get("name") for t in captured["tools"]]
    assert "decide" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_chat_decide_tool.py -v`
Expected: FAIL (`decide` not in tools / assertion error).

- [ ] **Step 3: Write minimal implementation**

In `process_message`, locate the generation block (chat_service.py:362–381). Build the tool list and pass it through:

```python
from backend.core.tool_registry import ToolRegistry

tier = f"{head.agentium_id[0]}xxxx"
try:
    registry_tools = ToolRegistry().to_openai_tools(tier)
except Exception:
    registry_tools = []
gen_tools = list(registry_tools) + [LLMClient.DECISION_TOOL]

# Instruct the model to always emit the routing decision alongside its reply.
full_prompt += (
    "\n\nAlways call the `decide` tool to classify your action "
    "(reply/create_task/delegate/dispatch_task) in the same turn as your reply."
)
```

Change the `await llm_client.generate_with_tools(...)` call to pass the tools and auto tool-choice:

```python
result = await llm_client.generate_with_tools(
    agent=head,
    user_message=message,
    db=db,
    config_id=config_id,
    fallback_configs=fallback_configs,
    system_prompt_override=full_prompt,
    agent_tier=tier,
    history=history,
    on_delta=on_delta,
    cancel_event=cancel_event,
    prompt_cache_key=cache_key,
    tools=gen_tools,
    tool_choice={"type": "auto"},
)
```

Then replace the post-generation classification call:

```python
# OLD: task_info = await ChatService.analyze_for_task(head, message, result["content"], db)
decision = ChatService.classify_action_from_result(result)
task_info = await ChatService.create_task_from_decision(head, decision, message, db)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_chat_decide_tool.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/unit/test_chat_decide_tool.py
git commit -m "perf(chat): inject decide tool so routing is classified in the main LLM call"
```

---

### Task 4: Decouple task creation from `message_end` + follow-up WS event

**Files:**
- Modify: `backend/services/chat_service.py` (`process_message` — background task + broadcast; add `_create_task_background`)
- Modify: `backend/api/routes/websocket.py` (no structural change; relies on existing `manager.broadcast`)
- Test: `tests/integration/test_ws_task_event.py`

**Interfaces:**
- Consumes: `create_task_from_decision` (Task 2), `ConnectionManager.broadcast` (backend/api/routes/websocket.py:226) — accessed via the `ws_manager` global already imported in chat_service.py.
- Produces:
  - `ChatService._create_task_background(head_agentium_id, decision, prompt, user_id)` — opens its own `SessionLocal()`, creates+routes the task, then broadcasts `{"type": "task_created", ...}`.
  - A new WebSocket event type `task_created` the frontend can render.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services import chat_service as cs


@pytest.mark.asyncio
async def test_create_task_background_broadcasts_event():
    from backend.models.database import SessionLocal

    sent = {}

    class FakeManager:
        async def broadcast(self, msg):
            sent.update(msg)

    with patch.object(cs, "ws_manager", FakeManager()), \
         patch("backend.services.chat_service.SessionLocal", SessionLocal):
        # Build a decision-like object
        class D:
            action = "create_task"
            task_brief = "Build a scraper"
            decision_id = "dec-1"

        # Patch create_task_from_decision to avoid real DB writes in unit test
        async def fake_create(head, decision, prompt, db):
            return {"created": True, "task_id": "30001"}

        with patch.object(cs.ChatService, "create_task_from_decision", staticmethod(fake_create)):
            await cs.ChatService._create_task_background("00001", D(), "build a scraper", "u1")
            # allow the broadcast (already sync in FakeManager) to register
            assert sent.get("type") == "task_created"
            assert sent.get("task_id") == "30001"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/integration/test_ws_task_event.py -v`
Expected: FAIL (`_create_task_background` not defined).

- [ ] **Step 3: Write minimal implementation**

Add to `class ChatService`:

```python
@staticmethod
async def _create_task_background(
    head_agentium_id: str,
    decision,
    prompt: str,
    user_id: Optional[str],
) -> None:
    """
    Fire-and-forget: create + route the Task in its own DB session and announce
    it via a follow-up WebSocket event so message_end is not blocked by task
    creation / deliberation startup.
    """
    global ws_manager
    try:
        from backend.models.entities import HeadOfCouncil
        from backend.services.decision_engine import DecisionAction

        db: Session = SessionLocal()
        try:
            head = db.query(HeadOfCouncil).filter_by(agentium_id=head_agentium_id).first()
            if not head:
                return
            task_info = await ChatService.create_task_from_decision(head, decision, prompt, db)
        finally:
            db.close()

        if task_info.get("created"):
            if ws_manager is None:
                from backend.api.routes.websocket import manager as ws_manager
            try:
                await ws_manager.broadcast({
                    "type": "task_created",
                    "task_id": task_info.get("task_id"),
                    "action": getattr(decision.action, "value", str(decision.action)),
                    "content": decision.task_brief or prompt[:100],
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except Exception as exc:
                logger.warning(f"[ChatService] task_created broadcast failed: {exc}")
    except Exception as exc:
        logger.error(f"[ChatService] background task creation failed: {exc}")
```

In `process_message`, replace the synchronous classification+creation block with a background handoff that returns `task_created=False` in the immediate response (the real status arrives via the `task_created` event):

```python
decision = ChatService.classify_action_from_result(result)
from backend.services.decision_engine import DecisionAction

_delegate_actions = (
    DecisionAction.CREATE_TASK,
    DecisionAction.DELEGATE,
    DecisionAction.DISPATCH_TASK,
    DecisionAction.SPAWN_AGENT,
)
if decision.action in _delegate_actions:
    try:
        asyncio.create_task(
            ChatService._create_task_background(
                head.agentium_id,
                decision,
                message,
                str(sovereign_user.id) if sovereign_user else None,
            )
        )
    except Exception as exc:
        logger.warning(f"[ChatService] failed to schedule background task: {exc}")
    task_info = {"created": True, "task_id": None, "pending": True}
else:
    task_info = {"created": False}
```

Keep `task_info` flowing into the return dict as before (the `task_id` may be `None` until the event arrives; the frontend updates on `task_created`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/integration/test_ws_task_event.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/integration/test_ws_task_event.py
git commit -m "perf(chat): create tasks in background; report via task_created WS event"
```

---

### Task 5: Move media interception off the critical path

**Files:**
- Modify: `backend/services/chat_service.py` (`process_message` — wrap MediaInterceptor + Head-turn persist in a background task)
- Test: `tests/unit/test_chat_media_offpath.py`

**Interfaces:**
- Consumes: `MediaInterceptor.intercept_and_store` (existing usage at chat_service.py:465), `SessionLocal`.
- Produces: the streamed reply still reaches the user immediately; media rewriting + DB persistence of the Head turn happen in the background.

- [ ] **Step 1: Write the failing test**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.services import chat_service as cs


@pytest.mark.asyncio
async def test_media_interception_not_awaited_on_critical_path(monkeypatch):
    # Stub the background coroutine so we don't do real network/DB work.
    scheduled = {"ran": False}

    async def fake_media_bg(*a, **k):
        scheduled["ran"] = True

    monkeypatch.setattr(cs.ChatService, "_persist_head_turn_background", staticmethod(fake_media_bg))

    head = MagicMock();
    head.agentium_id = "00001"
    db = MagicMock()
    # Process a message; media handling must be deferred, not awaited inline.
    await cs.ChatService.process_message(head, "show me the sales chart", db)
    # The inline path must NOT have run the heavy work synchronously.
    assert scheduled["ran"] is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_chat_media_offpath.py -v`
Expected: FAIL (`_persist_head_turn_background` not defined).

- [ ] **Step 3: Write minimal implementation**

Add a background helper next to `_create_task_background`:

```python
@staticmethod
async def _persist_head_turn_background(
    user_id: str,
    content: str,
    agent_id: str,
    model: str,
    media_urls: list,
) -> None:
    """Persist the Head-of-Council turn + media rewrite off the critical path."""
    try:
        db: Session = SessionLocal()
        try:
            # Persist original content immediately; rewrite happens async.
            msg_id = str(uuid.uuid4())
            db.add(ChatMsg(
                id=msg_id,
                user_id=user_id,
                role="head_of_council",
                content=content,
                message_metadata={
                    "agent_id": agent_id,
                    "model": model,
                    "media_urls": media_urls or [],
                },
            ))
            db.commit()
        finally:
            db.close()
    except Exception as exc:
        logger.warning(f"[ChatService] Head turn persist (bg) failed: {exc}")
```

In `process_message`, replace the inline media-interception + Head-turn persist block (chat_service.py:461–505) so the critical path only stores the inbound turn and schedules the background work:

```python
# OLD block removed: inline MediaInterceptor.intercept_and_store + db.add(ChatMsg...)
# NEW: schedule media interception + persistence in the background.
if sovereign_user:
    try:
        asyncio.create_task(
            ChatService._media_and_persist_background(
                str(sovereign_user.id),
                result["content"],
                head.agentium_id,
                result.get("model", model_name),
                [],  # media_urls filled after interception inside the bg task
            )
        )
    except Exception as exc:
        logger.warning(f"[ChatService] media bg schedule failed: {exc}")
```

And add the media-aware background helper referenced above:

```python
@staticmethod
async def _media_and_persist_background(
    user_id: str, content: str, agent_id: str, model: str, media_urls: list,
) -> None:
    try:
        import httpx
        from backend.services.media_interceptor import MediaInterceptor

        async with httpx.AsyncClient(timeout=MediaInterceptor.DOWNLOAD_TIMEOUT) as http_client:
            content, media_urls = await MediaInterceptor.intercept_and_store(
                text=content, user_id=user_id, db=SessionLocal(), http_client=http_client
            )
    except Exception as exc:
        logger.warning(f"[ChatService] media interception (bg) failed: {exc}")
    await ChatService._persist_head_turn_background(user_id, content, agent_id, model, media_urls)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_chat_media_offpath.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/chat_service.py tests/unit/test_chat_media_offpath.py
git commit -m "perf(chat): run media interception + Head-turn persist in background"
```

---

### Task 6: Benchmark before vs after

**Files:**
- Reference: `docs/chat-context-benchmark.md` (existing harness)
- Output: `docs/superpowers/plans/2026-07-19-head-of-council-chat-perf-results.md`

**Interfaces:**
- Consumes: a running stack (`make up`) and a way to send a chat message (WebSocket `/ws/chat` or `POST /api/v1/chat/send`).
- Produces: recorded latencies for the two measurements.

- [ ] **Step 1: Capture baseline latency (before this plan)**

With the `main` branch (pre-change) running:

```bash
cd "E:/Ongoing Projects/Agentium"
make up
# Send N representative messages (a chit-chat "hello" and an execution "build a scraper")
# and record: t(first delta) and t(message_end) from the WebSocket frames.
```

Record numbers in `docs/superpowers/plans/2026-07-19-head-of-council-chat-perf-results.md` under `## Baseline`.

- [ ] **Step 2: Capture post-change latency**

On the branch with all Tasks 1–5 merged:

```bash
cd "E:/Ongoing Projects/Agentium"
make restart
# Repeat the same N messages; record the same two timings.
```

Record under `## After`.

- [ ] **Step 3: Assert improvement**

Confirm:
- number of LLM round-trips per message dropped from 2 → 1 (no `DecisionEngine.decide` call on the chat hot path — verify by grep/log),
- `message_end` latency is not regressed and `task_created` still arrives (via the new event),
- execution requests still create + route a Task (check `Task` row + deliberation started).

Write the comparison table into the results doc.

- [ ] **Step 4: Commit results**

```bash
git add docs/superpowers/plans/2026-07-19-head-of-council-chat-perf-results.md
git commit -m "docs: record Head of Council chat perf benchmark before/after"
```

---

## Self-Review Notes

- **Spec coverage:** single-pass classification (Tasks 2–3), decouple task creation (Task 4), system-context cache (Task 1), media off critical path (Task 5), measurement (Task 6), boundaries (documented in spec, enforced by Tasks 2–4). All spec sections mapped.
- **No placeholders:** every code step shows concrete code; tests include assertions and exact run commands.
- **Type consistency:** `classify_action_from_result(result)` returns a `Decision`; `create_task_from_decision(head, decision, prompt, db)` consumes that `Decision`; `_create_task_background` forwards the same `decision`. `task_info` dict shape (`created`, `task_id`, `pending`) is consistent with the return dict at chat_service.py:580.
- **Risk note:** if the model occasionally omits the `decide` tool call, Task 2's default-to-REPLY means no task is created for that message. This is the safe failure mode (no spurious tasks). If real-world eval in Task 6 shows too many missed delegations, tighten the system-prompt instruction added in Task 3.
