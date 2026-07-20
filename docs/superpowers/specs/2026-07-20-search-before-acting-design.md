# Design: Search-Before-Acting Knowledge Loop (6.5 + 6.6 + 6.7)

- **Date:** 2026-07-20
- **Status:** Approved (design gate passed)
- **Source backlog item:** `docs/documents/todo_verify.md` §6.5, §6.6, §6.7
- **Priority:** P2 (all three)

## Goal

Make every agent, as a structural step in its standard task-execution flow,
query ChromaDB for relevant knowledge before acting; if the knowledge is
missing, perform a web search and write the result back to ChromaDB; and if web
search is unavailable, gracefully fall back to whatever ChromaDB already
returned rather than blocking. This is delivered as three interlocking changes:

- **6.5** — the search-before-acting step in the execution flow (code, not just Ethos text).
- **6.6** — a documented, shared write structure for all agent→ChromaDB writes (fields, dedup key, revision metadata), with all write paths routed through it.
- **6.7** — explicit Knowledge Retrieval and Knowledge Update steps in every agent's Ethos, so the loop is part of the standard procedure, not optional behavior.

## Architecture

### New module: `backend/services/knowledge_assist.py`

Central service that owns the knowledge loop. Public surface:

```python
async def retrieve_or_search(
    query: str,
    agent: Agent,
    db: Session,
    *,
    min_results: int = 3,
    collection_keys: Optional[List[str]] = None,
    sufficiency_distance: float = KNOWLEDGE_SUFFICIENCY_DISTANCE,
) -> RetrievalOutcome:
    """Query ChromaDB; if insufficient, web-search and write back; never block."""

async def write_knowledge(
    parent_id: str,
    text: str,
    metadata: Dict[str, Any],
    db: Session,
    collection_key: str = "web_knowledge",
) -> Dict[str, Any]:
    """Single funnel for all agent knowledge writes (6.6 schema enforcement)."""
```

`RetrievalOutcome` is a small dataclass:
`{ query, chroma_results, web_results, wrote_back: bool, context_text: str, fallback_used: bool }`.

### New ChromaDB collection: `web_knowledge`

- Added to `VectorStore.COLLECTIONS` (`backend/core/vector_store.py:97`) mapping to a
  v2 collection name (e.g. `"web_knowledge_v2"`).
- Added to `VectorDBTool.WRITABLE_COLLECTIONS` (`backend/tools/vector_db_tool.py:31`).
- This is the canonical home for web-search write-backs and also satisfies the
  web-index reference list from 6.4.

### Injection point: `SkillRAG.execute_with_skills`

`backend/services/skill_rag.py:48` is already `async`. At the very start (before
the skill search in step 1), call:

```python
outcome = await retrieve_or_search(task_description, agent, db)
```

then fold `outcome.context_text` into the augmented prompt as a `<<RETRIEVED
KNOWLEDGE>>` block (within the existing `MAX_CONTEXT_CHARS` budget of
`skill_rag`). This binds the structural step to the real flow used by
`Agent.execute_with_skill_rag` → `task_executor.execute_task_async`.

## Data flow (the 6.5 step)

1. **Retrieve.** `vector_store.query_knowledge(task_description,
   collection_keys=DEFAULT_RETRIEVAL_KEYS, n_results=5, db=db)`.
   `DEFAULT_RETRIEVAL_KEYS = ["web_knowledge", "domain_knowledge",
   "best_practices", "task_patterns"]`.
2. **Sufficiency check.** If the top hit's `effective_distance`
   (`vector_store.query_knowledge` already computes this) is `<=
   KNOWLEDGE_SUFFICIENCY_DISTANCE` (default `0.45`, a tuned constant), skip web
   search. Otherwise proceed to search.
3. **Search (if needed).** `await web_search_tool.execute(query=task_description,
   provider="auto")`. On `status == "success"`, synthesize one consolidated
   document from the top K results (title / URL / snippet per result) and write
   it back to `web_knowledge` via `write_knowledge` using a deterministic
   `parent_id` (stable hash of the normalized query) so repeats update in place.
   On **failure / unavailable** (`status == "error"`): log a warning, set
   `fallback_used = True`, return the ChromaDB results already gathered, and
   **do not raise** — the task proceeds.
4. **Fuse.** Return `context_text` (ChromaDB hits + any newly written web
   summary) to be appended to the LLM prompt.

## Standard write structure (6.6)

`write_knowledge` enforces a fixed metadata schema on every write:

| Field             | Type   | Meaning                                                        |
| ----------------- | ------ | ------------------------------------------------------------- |
| `parent_id`       | str    | **Dedup key** — deterministic (e.g. `web:<slug>` or content hash). |
| `type`            | str    | Logical kind: `web_result`, `agent_learning`, `seed`, …       |
| `source`          | str    | `web` \| `agent` \| `seed`                                     |
| `source_url`      | str?   | Origin URL for web results.                                    |
| `title`           | str?   | Human-readable title.                                          |
| `created_at`      | str    | ISO timestamp of first write.                                  |
| `updated_at`      | str    | ISO timestamp of last write.                                   |
| `revision`        | int    | Increment on every upsert (revision-aware).                   |
| `revision_id`     | str    | UUID per write (auditability).                                |
| `agent_id`        | str?   | Agent that authored the write.                                 |
| `document_type`   | str    | Mirrors `type` for collection filtering.                      |
| `decay_score`     | float  | Default `1.0` (consumed by `query_knowledge` decay weighting). |
| `citation_boost`  | float  | Default `1.0`.                                                 |

- **Dedup strategy.** `parent_id` is deterministic, so `upsert_document`
  (`vector_store.py:335`) replaces the parent row + chunk vectors in place. No
  duplicate rows for the same key.
- **Routing.** All agent writes go through `write_knowledge`:
  - the 6.5 web write-back;
  - `VectorDBTool._add` (`vector_db_tool.py:183`) — its body delegates to
    `write_knowledge` instead of calling `upsert_document` directly.
- **Documentation.** Schema lives in `docs/.../knowledge_write_schema.md` and is
  summarized in `backend/.agentium/skills/vector_db/SKILL.md`.

## Ethos steps (6.7)

In `Agent._create_default_ethos` (`backend/models/entities/agents.py:1150`), refine
each agent type's `working_method` (`agents.py:1346`) so it contains explicit,
numbered **"Knowledge Retrieval"** and **"Knowledge Update"** steps:

- **Knowledge Retrieval:** before acting on anything unfamiliar, query ChromaDB
  (via the `vector_db` tool / knowledge service); if missing, web-search and
  write the result back through the shared schema.
- **Knowledge Update:** after a task, write validated learnings back to ChromaDB
  via the shared `write_knowledge` structure.

The loop is made *real* (not optional) because 6.5's code runs it on every task.
Existing `TASK_AGENT` text already gestures at this; the change makes all agent
types explicit and consistent.

## Error handling

- ChromaDB query failure → log, proceed without knowledge (matches existing
  graceful-degradation pattern in `agents.py:292` `read_and_align_constitution`).
- Web search unavailable → fall back to Chroma results, never block (key 6.5
  requirement).
- Embedding / write-back failure → log, skip the write, continue. All wrapped
  non-fatally so a task is never blocked by the knowledge step.

## Testing

- **6.5 unit:** empty Chroma → `retrieve_or_search` awaits web search (mocked)
  → writes to `web_knowledge`; assert `wrote_back=True` and the standard schema
  was used. Separate test: web search returns `error` → returns Chroma results,
  `wrote_back=False`, no exception raised.
- **6.6 unit:** write same `parent_id` twice → exactly one `KnowledgeDocument`
  row; chunk vectors replaced (dedup confirmed).
- **6.7 unit:** fresh agent `working_method` contains both retrieval + update
  steps (assert substrings).
- **Integration:** run a task whose description is novel to the KB; assert the
  trace shows a ChromaDB retrieval call and (when the query was unknown) a
  write-back call.

## Files touched (summary)

- `backend/services/knowledge_assist.py` — **new**
- `backend/services/skill_rag.py` — inject `retrieve_or_search` at step 1
- `backend/core/vector_store.py` — add `web_knowledge` collection
- `backend/tools/vector_db_tool.py` — add `web_knowledge` to writable; route `_add` through `write_knowledge`
- `backend/models/entities/agents.py` — explicit Ethos retrieval/update steps
- `docs/.../knowledge_write_schema.md` — **new** (schema doc)
- `backend/.agentium/skills/vector_db/SKILL.md` — document schema
- tests: `backend/tests/unit/test_knowledge_assist.py`, `backend/tests/integration/test_search_before_acting.py`

## Out of scope

- 6.4 (web-index seeding) is only *partially* served by `web_knowledge`; its
  full seed list remains a separate task.
- Mid-task "I lack knowledge" agent signals (the hybrid explicit-gate option) are
  explicitly deferred — the chosen approach is auto pre-task retrieval only.
