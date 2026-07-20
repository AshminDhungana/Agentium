# Design: Vector DB Read/Write Checkpoints During Task Execution (8.4)

- **Date:** 2026-07-20
- **Status:** Approved (design gate passed)
- **Source backlog item:** `docs/documents/todo_verify.md` §8.4
- **Priority:** P2
- **Builds on:** 6.5 / 6.6 / 6.7 search-before-acting (`backend/services/knowledge_assist.py`, `docs/superpowers/specs/2026-07-20-search-before-acting-design.md`)

## Goal

Add three explicit, traced ChromaDB interaction checkpoints to the task-execution
flow. Each checkpoint follows the same shape:

1. **Query** ChromaDB for existing relevant context.
2. **Always web-search** (unconditionally — distinct from 6.5's conditional search).
3. **Fold the web result into the update** and write it back to ChromaDB via the
   shared 6.6 `write_knowledge` schema.
4. **Degrade gracefully** — if web search is unavailable/fails, still record the
   checkpoint (writing whatever ChromaDB context exists) and never block the task.

The three checkpoints:

- **`received`** — fired right after the task is loaded, before execution begins.
- **`completed`** — fired right after `task.complete(...)`, beside the existing
  Phase 13.4 real-time learning write.
- **`mid`** — fired only when the agent self-signals a knowledge gap during
  execution (the hybrid explicit-gate deferred by 6.5, reintroduced here).

## Why this shape (research grounding)

- **Memory engineering** treats *write policy* (what gets stored, how, and what
  happens when memory is missing) as a first-class design concern — not an
  afterthought (MarkTechPost "Comparing Memory Systems for LLM Agents", 2025;
  machinelearningmastery "Context vs. Memory Engineering", 2026-07).
- **Agentic RAG** research (LLM+Vector Data @ ICDE 2026) emphasizes agents that
  *monitor uncertainty* and write enriched context back to the vector store
  mid-workflow — exactly the self-signal + write-back pattern here.
- **Graceful degradation** with checkpoints and tool fallbacks is a recognized
  production pattern (buildmvpfast "Graceful Degradation for AI Agents", 2026) —
  supports "missing web search doesn't block the update".
- ChromaDB is the agreed store; the existing `write_knowledge` 6.6 schema is the
  correct, single funnel to reuse — no new write path is introduced.

## Architecture

### New service function: `knowledge_assist.checkpoint_write`

Owns the per-checkpoint read/write behavior. Lives in
`backend/services/knowledge_assist.py` next to `retrieve_or_search` /
`write_knowledge`.

```python
@dataclass
class CheckpointOutcome:
    stage: str                       # "received" | "completed" | "mid"
    queried_chroma: bool
    searched_web: bool
    wrote_back: bool
    fallback_used: bool
    parent_id: Optional[str]


async def checkpoint_write(
    stage: str,
    task: Any,
    agent: Any,
    db: Any,
    *,
    query: Optional[str] = None,
) -> CheckpointOutcome:
    """One traced ChromaDB checkpoint: read -> always web-search ->
    fold into a write_knowledge upsert; never blocks on search failure."""
```

Behavior:

1. **Read.** `store.query_knowledge(query or task.description,
   collection_keys=DEFAULT_RETRIEVAL_KEYS, n_results=5, db=db)`. Capture
   `queried_chroma=True` even if empty. On query exception, log + continue with
   empty Chroma context.
2. **Search (always).** `await web_search_tool.execute(query=query or
   task.description, provider="auto")`. Unlike 6.5, this is **unconditional** —
   every checkpoint performs the search. On `status == "success"`, synthesize one
   consolidated document (title / URL / snippet per result) and upsert via
   `write_knowledge` with `collection_key="web_knowledge"` and
   `type="agent_learning"`, `source="agent"`.
3. **Fold + write.** The written document combines (a) the synthesized web
   summary and (b) any ChromaDB context already present, so the update is a
   superset. Use a deterministic `parent_id` derived from the stage + normalized
   query so repeats update in place (dedup via the 6.6 schema). Set
   `metadata["stage"] = stage` and `metadata["task_id"] = task.agentium_id` for
   traceability.
4. **Graceful failure.** If web search returns `status == "error"` or raises,
   log a warning, set `fallback_used=True`, and still upsert the Chroma-only
   context if any. **Never raise** — the calling task must not be blocked.

`DEFAULT_RETRIEVAL_KEYS` already exists in `knowledge_assist` (6.5); reuse it.
A new constant `CHECKPOINT_STAGES = ("received", "completed", "mid")` validates
`stage`.

### Wiring the three checkpoints

**`received` and `completed` — `backend/services/tasks/task_executor.py`**
(`execute_task_async`, around lines 132 and 158):

- After `task`/`agent` are loaded (line ~132), wrap a call:
  `await checkpoint_write("received", task, agent, db)` in try/except
  (log + continue). Non-blocking.
- After `task.complete(...)` (line ~158), alongside the existing Phase 13.4
  learning write, wrap: `await checkpoint_write("completed", task, agent, db)`.
- Note: `execute_task_async` is a Celery task (sync function). `checkpoint_write`
  is async, so call it via `asyncio.run(...)` consistent with the existing
  `asyncio.run(manager.broadcast(...))` pattern at line 149 — or, preferably,
  `asyncio.get_event_loop().run_until_complete(...)`. Mirror the existing
  style in the file.

**`mid` — agent self-signal**

- `SkillRAG.execute_with_skills` (`backend/services/skill_rag.py`) gains a
  self-signal contract: when the LLM output contains a `<<NEED_KNOWLEDGE>>`
  marker (or invokes a `knowledge_query` tool), set
  `result["knowledge_needed"] = True` and
  `result["knowledge_query"] = <the agent's stated gap/query>`. The marker is a
  cheap string the LLM can emit; parsing is a single `in` check.
- `Agent.execute_with_skill_rag` (`backend/models/entities/agents.py:297`)
  forwards `knowledge_needed` / `knowledge_query` through its returned dict.
- In `task_executor.execute_task_async`, after `result =
  agent.execute_with_skill_rag(task, db)`: if
  `result.get("knowledge_needed")`, fire
  `await checkpoint_write("mid", task, agent, db, query=result.get("knowledge_query"))`.
  Wrapped in try/except, non-blocking.

The self-signal is opt-in by the model and costs nothing when absent — matching
the deferred 6.5 hybrid-gate decision.

## Data flow (per checkpoint)

```
checkpoint_write(stage, task, agent, db, query=?)
  ├─ chroma = store.query_knowledge(query, DEFAULT_RETRIEVAL_KEYS)   # READ
  ├─ web   = await web_search_tool.execute(query)                    # ALWAYS SEARCH
  ├─ if web.status == "success":
  │     doc = synthesize(chroma_context + web_results)
  │     pid = parent_id(stage, query)
  │     write_knowledge(pid, doc, {type:"agent_learning", source:"agent",
  │                                stage, task_id}, db, "web_knowledge")  # WRITE
  │     wrote_back = True
  └─ else:
        fallback_used = True
        if chroma had hits: write_knowledge(chroma-only context)    # still WRITE
  return CheckpointOutcome(...)
```

## Error handling

- ChromaDB query failure → log, proceed with empty Chroma context (`queried_chroma=True`).
- Web search unavailable (`status == "error"` or any exception) → `fallback_used=True`,
  write Chroma context if present, do **not** raise.
- Write-back (embedding/upsert) failure → log, skip write, continue.
- All three call sites wrap `checkpoint_write` in try/except so a task is never
  blocked by a checkpoint. Matches the existing non-fatal pattern at
  `task_executor.py:172-179` (Phase 13.4 learning write).

## Testing

- **Unit** (`backend/tests/unit/test_knowledge_assist_checkpoint.py`):
  - `test_checkpoint_write_web_success_writes_back`: empty Chroma + mocked web
    `success` → `wrote_back=True`, a `web_knowledge` doc written with
    `metadata["stage"]=="received"` and the 6.6 schema fields present.
  - `test_checkpoint_write_web_failure_falls_back`: web returns `error` →
    `fallback_used=True`, `wrote_back` reflects whether Chroma context existed,
    **no exception raised**.
  - `test_checkpoint_write_mid_uses_provided_query`: `query="..."` passed →
    web_search called with that query, not `task.description`.
  - `test_checkpoint_write_stage_validation`: invalid `stage` raises
    `ValueError` (defensive; call sites always pass valid stages).
- **Integration** (`backend/tests/integration/test_checkpoint_chroma.py`):
  - Run a task whose execution self-signals a gap; assert the trace shows all
    three ChromaDB interactions (received, completed, mid) via `CheckpointOutcome`
    captured on the task or a spy.
  - Separate run with web search forced to `error`: assert all three checkpoints
    still record (`fallback_used=True`) and the task completes.

## Files touched (summary)

- `backend/services/knowledge_assist.py` — **new** `checkpoint_write` +
  `CheckpointOutcome` + `CHECKPOINT_STAGES`
- `backend/services/tasks/task_executor.py` — wire `received` + `completed` +
  `mid` checkpoints (non-blocking)
- `backend/services/skill_rag.py` — parse `<<NEED_KNOWLEDGE>>` self-signal →
  `knowledge_needed` / `knowledge_query` in result
- `backend/models/entities/agents.py` — forward `knowledge_needed` /
  `knowledge_query` from `execute_with_skill_rag`
- tests: `backend/tests/unit/test_knowledge_assist_checkpoint.py`,
  `backend/tests/integration/test_checkpoint_chroma.py`

## Out of scope

- 6.5's pre-task `retrieve_or_search` behavior is unchanged (its search stays
  conditional on ChromaDB sufficiency). 8.4's checkpoints are an *additional*
  unconditional layer.
- No new ChromaDB collection — checkpoints reuse `web_knowledge` (6.5).
- Automatic (non-self-signal) midpoint firing is explicitly NOT done; only the
  agent self-signal triggers the `mid` checkpoint.
