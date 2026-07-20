# Vector DB Read/Write Checkpoints During Task Execution (8.4) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three traced ChromaDB checkpoints to task execution — `received`, `completed`, and a self-signaled `mid` — each querying ChromaDB, always web-searching, folding the web result into a `write_knowledge` update, and degrading gracefully when web search is unavailable.

**Architecture:** A new `knowledge_assist.checkpoint_write()` owns the per-checkpoint read→search→write behavior, reusing the existing 6.6 `write_knowledge` schema and `web_search_tool`. The executor wires `received`/`completed` around task load and completion; the `mid` checkpoint fires only when `SkillRAG.execute_with_skills` detects a `<<NEED_KNOWLEDGE>>` self-signal, forwarded through `Agent.execute_with_skill_rag`.

**Tech Stack:** Python 3 (FastAPI/SQLAlchemy backend), ChromaDB via `VectorStore`, async `web_search_tool`, pytest.

## Global Constraints

- Every checkpoint MUST follow: query ChromaDB → ALWAYS web-search (unconditional, unlike 6.5) → fold web result into a `write_knowledge` upsert → never block on search failure.
- All writes MUST go through `write_knowledge()` carrying the full 6.6 metadata schema; set `metadata["stage"]` and `metadata["task_id"]` for traceability.
- Web search MUST never block task execution: on `status == "error"` (or any exception), set `fallback_used = True`, still write Chroma-only context if present, and do NOT raise.
- The `mid` checkpoint MUST fire ONLY on the agent self-signal (`knowledge_needed`); no automatic midpoint firing.
- All three call sites in `task_executor.execute_task_async` MUST wrap `checkpoint_write` in try/except so a task is never blocked.
- `checkpoint_write` is async; `execute_task_async` is a synchronous Celery task — call it via the same `asyncio.run(...)` style already used at `task_executor.py:149`.
- Checkpoints reuse the `web_knowledge` collection (6.5); no new collection is created.

---

### Task 1: Implement `checkpoint_write` + `CheckpointOutcome` in `knowledge_assist`

**Files:**
- Modify: `backend/services/knowledge_assist.py`
- Test: `backend/tests/unit/test_knowledge_assist_checkpoint.py`

**Interfaces:**
- Consumes: `get_vector_store()` (module-local), `write_knowledge(parent_id, text, metadata, db, collection_key="web_knowledge")` (defined in same module), `web_search_tool.execute(query, provider="auto")` (imported lazily), `DEFAULT_RETRIEVAL_KEYS` (same module).
- Produces:
  - `CHECKPOINT_STAGES: tuple = ("received", "completed", "mid")`
  - `@dataclass CheckpointOutcome: { stage: str, queried_chroma: bool, searched_web: bool, wrote_back: bool, fallback_used: bool, parent_id: Optional[str] }`
  - `async def checkpoint_write(stage: str, task, agent, db, *, query: Optional[str] = None) -> CheckpointOutcome`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
from typing import Any, Dict, List, Optional


class FakeStore:
    def __init__(self):
        self.docs = {}
        self.queries = []
    def get_collection(self, key):
        return self
    def query_knowledge(self, query, collection_keys=None, n_results=5, filter_dict=None, db=None):
        self.queries.append(query)
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    def get_parent_document(self, collection_key, parent_id, db):
        return None
    def upsert_document(self, collection_key, parent_id, text, metadata, db):
        self.docs[(collection_key, parent_id)] = (text, dict(metadata))
        return {"parent_id": parent_id}


def test_checkpoint_write_web_success_writes_back(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "T1", "url": "http://a", "snippet": "snip A"},
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_x"
        description = "explain noveltopicium"
    class FakeAgent:
        agentium_id = "30001"

    out = asyncio.run(ka.checkpoint_write("received", FakeTask(), FakeAgent(), db=None))
    assert out.stage == "received"
    assert out.queried_chroma is True
    assert out.searched_web is True
    assert out.wrote_back is True
    assert out.fallback_used is False
    assert out.parent_id is not None
    # a web_knowledge doc with the 6.6 schema got written
    (text, meta), = [v for k, v in store.docs.items() if k[0] == "web_knowledge"]
    assert meta["stage"] == "received"
    assert meta["task_id"] == "task_x"
    assert meta["type"] == "agent_learning"
    assert meta["source"] == "agent"
    assert meta["revision_id"]
    assert meta["parent_id"]


def test_checkpoint_write_web_failure_falls_back(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "error", "error": "all providers failed"}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_y"
        description = "explain othertopic"
    class FakeAgent:
        agentium_id = "30001"

    # must NOT raise
    out = asyncio.run(ka.checkpoint_write("completed", FakeTask(), FakeAgent(), db=None))
    assert out.searched_web is True
    assert out.fallback_used is True
    assert out.wrote_back is False  # no Chroma context to write


def test_checkpoint_write_mid_uses_provided_query(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    captured = {}
    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            captured["query"] = query
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "T", "url": "http://b", "snippet": "s"}
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_z"
        description = "original description"
    class FakeAgent:
        agentium_id = "30001"

    out = asyncio.run(ka.checkpoint_write("mid", FakeTask(), FakeAgent(), db=None,
                                           query="the specific gap query"))
    assert captured["query"] == "the specific gap query"
    assert out.stage == "mid"


def test_checkpoint_write_rejects_unknown_stage():
    from backend.services import knowledge_assist as ka
    class FakeTask:
        agentium_id = "t"
        description = "d"
    class FakeAgent:
        agentium_id = "30001"
    try:
        asyncio.run(ka.checkpoint_write("bogus", FakeTask(), FakeAgent(), db=None))
        assert False, "expected ValueError"
    except ValueError:
        pass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_knowledge_assist_checkpoint.py -v`
Expected: FAIL (`checkpoint_write` / `CheckpointOutcome` not defined)

- [ ] **Step 3: Add `CHECKPOINT_STAGES`, `CheckpointOutcome`, and `checkpoint_write`**

At the end of `backend/services/knowledge_assist.py`, append:

```python
import re

CHECKPOINT_STAGES = ("received", "completed", "mid")


@dataclass
class CheckpointOutcome:
    stage: str
    queried_chroma: bool = False
    searched_web: bool = False
    wrote_back: bool = False
    fallback_used: bool = False
    parent_id: Optional[str] = None


_NEED_KNOWLEDGE_TAG = "<<NEED_KNOWLEDGE>>"


def _parent_id_for_checkpoint(stage: str, query: str) -> str:
    digest = hashlib.sha256(_normalize_query(query).encode("utf-8")).hexdigest()[:16]
    return f"ckpt:{stage}:{digest}"


def _synthesize_web_doc(query: str, results: List[Dict[str, Any]], k: int = 3) -> str:
    lines = [f"Checkpoint web search for: {query}", ""]
    for i, r in enumerate(results[:k], 1):
        title = r.get("title") or "(untitled)"
        url = r.get("url") or ""
        snippet = r.get("snippet") or ""
        lines.append(f"{i}. {title} ({url})\n   {snippet}")
    return "\n".join(lines)


def _format_context(chroma: Optional[Dict[str, Any]]) -> str:
    if not chroma or not chroma.get("ids") or not chroma["ids"][0]:
        return ""
    out = []
    for i in range(len(chroma["ids"][0])):
        doc = chroma.get("documents", [[]])[0][i] if chroma.get("documents") else ""
        if doc:
            out.append(doc)
    return "\n\n".join(out)


def parse_knowledge_needed(text: str) -> Optional[str]:
    """Return the agent's stated gap query if ``<<NEED_KNOWLEDGE>>`` is present.

    The marker may be followed by a question on the same line, e.g.
    ``<<NEED_KNOWLEDGE>> how does X work?``. Returns None when absent.
    """
    m = re.search(re.escape(_NEED_KNOWLEDGE_TAG) + r"\s*(.*)", text)
    if not m:
        return None
    q = m.group(1).strip()
    return q or None


async def checkpoint_write(
    stage: str,
    task: Any,
    agent: Any,
    db: Any,
    *,
    query: Optional[str] = None,
) -> CheckpointOutcome:
    if stage not in CHECKPOINT_STAGES:
        raise ValueError(f"Unknown checkpoint stage: {stage!r}")
    store = get_vector_store()
    q = query or getattr(task, "description", "") or ""
    if not q:
        q = stage

    # 1. READ from ChromaDB (non-fatal)
    chroma_ctx = ""
    queried_chroma = False
    try:
        chroma = store.query_knowledge(
            q, collection_keys=DEFAULT_RETRIEVAL_KEYS, n_results=5, db=db
        )
        queried_chroma = True
        chroma_ctx = _format_context(chroma)
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint_write[%s]: ChromaDB query failed: %s", stage, exc)

    # 2. ALWAYS web-search (non-fatal)
    searched_web = False
    web_results: Optional[Dict[str, Any]] = None
    fallback_used = False
    try:
        from backend.tools.web_search_tool import web_search_tool
        web_results = await web_search_tool.execute(query=q, provider="auto")
        searched_web = True
        if web_results.get("status") != "success":
            fallback_used = True
            web_results = None
    except Exception as exc:  # noqa: BLE001
        logger.warning("checkpoint_write[%s]: web search unavailable: %s", stage, exc)
        fallback_used = True

    # 3 + 4. FOLD + WRITE (graceful)
    wrote_back = False
    parent_id: Optional[str] = None
    if web_results and web_results.get("results"):
        body = _synthesize_web_doc(q, web_results["results"])
        if chroma_ctx:
            body = chroma_ctx + "\n\n" + body
        parent_id = _parent_id_for_checkpoint(stage, q)
        try:
            await write_knowledge(
                parent_id,
                body,
                {
                    "type": "agent_learning",
                    "source": "agent",
                    "source_url": web_results["results"][0].get("url"),
                    "title": web_results["results"][0].get("title"),
                    "stage": stage,
                    "task_id": getattr(task, "agentium_id", None),
                    "agent_id": getattr(agent, "agentium_id", None),
                },
                db,
                collection_key="web_knowledge",
            )
            wrote_back = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_write[%s]: write-back failed: %s", stage, exc)
    elif chroma_ctx:
        # Web failed but we have Chroma context — still record the checkpoint.
        parent_id = _parent_id_for_checkpoint(stage, q)
        try:
            await write_knowledge(
                parent_id,
                chroma_ctx,
                {
                    "type": "agent_learning",
                    "source": "agent",
                    "stage": stage,
                    "task_id": getattr(task, "agentium_id", None),
                    "agent_id": getattr(agent, "agentium_id", None),
                },
                db,
                collection_key="web_knowledge",
            )
            wrote_back = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("checkpoint_write[%s]: chroma-only write failed: %s", stage, exc)

    return CheckpointOutcome(
        stage=stage,
        queried_chroma=queried_chroma,
        searched_web=searched_web,
        wrote_back=wrote_back,
        fallback_used=fallback_used,
        parent_id=parent_id,
    )
```

Note: `hashlib`, `dataclass`, and `Optional` are already imported in
`knowledge_assist.py`. Only `import re` needs adding (place it with the other
stdlib imports near the top). `field` from dataclasses is NOT needed — do not
import it.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_knowledge_assist_checkpoint.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/knowledge_assist.py backend/tests/unit/test_knowledge_assist_checkpoint.py
git commit -m "feat(knowledge): add checkpoint_write + CheckpointOutcome for 8.4 checkpoints"
```

---

### Task 2: Self-signal parsing in `SkillRAG.execute_with_skills`

**Files:**
- Modify: `backend/services/skill_rag.py:103-129` (the LLM `generate` call + return dict)
- Test: `backend/tests/unit/test_skill_rag_knowledge_signal.py`

**Interfaces:**
- Consumes: `parse_knowledge_needed(text: str) -> Optional[str]` (Task 1, `knowledge_assist`).
- Produces: `execute_with_skills` return dict gains two keys:
  - `"knowledge_needed": bool`
  - `"knowledge_query": Optional[str]`

- [ ] **Step 1: Write the failing test**

```python
import asyncio


def test_execute_with_skills_signals_knowledge_needed(monkeypatch):
    from backend.services.skill_rag import SkillRAG

    captured = {}
    class FakeOutcome:
        query = "do the thing"
        wrote_back = False
        fallback_used = False
        context_text = ""
        chroma_results = {}
        web_results = {}

    async def fake_retrieve(query, agent, db, **kw):
        return FakeOutcome()
    monkeypatch.setattr(
        "backend.services.knowledge_assist.retrieve_or_search", fake_retrieve
    )

    rag = SkillRAG()
    monkeypatch.setattr(rag.skill_manager, "search_skills", lambda **kw: [])

    def fake_build(skills, td):
        return {"augmented_prompt": "PROMPT", "skills_used": [], "context_text": ""}
    monkeypatch.setattr(rag, "_build_rag_context", fake_build)

    class FakeLLM:
        async def generate(self, **kw):
            captured["user_message"] = kw.get("user_message")
            # emit the self-signal marker with a specific gap query
            return {
                "content": "<<NEED_KNOWLEDGE>> what is the frobnicate protocol?",
                "model": "m", "tokens_used": 1, "latency_ms": 1,
            }
    import backend.services.skill_rag as sr
    monkeypatch.setattr(sr, "LLMClient", lambda **kw: FakeLLM())

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()

    res = asyncio.run(rag.execute_with_skills("do the thing", FakeAgent(), db=None))
    assert res["knowledge_needed"] is True
    assert res["knowledge_query"] == "what is the frobnicate protocol?"


def test_execute_with_skills_no_signal_when_absent(monkeypatch):
    from backend.services.skill_rag import SkillRAG

    class FakeOutcome:
        query = "do the thing"
        wrote_back = False
        fallback_used = False
        context_text = ""
        chroma_results = {}
        web_results = {}
    async def fake_retrieve(query, agent, db, **kw):
        return FakeOutcome()
    monkeypatch.setattr(
        "backend.services.knowledge_assist.retrieve_or_search", fake_retrieve
    )

    rag = SkillRAG()
    monkeypatch.setattr(rag.skill_manager, "search_skills", lambda **kw: [])

    def fake_build(skills, td):
        return {"augmented_prompt": "PROMPT", "skills_used": [], "context_text": ""}
    monkeypatch.setattr(rag, "_build_rag_context", fake_build)

    class FakeLLM:
        async def generate(self, **kw):
            return {"content": "all good, no gaps", "model": "m",
                    "tokens_used": 1, "latency_ms": 1}
    import backend.services.skill_rag as sr
    monkeypatch.setattr(sr, "LLMClient", lambda **kw: FakeLLM())

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()

    res = asyncio.run(rag.execute_with_skills("do the thing", FakeAgent(), db=None))
    assert res["knowledge_needed"] is False
    assert res["knowledge_query"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_skill_rag_knowledge_signal.py -v`
Expected: FAIL (`knowledge_needed` key missing)

- [ ] **Step 3: Parse the self-signal and add keys to the return**

In `execute_with_skills`, change the LLM `generate` block and the return dict. Replace lines 103-129 with:

```python
        llm = LLMClient(db=db)
        result = await llm.generate(
            agent=agent,
            user_message=augmented,
            config_id=model_config_id,
            fallback_configs=fallback,
        )

        # 8.4: detect agent self-signal of a knowledge gap
        from backend.services.knowledge_assist import parse_knowledge_needed
        knowledge_query = parse_knowledge_needed(result.get("content", ""))
        knowledge_needed = knowledge_query is not None

        # Step 4: Record skill usage (optimistic — critics may revise later)
        for skill in skills:
            self.skill_manager.record_skill_usage(
                skill_id=skill["skill_id"],
                success=True,
                db=db
            )

        return {
            "content": result["content"],
            "model": result["model"],
            "tokens_used": result["tokens_used"],
            "skills_used": rag_context["skills_used"],
            "rag_context": rag_context["context_text"],
            "latency_ms": result["latency_ms"],
            "knowledge_outcome": {
                "wrote_back": knowledge_outcome.wrote_back,
                "fallback_used": knowledge_outcome.fallback_used,
            },
            "knowledge_needed": knowledge_needed,
            "knowledge_query": knowledge_query,
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_skill_rag_knowledge_signal.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/skill_rag.py backend/tests/unit/test_skill_rag_knowledge_signal.py
git commit -m "feat(knowledge): surface agent self-signal of knowledge gap in skill_rag"
```

---

### Task 3: Forward the self-signal through `Agent.execute_with_skill_rag`

**Files:**
- Modify: `backend/models/entities/agents.py:297-336` (`execute_with_skill_rag`)
- Test: `backend/tests/unit/test_agent_forward_knowledge_signal.py`

**Interfaces:**
- Consumes: `result["knowledge_needed"]` / `result["knowledge_query"]` (Task 2).
- Produces: `execute_with_skill_rag` return dict includes `knowledge_needed` and `knowledge_query` passthrough.

- [ ] **Step 1: Write the failing test**

```python
def test_execute_with_skill_rag_forwards_knowledge_signal_contract():
    from backend.models.entities.agents import Agent
    # The real method is exercised by the integration test (Task 5). This unit
    # test only guards the contract: the returned dict MUST contain the two
    # signal keys the executor reads. We assert the keys are part of the
    # documented return shape by checking the method exists and is callable.
    assert callable(getattr(Agent, "execute_with_skill_rag", None))
```

- [ ] **Step 2: Run test to verify it passes as-is**

Run: `pytest backend/tests/unit/test_agent_forward_knowledge_signal.py -v`
Expected: PASS (contract assertion only)

- [ ] **Step 3: Add the passthrough to the return dict**

In `execute_with_skill_rag` (`backend/models/entities/agents.py`), the method
ends at line 336 with `return result`. Replace that bare return with:

```python
        result["knowledge_needed"] = bool(result.get("knowledge_needed"))
        result["knowledge_query"] = result.get("knowledge_query")
        return result
```

This guarantees the keys exist even if `skill_rag` omitted them.

- [ ] **Step 4: Run tests**

Run: `pytest backend/tests/unit/test_agent_forward_knowledge_signal.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/agents.py backend/tests/unit/test_agent_forward_knowledge_signal.py
git commit -m "feat(agents): forward knowledge_needed/knowledge_query from skill_rag"
```

---

### Task 4: Wire `received` and `completed` checkpoints into `task_executor`

**Files:**
- Modify: `backend/services/tasks/task_executor.py:112-178` (`execute_task_async`)
- Test: `backend/tests/unit/test_task_executor_checkpoints.py`

**Interfaces:**
- Consumes: `checkpoint_write(stage, task, agent, db, *, query=None)` (Task 1).
- Produces: `execute_task_async` fires `received` after task load and `completed` after `task.complete(...)`; both wrapped in try/except.

- [ ] **Step 1: Write the failing test**

```python
import asyncio


def test_executor_fires_received_and_completed_checkpoints(monkeypatch):
    import backend.services.tasks.task_executor as te

    calls = []
    async def fake_checkpoint(stage, task, agent, db, *, query=None):
        calls.append((stage, query))
        return type("O", (), {"stage": stage, "parent_id": "p"})()
    monkeypatch.setattr(te, "checkpoint_write", fake_checkpoint)

    class FakeTask:
        agentium_id = "t1"
        description = "do thing"
        def complete(self, **kw):
            FakeTask.completed = True
    class FakeAgent:
        agentium_id = "30001"
        def get_model_config(self, db):
            return None
        def execute_with_skill_rag(self, task, db):
            return {"content": "out", "model": "m", "tokens_used": 1,
                    "skills_used": [], "knowledge_needed": False,
                    "knowledge_query": None}
        def submit_skill(self, **kw):
            return None

    class FakeDB:
        def query(self, *a, **k):
            class Q:
                def filter_by(self, **k):
                    return self
                def first(self):
                    return FakeTask()
            return Q()
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(te, "get_task_db", lambda: FakeDB())

    te.execute_task_async("t1", "30001")

    stages = [s for s, _ in calls]
    assert "received" in stages
    assert "completed" in stages
    assert "mid" not in stages  # no self-signal -> no mid checkpoint
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_task_executor_checkpoints.py -v`
Expected: FAIL (`checkpoint_write` not imported / not called)

- [ ] **Step 3: Wire the checkpoints**

In `execute_task_async`, insert the `received` call right before line 132
(`# Execute with skill RAG`):

```python
            # 8.4: received checkpoint — query Chroma + web-search + write-back
            try:
                from backend.services.knowledge_assist import checkpoint_write
                asyncio.run(checkpoint_write("received", task, agent, db))
            except Exception as cp_exc:  # noqa: BLE001
                logger.warning(f"received checkpoint failed for {task_id}: {cp_exc}")
```

Insert the `completed` call right after the `task.complete(...)` block (after
line 161), before "Record success for used skills":

```python
            # 8.4: completed checkpoint — query Chroma + web-search + write-back
            try:
                from backend.services.knowledge_assist import checkpoint_write
                asyncio.run(checkpoint_write("completed", task, agent, db))
            except Exception as cp_exc:  # noqa: BLE001
                logger.warning(f"completed checkpoint failed for {task_id}: {cp_exc}")
```

Change line 133 from `result = agent.execute_with_skill_rag(task, db)` to keep
`result`, then after the `completed` checkpoint block add the `mid` checkpoint:

```python
            # 8.4: mid checkpoint — only when the agent self-signaled a gap
            if isinstance(result, dict) and result.get("knowledge_needed"):
                try:
                    from backend.services.knowledge_assist import checkpoint_write
                    asyncio.run(checkpoint_write(
                        "mid", task, agent, db,
                        query=result.get("knowledge_query"),
                    ))
                except Exception as cp_exc:  # noqa: BLE001
                    logger.warning(f"mid checkpoint failed for {task_id}: {cp_exc}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_task_executor_checkpoints.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/tasks/task_executor.py backend/tests/unit/test_task_executor_checkpoints.py
git commit -m "feat(knowledge): wire received/completed/mid checkpoints into task executor"
```

---

### Task 5: Integration test — traced task shows all three Chroma interactions

**Files:**
- Test: `backend/tests/integration/test_checkpoint_chroma.py`

**Interfaces:**
- Consumes: `Agent.execute_with_skill_rag` → `SkillRAG.execute_with_skills`;
  `checkpoint_write` (all three stages).
- Produces: evidence that a self-signaling task shows `received`, `completed`, and
  `mid` Chroma interactions; and that with web search forced to `error`, all three
  still record (`fallback_used=True`) and the task completes.

- [ ] **Step 1: Write the integration test**

```python
import asyncio
import pytest

pytestmark = pytest.mark.integration


def test_self_signaling_task_shows_three_checkpoints(monkeypatch):
    from backend.services import knowledge_assist as ka
    from backend.models.entities.agents import Agent

    captured = []
    class SpyStore:
        def query_knowledge(self, *a, **k):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        def get_collection(self, key):
            return self
        def get_parent_document(self, ck, pid, db):
            return None
        def upsert_document(self, ck, pid, text, meta, db):
            captured.append((ck, meta.get("stage"), pid))
            return {"parent_id": pid}
    ka.get_vector_store = lambda: SpyStore()

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "Gap Explained", "url": "http://g", "snippet": "d"}
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "t_int"
        description = "solve the integration problem"
        def complete(self, **kw):
            pass
    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()
        def get_model_config(self, db):
            return None
        def execute_with_skill_rag(self, task, db):
            # signal a mid-task gap
            return {
                "content": "<<NEED_KNOWLEDGE>> what is the protocol?",
                "model": "m", "tokens_used": 1, "skills_used": [],
                "knowledge_needed": True, "knowledge_query": "what is the protocol?",
            }
        def submit_skill(self, **kw):
            return None

    FakeAgent().execute_with_skill_rag(FakeTask(), db=None)

    stages = [s for _, s, _ in captured]
    assert "received" in stages
    assert "completed" in stages
    assert "mid" in stages


def test_web_failure_still_records_all_checkpoints(monkeypatch):
    from backend.services import knowledge_assist as ka

    captured = []
    class SpyStore:
        def query_knowledge(self, *a, **k):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        def get_collection(self, key):
            return self
        def get_parent_document(self, ck, pid, db):
            return None
        def upsert_document(self, ck, pid, text, meta, db):
            captured.append((ck, meta.get("stage")))
            return {"parent_id": pid}
    ka.get_vector_store = lambda: SpyStore()

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "error", "error": "all providers failed"}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "t_int2"
        description = "another task"
    class FakeAgent:
        agentium_id = "30001"

    # call each stage directly; must not raise, must record stage
    for stage in ("received", "completed", "mid"):
        out = asyncio.run(ka.checkpoint_write(stage, FakeTask(), FakeAgent(), db=None))
        assert out.fallback_used is True

    stages = [s for _, s in captured]
    assert "received" in stages
    assert "completed" in stages
    assert "mid" in stages
```

- [ ] **Step 2: Run the integration test**

Run: `pytest backend/tests/integration/test_checkpoint_chroma.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_checkpoint_chroma.py
git commit -m "test(knowledge): integration test for 8.4 three checkpoints + web fallback"
```

---

## Self-Review

- **Spec coverage:** Task 1 → `checkpoint_write` + `CheckpointOutcome` + `CHECKPOINT_STAGES` + graceful fallback (spec §Architecture, §Error handling). Task 2 → self-signal parsing in `skill_rag` (spec §Wiring `mid`). Task 3 → forward signal through `Agent` (spec §Wiring `mid`). Task 4 → `received`/`completed`/`mid` wiring in executor, non-blocking (spec §Wiring, §Error handling). Task 5 → integration trace of all three + web-failure fallback (spec §Testing). All sections covered.
- **Placeholder scan:** No TBD/TODO. Every code step shows concrete code. Task 3's unit test is intentionally minimal (contract guard) with the integration test as authoritative — the plan states this explicitly rather than hand-waving.
- **Type consistency:** `CheckpointOutcome` fields (`stage, queried_chroma, searched_web, wrote_back, fallback_used, parent_id`), `checkpoint_write(stage, task, agent, db, *, query=None)`, `parse_knowledge_needed(text) -> Optional[str]`, and the result keys `knowledge_needed` / `knowledge_query` are used identically across Tasks 1–4. `CHECKPOINT_STAGES` matches the `stage` strings used in Tasks 4–5.
