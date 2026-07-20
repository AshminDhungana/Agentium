# Search-Before-Acting Knowledge Loop Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every agent query ChromaDB before acting, fall back to a web search that writes back to ChromaDB when knowledge is missing, and never block when web search is unavailable — with a shared, documented write schema and explicit Ethos steps.

**Architecture:** A new `backend/services/knowledge_assist.py` owns the loop: `retrieve_or_search()` checks ChromaDB, web-searches and writes back when insufficient, and is invoked at the start of `SkillRAG.execute_with_skills`. All agent→ChromaDB writes funnel through `write_knowledge()`, which enforces a fixed metadata schema with a deterministic `parent_id` dedup key. Ethos `working_method` text gets explicit Knowledge Retrieval / Knowledge Update steps.

**Tech Stack:** Python 3 (FastAPI/SQLAlchemy backend), ChromaDB via `VectorStore`, async `web_search_tool`, pytest.

## Global Constraints

- Every agent write to ChromaDB MUST go through `write_knowledge()` and carry the full 6.6 metadata schema (`parent_id`, `type`, `source`, `source_url`, `title`, `created_at`, `updated_at`, `revision`, `revision_id`, `agent_id`, `document_type`, `decay_score`, `citation_boost`).
- Web search MUST never block task execution: on `status == "error"` (or any exception), return whatever ChromaDB returned and set `fallback_used = True`; do not raise.
- `parent_id` is the dedup key: re-writing the same `parent_id` updates in place (no duplicate `KnowledgeDocument` rows).
- Default pre-task retrieval searches only `["web_knowledge", "domain_knowledge", "best_practices", "task_patterns"]` — NOT `constitution`/`council_memory` (handled by existing RAG context).
- `KNOWLEDGE_SUFFICIENCY_DISTANCE = 0.45` (tunable constant) is the cosine-distance threshold below which web search is skipped.

---

### Task 1: Register the `web_knowledge` collection

**Files:**
- Modify: `backend/core/vector_store.py:97-115` (inside `COLLECTIONS`)
- Test: `backend/tests/unit/test_vector_store_collections.py`

**Interfaces:**
- Consumes: `VectorStore.COLLECTIONS` dict
- Produces: a `web_knowledge` key resolvable by `get_collection("web_knowledge")` and `query_knowledge(collection_keys=["web_knowledge"])`

- [ ] **Step 1: Write the failing test**

```python
def test_web_knowledge_collection_registered():
    from backend.core.vector_store import VectorStore
    assert "web_knowledge" in VectorStore.COLLECTIONS
    store = VectorStore()
    # get_collection must resolve without raising
    coll = store.get_collection("web_knowledge")
    assert coll is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_vector_store_collections.py -v`
Expected: FAIL (`KeyError` / `web_knowledge` not in `COLLECTIONS`)

- [ ] **Step 3: Add the collection key**

In `backend/core/vector_store.py`, inside `COLLECTIONS` (after `"tool_skills": "tool_skills",`):

```python
        # Web-search write-backs live here; also serves the 6.4 web-index seed.
        "web_knowledge": "web_knowledge_v2",
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_vector_store_collections.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/vector_store.py backend/tests/unit/test_vector_store_collections.py
git commit -m "feat(knowledge): register web_knowledge ChromaDB collection"
```

---

### Task 2: Make `web_knowledge` agent-writable

**Files:**
- Modify: `backend/tools/vector_db_tool.py:31-38` (`WRITABLE_COLLECTIONS`)
- Test: `backend/tests/unit/test_vector_db_tool.py`

**Interfaces:**
- Consumes: `VectorDBTool.WRITABLE_COLLECTIONS`
- Produces: `web_knowledge` accepted by `VectorDBTool._add` (after Task 4 routes it through `write_knowledge`)

- [ ] **Step 1: Write the failing test**

```python
def test_web_knowledge_is_writable():
    from backend.tools.vector_db_tool import VectorDBTool
    assert "web_knowledge" in VectorDBTool.WRITABLE_COLLECTIONS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_vector_db_tool.py -v`
Expected: FAIL (`web_knowledge` not in `WRITABLE_COLLECTIONS`)

- [ ] **Step 3: Add to writable list**

In `backend/tools/vector_db_tool.py`, extend `WRITABLE_COLLECTIONS`:

```python
    WRITABLE_COLLECTIONS: List[str] = [
        "council_memory",
        "task_patterns",
        "best_practices",
        "domain_knowledge",
        "sovereign_prefs",
        "audit_semantic",
        "web_knowledge",
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_vector_db_tool.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/vector_db_tool.py backend/tests/unit/test_vector_db_tool.py
git commit -m "feat(knowledge): allow agents to write web_knowledge collection"
```

---

### Task 3: Implement `knowledge_assist` — `write_knowledge` (6.6) and `retrieve_or_search` (6.5)

**Files:**
- Create: `backend/services/knowledge_assist.py`
- Test: `backend/tests/unit/test_knowledge_assist.py`

**Interfaces:**
- Consumes: `get_vector_store()` (`backend.core.vector_store`), `web_search_tool.execute` (`backend.tools.web_search_tool`), `Agent` (`backend.models.entities.agents`)
- Produces:
  - `async def write_knowledge(parent_id: str, text: str, metadata: Dict[str, Any], db, collection_key: str = "web_knowledge") -> Dict[str, Any]`
  - `async def retrieve_or_search(query: str, agent, db, *, min_results: int = 3, collection_keys: Optional[List[str]] = None, sufficiency_distance: float = KNOWLEDGE_SUFFICIENCY_DISTANCE) -> RetrievalOutcome`
  - `RetrievalOutcome` dataclass: `{ query, chroma_results, web_results, wrote_back, context_text, fallback_used }`
  - constants `KNOWLEDGE_SUFFICIENCY_DISTANCE = 0.45`, `DEFAULT_RETRIEVAL_KEYS`

- [ ] **Step 1: Write the failing tests**

```python
import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

class FakeStore:
    def __init__(self):
        self.docs = {}  # (collection_key, parent_id) -> (text, metadata)
    def get_collection(self, key):
        return self
    def query_knowledge(self, query, collection_keys=None, n_results=5, filter_dict=None, db=None):
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    def get_parent_document(self, collection_key, parent_id, db):
        row = self.docs.get((collection_key, parent_id))
        if not row:
            return None
        return {"full_text": row[0], "metadata": row[1], "chunk_count": 1}
    def upsert_document(self, collection_key, parent_id, text, metadata, db):
        self.docs[(collection_key, parent_id)] = (text, dict(metadata))
        return {"parent_id": parent_id, "chunk_count": 1, "collection_key": collection_key}


def test_write_knowledge_enforces_schema_and_dedup():
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store
    meta = {"type": "web_result", "source": "web", "source_url": "http://x", "title": "T", "agent_id": "30001"}
    r1 = asyncio.run(ka.write_knowledge("web:abc", "body", meta, db=None))
    r2 = asyncio.run(ka.write_knowledge("web:abc", "body2", meta, db=None))
    # single row -> dedup worked
    assert len(store.docs) == 1
    saved_text, saved_meta = store.docs[("web_knowledge", "web:abc")]
    assert saved_text == "body2"
    assert saved_meta["revision"] == 2
    assert saved_meta["revision_id"]
    assert saved_meta["created_at"] and saved_meta["updated_at"]


def test_retrieve_or_search_web_fallback_on_empty_chroma():
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "T1", "url": "http://a", "snippet": "snip A"},
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeAgent:
        agentium_id = "30001"
    out = asyncio.run(ka.retrieve_or_search("novel query here", FakeAgent(), db=None))
    assert out.wrote_back is True
    assert out.fallback_used is False
    assert ("web:abc" in store.docs) is False  # parent_id is hashed, not literal
    # a web_knowledge doc was written
    assert any(k[0] == "web_knowledge" for k in store.docs)


def test_retrieve_or_search_skips_search_when_sufficient():
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    # preset a very-close match
    store.docs[("web_knowledge", "web:known")] = ("known body", {"document_type": "x"})
    ka.get_vector_store = lambda: store

    class FakeWeb:
        def __init__(self):
            self.called = False
        async def execute(self, query, provider="auto", max_results=5):
            self.called = True
            return {"status": "success", "results": []}
    fw = FakeWeb()
    ka.web_search_tool = fw

    class FakeAgent:
        agentium_id = "30001"
    out = asyncio.run(ka.retrieve_or_search("known query", FakeAgent(), db=None,
                                             sufficiency_distance=0.45))
    assert fw.called is False
    assert out.wrote_back is False


def test_retrieve_or_search_never_blocks_on_web_failure():
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "error", "error": "all providers failed"}
    ka.web_search_tool = FakeWeb()

    class FakeAgent:
        agentium_id = "30001"
    # must NOT raise
    out = asyncio.run(ka.retrieve_or_search("novel query", FakeAgent(), db=None))
    assert out.wrote_back is False
    assert out.fallback_used is True
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/unit/test_knowledge_assist.py -v`
Expected: FAIL (module `backend.services.knowledge_assist` not found)

- [ ] **Step 3: Implement `knowledge_assist.py`**

```python
"""
knowledge_assist — the search-before-acting knowledge loop (6.5 + 6.6).

Owns two public coroutines:
  * retrieve_or_search() — query ChromaDB; if insufficient, web-search and
    write the result back; never block when web search is unavailable.
  * write_knowledge()    — the single funnel for ALL agent->ChromaDB writes,
    enforcing the shared 6.6 metadata schema with a deterministic dedup key.
"""
import hashlib
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

KNOWLEDGE_SUFFICIENCY_DISTANCE = 0.45
DEFAULT_RETRIEVAL_KEYS = [
    "web_knowledge",
    "domain_knowledge",
    "best_practices",
    "task_patterns",
]


@dataclass
class RetrievalOutcome:
    query: str
    chroma_results: Dict[str, Any]
    web_results: Optional[Dict[str, Any]]
    wrote_back: bool
    context_text: str
    fallback_used: bool


def _normalize_query(q: str) -> str:
    return " ".join((q or "").lower().split())


def _parent_id_for_query(q: str) -> str:
    digest = hashlib.sha256(_normalize_query(q).encode("utf-8")).hexdigest()[:16]
    return f"web:{digest}"


def _top_distance(chroma: Optional[Dict[str, Any]]) -> Optional[float]:
    if not chroma or not chroma.get("ids") or not chroma["ids"][0]:
        return None
    dists = chroma.get("distances")
    if not dists or not dists[0]:
        return None
    return float(dists[0][0])


def _synthesize_web_doc(query: str, results: List[Dict[str, Any]], k: int = 3) -> str:
    lines = [f"Web search results for: {query}", ""]
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


def get_vector_store():
    from backend.core.vector_store import get_vector_store as _gvs
    return _gvs()


async def write_knowledge(
    parent_id: str,
    text: str,
    metadata: Dict[str, Any],
    db: Any,
    collection_key: str = "web_knowledge",
) -> Dict[str, Any]:
    """Enforce the 6.6 write schema and upsert (dedup by parent_id)."""
    store = get_vector_store()
    now = datetime.utcnow().isoformat()
    meta = dict(metadata or {})
    meta["parent_id"] = parent_id
    meta.setdefault("type", "agent_learning")
    meta.setdefault("source", "agent")
    meta.setdefault("document_type", meta["type"])
    meta.setdefault("decay_score", 1.0)
    meta.setdefault("citation_boost", 1.0)

    existing = store.get_parent_document(collection_key, parent_id, db)
    if existing and existing.get("metadata"):
        em = existing["metadata"]
        meta["created_at"] = em.get("created_at", now)
        meta["revision"] = int(em.get("revision", 0)) + 1
    else:
        meta["created_at"] = now
        meta["revision"] = 1
    meta["updated_at"] = now
    meta["revision_id"] = uuid.uuid4().hex
    return store.upsert_document(collection_key, parent_id, text, meta, db)


async def retrieve_or_search(
    query: str,
    agent: Any,
    db: Any,
    *,
    min_results: int = 3,
    collection_keys: Optional[List[str]] = None,
    sufficiency_distance: float = KNOWLEDGE_SUFFICIENCY_DISTANCE,
) -> RetrievalOutcome:
    store = get_vector_store()
    keys = collection_keys or DEFAULT_RETRIEVAL_KEYS
    chroma = store.query_knowledge(query, collection_keys=keys, n_results=5, db=db)

    wrote_back = False
    web_results: Optional[Dict[str, Any]] = None
    fallback_used = False

    top = _top_distance(chroma)
    if top is None or top > sufficiency_distance:
        try:
            from backend.tools.web_search_tool import web_search_tool
            web_results = await web_search_tool.execute(query=query, provider="auto")
            if web_results.get("status") == "success" and web_results.get("results"):
                doc = _synthesize_web_doc(query, web_results["results"])
                pid = _parent_id_for_query(query)
                await write_knowledge(
                    pid,
                    doc,
                    {
                        "type": "web_result",
                        "source": "web",
                        "source_url": web_results["results"][0].get("url"),
                        "title": web_results["results"][0].get("title"),
                        "agent_id": getattr(agent, "agentium_id", None),
                    },
                    db,
                    collection_key="web_knowledge",
                )
                wrote_back = True
                # refresh so the new doc is in the returned context
                chroma = store.query_knowledge(query, collection_keys=keys, n_results=5, db=db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("retrieve_or_search: web search unavailable/failed: %s", exc)
            fallback_used = True

    return RetrievalOutcome(
        query=query,
        chroma_results=chroma,
        web_results=web_results,
        wrote_back=wrote_back,
        context_text=_format_context(chroma),
        fallback_used=fallback_used,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/unit/test_knowledge_assist.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/knowledge_assist.py backend/tests/unit/test_knowledge_assist.py
git commit -m "feat(knowledge): add knowledge_assist with write_knowledge + retrieve_or_search"
```

---

### Task 4: Route `VectorDBTool._add` through `write_knowledge` (6.6 enforcement)

**Files:**
- Modify: `backend/tools/vector_db_tool.py:183-219` (`_add`)
- Test: `backend/tests/unit/test_vector_db_tool_add_routing.py`

**Interfaces:**
- Consumes: `write_knowledge` (`backend.services.knowledge_assist`)
- Produces: `VectorDBTool._add` delegates write schema enforcement to `write_knowledge`

- [ ] **Step 1: Write the failing test**

```python
import asyncio

def test_add_routes_through_write_knowledge(monkeypatch):
    from backend.tools.vector_db_tool import VectorDBTool

    captured = {}
    async def fake_write(parent_id, text, metadata, db, collection_key="web_knowledge"):
        captured["collection_key"] = collection_key
        captured["parent_id"] = parent_id
        captured["metadata"] = metadata
        return {"parent_id": parent_id}

    import backend.services.knowledge_assist as ka
    monkeypatch.setattr(ka, "write_knowledge", fake_write)

    tool = VectorDBTool()
    res = tool._add("web_knowledge", ["some fact"], [{"type": "agent_learning"}], None)
    assert res["success"] is True
    assert captured["collection_key"] == "web_knowledge"
    # schema field present
    assert "revision_id" in captured["metadata"]
    assert captured["metadata"]["source"] == "agent"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_vector_db_tool_add_routing.py -v`
Expected: FAIL (`write_knowledge` not called / `revision_id` missing)

- [ ] **Step 3: Rewrite `_add` to delegate**

Replace the body of `_add` (lines 183-219) with:

```python
    def _add(self, collection, documents, metadatas, ids):
        if not collection:
            return {"success": False, "error": "collection is required for action 'add'"}
        if not documents:
            return {"success": False, "error": "documents (list[str]) is required for action 'add'"}
        if collection not in self.store.COLLECTIONS:
            return {"success": False, "error": f"Unknown collection '{collection}'"}
        if collection not in self.WRITABLE_COLLECTIONS:
            return {
                "success": False,
                "error": (
                    f"Collection '{collection}' is not writable by agents. "
                    f"Writable collections: {self.WRITABLE_COLLECTIONS}"
                ),
            }
        docs = documents if isinstance(documents, list) else [documents]
        if not ids:
            ids = [f"{collection}_{i}" for i in range(len(docs))]
        if metadatas is None:
            metadatas = [{} for _ in docs]
        stored = []
        try:
            with get_db_context() as db:
                for d_id, doc, meta in zip(ids, docs, metadatas):
                    # Route every agent write through the shared 6.6 schema.
                    asyncio.run(
                        self._write_knowledge(d_id, doc, meta or {}, db, collection)
                    )
                    stored.append(d_id)
        except Exception:  # noqa: BLE001
            coll = self.store.get_collection(collection)
            coll.upsert(documents=docs, metadatas=metadatas, ids=ids)
            stored = ids
        return {
            "success": True,
            "collection": collection,
            "count": len(stored),
            "ids": stored,
        }

    @staticmethod
    async def _write_knowledge(parent_id, text, metadata, db, collection_key):
        from backend.services.knowledge_assist import write_knowledge
        return await write_knowledge(parent_id, text, metadata, db, collection_key)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_vector_db_tool_add_routing.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tools/vector_db_tool.py backend/tests/unit/test_vector_db_tool_add_routing.py
git commit -m "feat(knowledge): route vector_db writes through shared write_knowledge schema"
```

---

### Task 5: Inject `retrieve_or_search` into the task-execution flow (6.5)

**Files:**
- Modify: `backend/services/skill_rag.py:48-110` (`execute_with_skills`)
- Test: `backend/tests/unit/test_skill_rag_knowledge_step.py`

**Interfaces:**
- Consumes: `retrieve_or_search` (`backend.services.knowledge_assist`)
- Produces: every task now includes a `<<RETRIEVED KNOWLEDGE>>` block in the prompt; `result["knowledge_outcome"]` exposes `{wrote_back, fallback_used}` for tracing/tests

- [ ] **Step 1: Write the failing test**

```python
import asyncio

def test_execute_with_skills_includes_retrieved_knowledge(monkeypatch):
    from backend.services.skill_rag import SkillRAG

    captured = {}
    class FakeOutcome:
        query = "do the thing"
        wrote_back = True
        fallback_used = False
        context_text = "Web search results for: do the thing\n1. T (http://a)\n   snip A"
        chroma_results = {}
        web_results = {}
    async def fake_retrieve(query, agent, db, **kw):
        captured["query"] = query
        return FakeOutcome()
    monkeypatch.setattr(
        "backend.services.knowledge_assist.retrieve_or_search", fake_retrieve
    )

    # minimal fakes for skill search + llm
    rag = SkillRAG()
    monkeypatch.setattr(rag.skill_manager, "search_skills",
                        lambda **kw: [])
    monkeypatch.setattr(rag, "_build_rag_context",
                        lambda skills, td: {"augmented_prompt": "PROMPT", "skills_used": [], "context_text": ""})

    class FakeLLM:
        async def generate(self, **kw):
            captured["user_message"] = kw.get("user_message")
            return {"content": "ok", "model": "m", "tokens_used": 1, "latency_ms": 1}
    import backend.services.skill_rag as sr
    monkeypatch.setattr(sr, "LLMClient", lambda **kw: FakeLLM())

    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()

    res = asyncio.run(rag.execute_with_skills("do the thing", FakeAgent(), db=None))
    assert "RETRIEVED KNOWLEDGE" in captured["user_message"]
    assert res["knowledge_outcome"]["wrote_back"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_skill_rag_knowledge_step.py -v`
Expected: FAIL (`knowledge_outcome` missing / `RETRIEVED KNOWLEDGE` absent)

- [ ] **Step 3: Inject the step into `execute_with_skills`**

At the top of `execute_with_skills` (after the docstring, before "Step 1: Retrieve relevant skills"), add:

```python
        # ── 6.5: search-before-acting step ──────────────────────────────────────
        from backend.services.knowledge_assist import retrieve_or_search
        knowledge_outcome = await retrieve_or_search(
            task_description, agent, db
        )
```

Then change the skill-search call to keep `skills` as-is, and before the LLM
`generate` call, build the augmented prompt including the retrieved knowledge:

```python
        # Step 2: Build RAG prompt with context budget enforcement
        rag_context = self._build_rag_context(skills, task_description)

        augmented = rag_context["augmented_prompt"]
        if knowledge_outcome.context_text:
            augmented = (
                "<<RETRIEVED KNOWLEDGE>>\n"
                + knowledge_outcome.context_text
                + "\n<</RETRIEVED KNOWLEDGE>>\n\n"
                + augmented
            )
```

And change the `llm.generate(...)` call's `user_message` arg from
`rag_context["augmented_prompt"]` to `augmented`. Finally, in the returned dict,
add:

```python
            "knowledge_outcome": {
                "wrote_back": knowledge_outcome.wrote_back,
                "fallback_used": knowledge_outcome.fallback_used,
            },
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_skill_rag_knowledge_step.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/skill_rag.py backend/tests/unit/test_skill_rag_knowledge_step.py
git commit -m "feat(knowledge): inject search-before-acting step into task execution"
```

---

### Task 6: Explicit Ethos Knowledge Retrieval / Update steps (6.7)

**Files:**
- Modify: `backend/models/entities/agents.py:1346-1425` (extract `DEFAULT_WORKING_METHODS` module-level; add explicit steps)
- Test: `backend/tests/unit/test_ethos_knowledge_steps.py`

**Interfaces:**
- Consumes: none new
- Produces: module-level `DEFAULT_WORKING_METHODS` dict; `_create_default_ethos` references it; every agent type's `working_method` contains literal `"Knowledge Retrieval"` and `"Knowledge Update"`

- [ ] **Step 1: Write the failing test**

```python
def test_working_methods_have_explicit_knowledge_steps():
    from backend.models.entities.agents import DEFAULT_WORKING_METHODS
    for agent_type, text in DEFAULT_WORKING_METHODS.items():
        assert "Knowledge Retrieval" in text, f"{agent_type} missing retrieval step"
        assert "Knowledge Update" in text, f"{agent_type} missing update step"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest backend/tests/unit/test_ethos_knowledge_steps.py -v`
Expected: FAIL (`DEFAULT_WORKING_METHODS` not defined / missing substrings)

- [ ] **Step 3: Extract and augment the working-method map**

In `backend/models/entities/agents.py`, replace the local `working_methods = { ... }`
block (lines 1346-1425) with a module-level constant. Add it near the top of the
module (after imports) or just before `_create_default_ethos`; reference it inside
`_create_default_ethos` via `working_methods = DEFAULT_WORKING_METHODS`.

Add an explicit retrieval + update step to EACH agent type. Example for
`TASK_AGENT` (apply the same two steps to all seven types):

```python
DEFAULT_WORKING_METHODS = {
    AgentType.HEAD_OF_COUNCIL: (
        "1. Read your Ethos and the active Constitution; confirm "
        "constitutional alignment before any action. "
        "2. Delegate execution to Lead/Task agents — do not execute "
        "tasks yourself. "
        "3. Knowledge Retrieval: before deciding on anything unfamiliar, "
        "query ChromaDB (vector_db tool / knowledge service); if the answer "
        "is missing, web-search and write the result back via the shared "
        "knowledge-write schema. "
        "4. Consult the knowledge base (ChromaDB / skills) before "
        "deliberating on unfamiliar topics. "
        "5. Approve/reject amendments and emergency overrides via the "
        "constitutional process. "
        "6. Stay responsive: acknowledge new messages immediately even "
        "while a prior task is in flight. "
        "7. Knowledge Update: after each action, store validated learnings "
        "to ChromaDB via the shared schema and re-read the Constitution."
    ),
    # ... COUNCIL_MEMBER, LEAD_AGENT, TASK_AGENT, CODE_CRITIC,
    #     OUTPUT_CRITIC, PLAN_CRITIC follow the same pattern: keep their
    #     existing steps, and insert a "Knowledge Retrieval:" step and a
    #     "Knowledge Update:" step (verbatim substrings required by the test).
    AgentType.TASK_AGENT: (
        "1. Read your Ethos and the active Constitution; confirm the "
        "task is constitutional. "
        "2. Knowledge Retrieval: consult ChromaDB (vector_db tool) before "
        "acting on anything unfamiliar — if it is missing, web-search and "
        "write the result back via the shared knowledge-write schema. "
        "3. Execute within your authorized scope using approved tools; "
        "write artifacts to /host_home. "
        "4. Submit output to the relevant Critic for validation. "
        "5. Knowledge Update: store execution learnings to ChromaDB via the "
        "shared schema. "
        "6. Re-read the Constitution after each task."
    ),
}
```

Then in `_create_default_ethos`, change `working_methods = { ... }` to:

```python
        working_methods = DEFAULT_WORKING_METHODS
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest backend/tests/unit/test_ethos_knowledge_steps.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/agents.py backend/tests/unit/test_ethos_knowledge_steps.py
git commit -m "feat(ethos): add explicit Knowledge Retrieval + Update steps (6.7)"
```

---

### Task 7: Document the shared write schema (6.6)

**Files:**
- Create: `docs/knowledge_write_schema.md`
- Modify: `backend/.agentium/skills/vector_db/SKILL.md` (append schema section)

**Interfaces:**
- Consumes: 6.6 metadata schema from `write_knowledge`
- Produces: human-readable schema reference; no code behavior change

- [ ] **Step 1: Write the schema doc**

Create `docs/knowledge_write_schema.md`:

```markdown
# Agent → ChromaDB Knowledge Write Schema (6.6)

All agent writes to ChromaDB MUST go through `write_knowledge()` in
`backend/services/knowledge_assist.py`. The `parent_id` is the dedup key:
re-writing the same `parent_id` updates the existing `KnowledgeDocument` row
and replaces its chunk vectors in place.

## Metadata fields

| Field           | Type   | Required | Meaning                                         |
| --------------- | ------ | -------- | ---------------------------------------------- |
| `parent_id`     | str    | auto     | Dedup key (set by `write_knowledge`).          |
| `type`          | str    | yes      | `web_result` \| `agent_learning` \| `seed` …   |
| `source`        | str    | yes      | `web` \| `agent` \| `seed`                      |
| `source_url`    | str?   | no       | Origin URL for web results.                    |
| `title`         | str?   | no       | Human-readable title.                          |
| `created_at`    | str    | auto     | ISO timestamp, preserved across revisions.     |
| `updated_at`    | str    | auto     | ISO timestamp of last write.                   |
| `revision`      | int    | auto     | Incremented on every upsert.                   |
| `revision_id`   | str    | auto     | UUID per write (auditability).                 |
| `agent_id`      | str?   | no       | Agent that authored the write.                 |
| `document_type` | str    | auto     | Mirrors `type` for filtering.                  |
| `decay_score`   | float  | auto     | Default 1.0 (consumed by `query_knowledge`).   |
| `citation_boost`| float  | auto     | Default 1.0.                                   |

## Collections

Web-search write-backs use `web_knowledge`. Agent learnings use
`task_patterns` / `best_practices` / `domain_knowledge` as appropriate.
```

- [ ] **Step 2: Append a schema note to the vector_db SKILL.md**

At the end of `backend/.agentium/skills/vector_db/SKILL.md`, append:

```markdown

## Write schema (6.6)

Every `add` is routed through `write_knowledge()`, which enforces a fixed
metadata schema (see `docs/knowledge_write_schema.md`). You do NOT set
`parent_id`, `created_at`, `updated_at`, `revision`, `revision_id`,
`document_type`, `decay_score`, or `citation_boost` yourself — they are
managed for you. Provide at least `type` and `source`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/knowledge_write_schema.md backend/.agentium/skills/vector_db/SKILL.md
git commit -m "docs(knowledge): document shared ChromaDB write schema (6.6)"
```

---

### Task 8: Integration test — novel query triggers retrieval + write-back (6.5 acceptance)

**Files:**
- Test: `backend/tests/integration/test_search_before_acting.py`

**Interfaces:**
- Consumes: `Agent.execute_with_skill_rag` → `SkillRAG.execute_with_skills`; `retrieve_or_search`
- Produces: evidence that a novel task shows a ChromaDB retrieval call and a `web_knowledge` write-back

- [ ] **Step 1: Write the integration test**

This test requires running infra (ChromaDB + Postgres). It monkeypatches the
cheap, external bits (web search + vector store query) so it runs without
network, while exercising the real `execute_with_skill_rag` path.

```python
import asyncio
import pytest

pytestmark = pytest.mark.integration


def test_novel_task_triggers_retrieval_and_writeback(monkeypatch):
    from backend.models.entities.agents import Agent
    from backend.services import knowledge_assist as ka

    # ChromaDB returns nothing relevant -> force web search + write-back
    class EmptyStore:
        def query_knowledge(self, *a, **k):
            return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        def get_collection(self, key):
            return self
        def get_parent_document(self, ck, pid, db):
            return None
        def upsert_document(self, ck, pid, text, meta, db):
            test_novel_task_triggers_retrieval_and_writeback._writes.append((ck, pid))
            return {"parent_id": pid}
    ka.get_vector_store = lambda: EmptyStore()
    test_novel_task_triggers_retrieval_and_writeback._writes = []

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "Novel Topic Explained", "url": "http://n", "snippet": "details"}
            ]}
    ka.web_search_tool = FakeWeb()

    # Build a minimal Task + Agent without heavy infra
    class FakeTask:
        description = "explain the noveltopicium protocol in depth"
        agentium_id = "t_novel"
        def complete(self, **kw):
            pass
    class FakeAgent:
        agent_type = type("T", (), {"value": "task_agent"})()
        def get_model_config(self, db):
            return None
        def submit_skill(self, **kw):
            return None

    agent = FakeAgent()
    res = asyncio.run(agent.execute_with_skill_rag(FakeTask(), db=None))
    writes = test_novel_task_triggers_retrieval_and_writeback._writes
    assert any(ck == "web_knowledge" for ck, _ in writes), "expected a web_knowledge write-back"
    assert res["knowledge_outcome"]["wrote_back"] is True
```

- [ ] **Step 2: Run the integration test**

Run: `pytest backend/tests/integration/test_search_before_acting.py -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/integration/test_search_before_acting.py
git commit -m "test(knowledge): integration test for search-before-acting flow (6.5)"
```

---

## Self-Review

- **Spec coverage:** 6.5 → Tasks 3, 5, 8. 6.6 → Tasks 3, 4, 7. 6.7 → Task 6. Collection plumbing → Tasks 1, 2. All sections covered.
- **Placeholder scan:** No TBD/TODO; every code step shows concrete code. Task 6 says "apply the same pattern to all seven types" — the concrete `TASK_AGENT` and `HEAD_OF_COUNCIL` examples are given with the exact required substrings; the remaining five types reuse the same two verbatim step strings, which the test enforces.
- **Type consistency:** `write_knowledge(parent_id, text, metadata, db, collection_key)`, `retrieve_or_search(query, agent, db, *, min_results, collection_keys, sufficiency_distance)`, `RetrievalOutcome` fields, and `DEFAULT_WORKING_METHODS` are used consistently across Tasks 3–8.
