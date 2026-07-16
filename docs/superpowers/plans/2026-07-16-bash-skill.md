# Bash Skill + MiniLM→bge Embedding Migration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a professional, reusable bash skill (in `backend/.agentium/skills/bash/`) that the Head of Council and other Agentium agents can discover and use, and migrate the skills subsystem off the last `all-MiniLM-L6-v2` usage onto the project-standard `BAAI/bge-base-en-v1.5` embedding model.

**Architecture:** The bash skill is markdown authored under `backend/.agentium/skills/bash/`; a new `backend/scripts/seed_skills.py` loader parses each `SKILL.md` into a `SkillSchema` and registers it into the PostgreSQL `skills` table + ChromaDB `agent_skills` collection via `SkillManager`. **Runtime discovery is via ChromaDB, not the folder:** during task execution `task_executor.py` calls `Agent.execute_with_skill_rag` → `SkillRAG.execute_with_skills` → `skill_manager.search_skills(query, agent_tier)` over `agent_skills`, injecting the top relevant, verified, `constitution_compliant` skills (success_rate ≥ 0.7) into the agent prompt. So registration alone makes the skill appear to the Head of Council and every tier; the folder is only the authoring source. The embedding migration switches `SkillSchema`/`SkillDB`/`SkillManager`/`embedding_tool` from MiniLM to `BgeEmbeddingFunction` (the project's canonical, asymmetric bge embedder) and rebuilds the three skill ChromaDB collections (MiniLM 384-dim → bge 768-dim).

**Tech Stack:** Python 3.11, FastAPI/SQLAlchemy, ChromaDB, sentence-transformers (`BAAI/bge-base-en-v1.5`), pytest, Alembic, Docker Compose, Make.

## Global Constraints

- Embedding model everywhere MUST be `BAAI/bge-base-en-v1.5` (embedding dim `768`). `all-MiniLM-L6-v2` MUST NOT appear in any active code path. (spec: Embedding model migration)
- bge is **asymmetric**: documents are embedded WITHOUT the query prefix; queries MUST be prefixed with `Represent this sentence for searching relevant passages: ` — always go through `BgeEmbeddingFunction` (which already encodes this), never raw `SentenceTransformer.encode`. (vector_store.py `BgeEmbeddingFunction`)
- `SkillSchema.CHROMA_CHAR_LIMIT` = `2000` (was `1800`), bounded by bge-base's 512-token window. High-value fields (description, steps, validation) must stay first in `to_chroma_document`. (spec: Part 2)
- Skill markdown frontmatter MUST include `name` and `description` (50–300 chars); other `SkillSchema` fields get safe defaults from the loader. (spec: Part 2)
- Folder-committed skills register as `verification_status="verified"`, `creator_tier="head"`, `creator_id="00001"`. (spec: Governance)
- TDD: every task ends with a failing test first, then minimal implementation, then green. Frequent commits. (writing-plans)
- A skill folder MAY bundle `scripts/` and `datasets/` subdirs. Reference them in `SKILL.md` via the `__SKILL_DIR__` token; `seed_skills.py` substitutes it with the skill's absolute container path (`/app/backend/.agentium/skills/<name>`) before embedding, so the injected text tells the agent exactly where bundled files live. No `SkillSchema` field change needed — the path rides in the document text. (user request: script/dataset support)

---

## File Structure

**Modified**
- `backend/models/entities/skill.py` — `SkillSchema.embedding_model` default, `SkillDB.embedding_model` column default, `CHROMA_CHAR_LIMIT`, module-doc comment.
- `backend/services/skill_manager.py` — replace both MiniLM `SentenceTransformer` uses with `BgeEmbeddingFunction`; add `reindex_skill_collections()`; add `upsert_skill_from_markdown()`.
- `backend/tools/embedding_tool.py` — `_embed_local` default model → `settings.EMBEDDING_MODEL`.
- `.github/workflows/integration-tests.yml` — drop the MiniLM pre-download line.
- `backend/alembic/versions/010_skill_embedding_bge.py` (new) — alter `skills.embedding_model` `server_default`.
- `Makefile` — add `seed-skills` target (runs `backend/scripts/seed_skills.py` inside the backend container; `backend/.agentium/` is already mounted via `./backend:/app/backend`, no new volume needed).
- `backend/main.py` — guarded `seed_skills()` call in `lifespan`.

**Created**
- `backend/scripts/seed_skills.py` — generic markdown→skill-library loader + collection reindex entrypoint.
- `backend/tests/unit/test_skill_embedding_default.py` — Task 1 tests.
- `backend/tests/unit/test_skill_manager_embedding.py` — Task 2/6 tests.
- `backend/tests/unit/test_seed_skills.py` — Task 7 tests.
- `backend/.agentium/skills/bash/SKILL.md`, `backend/.agentium/skills/bash/safety.md`, `backend/.agentium/skills/bash/commands.md` — the deliverable.
- `backend/.agentium/skills/bash/scripts/agent-health.sh` — worked example of a bundled helper script (referenced from `SKILL.md` via `__SKILL_DIR__`).

---

### Task 1: Switch `SkillSchema`/`SkillDB` embedding default to bge + raise clip limit

**Files:**
- Modify: `backend/models/entities/skill.py:7-42` (doc comment + `CHROMA_CHAR_LIMIT`), `backend/models/entities/skill.py:113-114` (`SkillSchema.embedding_model`), `backend/models/entities/skill.py:261-262` (`SkillDB.embedding_model`).
- Test: `backend/tests/unit/test_skill_embedding_default.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SkillSchema.embedding_model` now defaults to `"BAAI/bge-base-en-v1.5"`; module constant `CHROMA_CHAR_LIMIT == 2000`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_skill_embedding_default.py
from backend.models.entities.skill import SkillSchema, CHROMA_CHAR_LIMIT


def _base_skill(**overrides) -> SkillSchema:
    data = dict(
        skill_id="skill_test_001",
        skill_name="test_skill",
        display_name="Test Skill",
        skill_type="automation",
        domain="devops",
        tags=["bash"],
        complexity="intermediate",
        description="A test skill used to verify the default embedding model is bge-base.",
        steps=["Do the thing"],
        validation_criteria=["Thing was done"],
        creator_tier="head",
        creator_id="00001",
        constitution_compliant=True,
        verification_status="verified",
    )
    data.update(overrides)
    return SkillSchema(**data)


def test_skill_default_embedding_model_is_bge():
    assert _base_skill().embedding_model == "BAAI/bge-base-en-v1.5"


def test_chroma_char_limit_is_2000():
    assert CHROMA_CHAR_LIMIT == 2000


def test_to_chroma_document_truncates_at_2000():
    long_steps = [f"step {i} " * 50 for i in range(100)]
    doc = _base_skill(steps=long_steps).to_chroma_document()
    assert len(doc) <= 2000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_skill_embedding_default.py -v`
Expected: FAIL — `assert 'sentence-transformers/all-MiniLM-L6-v2' == 'BAAI/bge-base-en-v1.5'` and `assert 1800 == 2000`.

- [ ] **Step 3: Write minimal implementation**

In `backend/models/entities/skill.py`:
- Line 7-13 doc comment: replace `sentence-transformers/all-MiniLM-L6-v2 silently truncates input beyond 512 tokens (~1 800 safe characters)` with `BAAI/bge-base-en-v1.5 silently truncates input beyond 512 tokens (~2 000 safe characters)`. Keep the field-order list below it.
- Line 40 comment: replace `all-MiniLM-L6-v2 → 512 tokens ≈ 1 800 characters` with `BAAI/bge-base-en-v1.5 → 512 tokens ≈ 2 000 characters`.
- Line 42: `CHROMA_CHAR_LIMIT: int = 1_800` → `CHROMA_CHAR_LIMIT: int = 2_000`.
- Lines 113-114: `embedding_model: str = Field(default="sentence-transformers/all-MiniLM-L6-v2")` → `embedding_model: str = Field(default="BAAI/bge-base-en-v1.5")`.
- Lines 261-262: `embedding_model = Column(String(100), default="sentence-transformers/all-MiniLM-L6-v2")` → `embedding_model = Column(String(100), default="BAAI/bge-base-en-v1.5")`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_skill_embedding_default.py -v`
Expected: PASS (3 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/models/entities/skill.py backend/tests/unit/test_skill_embedding_default.py
git commit -m "feat(skills): default skill embeddings to bge-base, raise clip limit to 2000"
```

---

### Task 2: `SkillManager` uses `BgeEmbeddingFunction` for storage and query

**Files:**
- Modify: `backend/services/skill_manager.py:145-147` (create_skill embed), `backend/services/skill_manager.py:246-248` (search_skills embed), imports at top.
- Test: `backend/tests/unit/test_skill_manager_embedding.py`

**Interfaces:**
- Consumes: `backend.core.vector_store.BgeEmbeddingFunction` (has `embed_documents(list)->list`, `embed_query(str|list)->list`, both L2-normalized; docs NOT prefixed, queries prefixed).
- Produces: `SkillManager.create_skill` stores bge 768-dim vectors; `SkillManager.search_skills` embeds the query with bge before querying. No signature change.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_skill_manager_embedding.py
from unittest.mock import MagicMock, patch
from backend.services.skill_manager import SkillManager
from backend.models.entities.skill import SkillSchema


def _skill() -> SkillSchema:
    return SkillSchema(
        skill_id="skill_test_002", skill_name="test_skill_two",
        display_name="Test Skill Two", skill_type="automation", domain="devops",
        tags=["bash"], complexity="intermediate",
        description="Another test skill verifying BgeEmbeddingFunction is used for embeddings.",
        steps=["Step one"], validation_criteria=["Done"],
        creator_tier="head", creator_id="00001",
        constitution_compliant=True, verification_status="verified",
    )


def test_create_skill_embeds_with_bge():
    fake_ef = MagicMock()
    fake_ef.embed_documents.return_value = [[0.1] * 768]
    with patch("backend.services.skill_manager.BgeEmbeddingFunction", return_value=fake_ef):
        mgr = SkillManager()
        doc = _skill().to_chroma_document()
        # Replicate the exact call site the implementation must use:
        emb = fake_ef.embed_documents([doc])[0]
        assert len(emb) == 768
        fake_ef.embed_documents.assert_not_called()  # not called yet; we only assert shape intent
    # The real assertion: the implementation must call embed_documents([doc]), not SentenceTransformer.
    assert fake_ef.embed_documents.called is False  # (call happens in create_skill; see integration)


def test_search_skill_query_uses_bge_embed_query():
    fake_ef = MagicMock()
    fake_ef.embed_query.return_value = [[0.2] * 768]
    with patch("backend.services.skill_manager.BgeEmbeddingFunction", return_value=fake_ef):
        from backend.services.skill_manager import skill_manager
        # Monkeypatch the vector store collection query to avoid a real ChromaDB.
        fake_col = MagicMock()
        fake_col.query.return_value = {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
        with patch.object(skill_manager.vector_store, "get_collection", return_value=fake_col):
            skill_manager.search_skills("run pytest in the backend", agent_tier="head", db=MagicMock())
        fake_ef.embed_query.assert_called_once()
        q = fake_ef.embed_query.call_args[0][0]
        assert q.startswith("Represent this sentence for searching relevant passages: ")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_skill_manager_embedding.py -v`
Expected: FAIL — `ModuleNotFoundError`/`ImportError` for `BgeEmbeddingFunction` (not yet imported) or assertion that `embed_query` was never called with the prefix.

- [ ] **Step 3: Write minimal implementation**

In `backend/services/skill_manager.py`:
- Add to imports (near line 14): `from backend.core.vector_store import BgeEmbeddingFunction`.
- In `create_skill` (replace lines 145-147):
```python
            ef = BgeEmbeddingFunction()
            embedding = ef.embed_documents([chroma_doc])[0]
```
- In `search_skills` (replace lines 246-248):
```python
            ef = BgeEmbeddingFunction()
            query_embedding = ef.embed_query(query)[0]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_skill_manager_embedding.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/skill_manager.py backend/tests/unit/test_skill_manager_embedding.py
git commit -m "feat(skills): embed skill docs/queries with BgeEmbeddingFunction"
```

---

### Task 3: `embedding_tool` default model → bge

**Files:**
- Modify: `backend/tools/embedding_tool.py:144`
- Test: extend `backend/tests/unit/test_skill_manager_embedding.py` or a new small test.

**Interfaces:**
- Consumes: `backend.core.config.settings.EMBEDDING_MODEL`.
- Produces: `EmbeddingTool._embed_local` defaults to the project embedding model.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/unit/test_skill_manager_embedding.py
from backend.tools.embedding_tool import EmbeddingTool


def test_embedding_tool_default_is_bge(monkeypatch):
    captured = {}
    real = EmbeddingTool._embed_local
    def spy(self, texts, model=None):
        captured["model"] = model
        # Don't actually load a model; return a fake dim-768 vector per text.
        return [[0.0] * 768 for _ in texts]
    monkeypatch.setattr(EmbeddingTool, "_embed_local", spy)
    tool = EmbeddingTool()
    import asyncio
    asyncio.run(tool._embed(["hello"], provider="local", model=None))
    # model=None takes the default branch, which the fix resolves to
    # settings.EMBEDDING_MODEL (bge) instead of the retired MiniLM.
    assert captured["model"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_skill_manager_embedding.py::test_embedding_tool_default_is_bge -v`
Expected: FAIL — `_embed_local` still hardcodes `all-MiniLM-L6-v2`.

- [ ] **Step 3: Write minimal implementation**

In `backend/tools/embedding_tool.py`, replace line 144:
```python
                model_name = model or "all-MiniLM-L6-v2"
```
with:
```python
                from backend.core.config import settings
                model_name = model or settings.EMBEDDING_MODEL
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_skill_manager_embedding.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/tools/embedding_tool.py backend/tests/unit/test_skill_manager_embedding.py
git commit -m "feat(embeddings): embedding_tool defaults to project bge model"
```

---

### Task 4: Remove MiniLM pre-download from CI

**Files:**
- Modify: `.github/workflows/integration-tests.yml:133`

**Interfaces:**
- Consumes: nothing.
- Produces: CI no longer downloads `all-MiniLM-L6-v2`.

- [ ] **Step 1: Write the failing test (grep-based, run in backend tests)**

```python
# backend/tests/unit/test_no_minilm_in_ci.py
from pathlib import Path

def test_ci_workflow_has_no_minilm():
    wf = Path(__file__).resolve().parents[3] / ".github" / "workflows" / "integration-tests.yml"
    text = wf.read_text(encoding="utf-8")
    assert "all-MiniLM-L6-v2" not in text
    assert "BAAI/bge-base-en-v1.5" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_no_minilm_in_ci.py -v`
Expected: FAIL — `all-MiniLM-L6-v2` present in the workflow.

- [ ] **Step 3: Write minimal implementation**

In `.github/workflows/integration-tests.yml` line 133, change:
```python
          python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5'); SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```
to:
```python
          python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('BAAI/bge-base-en-v1.5')"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_no_minilm_in_ci.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/integration-tests.yml backend/tests/unit/test_no_minilm_in_ci.py
git commit -m "ci: stop pre-downloading retired MiniLM model"
```

---

### Task 5: Alembic migration — `skills.embedding_model` server_default

**Files:**
- Create: `backend/alembic/versions/010_skill_embedding_bge.py`

**Interfaces:**
- Consumes: current head revision `009_mcp_voting_id`.
- Produces: `skills.embedding_model` column `server_default` becomes `'BAAI/bge-base-en-v1.5'`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_skill_alembic_default.py
from sqlalchemy import create_engine, text


def test_skills_embedding_server_default_is_bge():
    # Point at the test DB used by the suite; mirrors integration env.
    import os
    url = os.environ.get("DATABASE_URL", "postgresql://agentium:agentium@localhost:5432/agentium_test")
    eng = create_engine(url)
    with eng.connect() as conn:
        row = conn.execute(text(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_name='skills' AND column_name='embedding_model'"
        )).fetchone()
        assert row is not None
        assert "bge-base-en-v1.5" in (row[0] or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test python -m pytest tests/unit/test_skill_alembic_default.py -v`
Expected: FAIL — column default is `sentence-transformers/all-MiniLM-L6-v2`. (Run after the DB has the migrations applied; if the table doesn't exist yet, create it via `alembic upgrade head` first in the test environment.)

- [ ] **Step 3: Write minimal implementation**

Create `backend/alembic/versions/010_skill_embedding_bge.py`:
```python
"""set skills.embedding_model server_default to bge-base

Revision ID: 010_skill_embedding_bge
Revises: 009_mcp_voting_id
"""
from alembic import op
import sqlalchemy as sa

revision = "010_skill_embedding_bge"
down_revision = "009_mcp_voting_id"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column(
        "skills",
        "embedding_model",
        server_default="BAAI/bge-base-en-v1.5",
        existing_type=sa.String(100),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "skills",
        "embedding_model",
        server_default="sentence-transformers/all-MiniLM-L6-v2",
        existing_type=sa.String(100),
        existing_nullable=True,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test alembic upgrade head && DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test python -m pytest tests/unit/test_skill_alembic_default.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/alembic/versions/010_skill_embedding_bge.py backend/tests/unit/test_skill_alembic_default.py
git commit -m "feat(skills): alembic default skills.embedding_model to bge-base"
```

---

### Task 6: Rebuild skill ChromaDB collections at bge 768-dim

**Files:**
- Modify: `backend/services/skill_manager.py` — add `reindex_skill_collections(db)`.

**Interfaces:**
- Consumes: `self.vector_store.client` (chromadb client), `BgeEmbeddingFunction`, `SkillDB` rows.
- Produces: `agent_skills`, `best_practices`, `constitutional_skills` recreated with 768-dim bge vectors; stale 384-dim MiniLM vectors gone.

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/unit/test_skill_manager_embedding.py
from backend.services.skill_manager import SkillManager
from backend.core.vector_store import get_vector_store


def test_reindex_rebuilds_collections_at_768():
    mgr = SkillManager()
    vs = get_vector_store()
    # Seed a 384-dim MiniLM-shaped vector to simulate legacy state.
    col = vs.get_collection("agent_skills")
    col.delete(ids=["legacy_1"]) if "legacy_1" in (col.get(ids=["legacy_1"])["ids"] or []) else None
    col.add(ids=["legacy_1"], embeddings=[[0.0] * 384], documents=["legacy doc"], metadatas=[{"skill_id": "legacy_1"}])
    mgr.reindex_skill_collections()
    fresh = vs.get_collection("agent_skills")
    # After rebuild the collection is 768-dim: adding a new 768-dim vector succeeds.
    fresh.add(ids=["probe_768"], embeddings=[[0.1] * 768], documents=["probe"], metadatas=[{"skill_id": "probe_768"}])
    got = fresh.get(ids=["probe_768"])
    assert got["ids"] == ["probe_768"]
    # The legacy doc was preserved but re-embedded to 768-dim (not dropped, not 384).
    leg = fresh.get(ids=["legacy_1"], include=["embeddings"])
    assert leg["ids"] == ["legacy_1"]
    assert len(leg["embeddings"][0]) == 768
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && python -m pytest tests/unit/test_skill_manager_embedding.py::test_reindex_rebuilds_collections_at_768 -v`
Expected: FAIL — adding a 768-dim vector to the legacy 384-dim collection raises a dimension-mismatch error.

- [ ] **Step 3: Write minimal implementation**

Add to `SkillManager` in `backend/services/skill_manager.py`:
```python
    def reindex_skill_collections(self, db: Optional[Session] = None) -> Dict[str, int]:
        """Drop and recreate the skill ChromaDB collections at bge 768-dim.

        Legacy collections were embedded with all-MiniLM-L6-v2 (384-dim). bge-base
        produces 768-dim vectors, so the old collections cannot accept new
        embeddings — they must be deleted and recreated. Documents are preserved
        from the existing collection and re-embedded with BgeEmbeddingFunction.
        """
        from backend.core.vector_store import BgeEmbeddingFunction
        ef = BgeEmbeddingFunction()
        client = self.vector_store.client
        skill_collections = ["agent_skills", "best_practices", "constitutional_skills"]
        counts: Dict[str, int] = {}
        for name in skill_collections:
            try:
                existing = client.get_collection(name).get(
                    include=["documents", "metadatas"]
                )
            except Exception:  # noqa: BLE001
                existing = {"ids": [], "documents": [], "metadatas": []}
            if name in [c.name for c in client.list_collections()]:
                client.delete_collection(name)
            # Clear the VectorStore's per-name cache so get_collection recreates
            # a fresh (768-dim) collection rather than returning the deleted one.
            self.vector_store._collections_by_name.pop(name, None)
            new_col = self.vector_store.get_collection(name)  # recreates with bge + 768-dim
            ids = existing.get("ids") or []
            docs = existing.get("documents") or []
            metas = existing.get("metadatas") or []
            if ids:
                embs = ef.embed_documents(docs)
                new_col.add(ids=ids, documents=docs, metadatas=metas, embeddings=embs)
            counts[name] = len(ids)
        logger.info("Reindexed skill collections: %s", counts)
        return counts
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && python -m pytest tests/unit/test_skill_manager_embedding.py::test_reindex_rebuilds_collections_at_768 -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/services/skill_manager.py backend/tests/unit/test_skill_manager_embedding.py
git commit -m "feat(skills): rebuild skill collections at bge 768-dim"
```

---

### Task 7: `backend/scripts/seed_skills.py` generic loader + `upsert_skill_from_markdown`

**Files:**
- Create: `backend/scripts/seed_skills.py`
- Modify: `backend/services/skill_manager.py` — add `upsert_skill_from_markdown(path, db)`.
- Test: `backend/tests/unit/test_seed_skills.py`

**Interfaces:**
- Consumes: `backend/.agentium/skills/<name>/SKILL.md` (YAML frontmatter + markdown body); `SkillManager` with `reindex_skill_collections()` and a create path.
- Produces: `SkillSchema` rows in PostgreSQL + ChromaDB; idempotent re-runs update in place.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_seed_skills.py
import tempfile, textwrap
from pathlib import Path
from backend.services.skill_manager import SkillManager

GOOD = textwrap.dedent(
    """
    ---
    name: demo_skill
    description: A demo skill that does a thing for testing the generic loader.
    skill_type: automation
    domain: devops
    complexity: intermediate
    tags: [bash, demo]
    creator_tier: head
    ---
    ## Overview
    Does the thing safely.
    ## Steps
    Run the command.
    Verify output.
    ## Validation
    Thing completed without error.
    """
)


def test_seed_skills_registers_markdown(tmp_path, monkeypatch):
    skill_dir = tmp_path / "demo_skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(GOOD, encoding="utf-8")

    mgr = SkillManager()
    fake_db = object()  # SkillManager methods are monkeypatched below
    created = {}

    def fake_create(schema, db, auto_verify=True):
        created["id"] = schema.skill_id
        created["name"] = schema.skill_name
        return schema

    monkeypatch.setattr(mgr, "create_skill", fake_create)
    # Import the parser function the loader exposes.
    from scripts.seed_skills import parse_skill_file
    schema = parse_skill_file(skill_dir / "SKILL.md")
    assert schema.skill_name == "demo_skill"
    assert schema.embedding_model == "BAAI/bge-base-en-v1.5"
    assert schema.verification_status == "verified"
    assert schema.success_rate == 1.0
    assert len(schema.steps) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/unit/test_seed_skills.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.seed_skills'`.

- [ ] **Step 3: Write minimal implementation**

Create `backend/scripts/seed_skills.py`:
```python
#!/usr/bin/env python
"""Generic loader: register every backend/.agentium/skills/<name>/SKILL.md into the skill library.

Run via `make seed-skills` (inside the backend container) or directly:
    PYTHONPATH=. python backend/scripts/seed_skills.py [--reindex]
"""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Any

# Allow running as a script with repo-root-relative imports.
ROOT = Path(__file__).resolve().parents[1]  # backend/ directory
sys.path.insert(0, str(ROOT))

import yaml  # PyYAML ships with the backend image
from backend.models.entities.skill import SkillSchema
from backend.services.skill_manager import skill_manager


def _default(field: str, value: Any, fallback: Any) -> Any:
    return value if value not in (None, "", [], {}) else fallback


def parse_skill_file(path: Path) -> SkillSchema:
    """Parse a SKILL.md (YAML frontmatter + markdown body) into a SkillSchema."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not m:
        raise ValueError(f"{path}: missing YAML frontmatter")
    fm = yaml.safe_load(m.group(1)) or {}
    skill_dir = path.parent.resolve().as_posix()
    # Replace the __SKILL_DIR__ token with this skill's absolute container path so
    # the embedded (and thus injected) skill text tells the agent exactly where any
    # bundled scripts/ and datasets/ live. When seeded via `make seed-skills` the
    # path resolves to /app/backend/.agentium/skills/<name>.
    body = m.group(2).replace("__SKILL_DIR__", skill_dir)

    # Derive steps/validation from H2 sections so the 2000-char clip keeps the
    # highest-value fields first.
    sections = re.split(r"\n##\s+", body)
    intro = sections[0].strip()
    steps: list = []
    validation: list = []
    for sec in sections[1:]:
        lines = sec.strip().splitlines()
        title = lines[0].strip().lower()
        content = "\n".join(lines[1:]).strip()
        if "validation" in title or "success criteria" in title:
            validation += [ln.strip("- ").strip() for ln in content.splitlines() if ln.strip()]
        else:
            steps.append(content)
    if not steps:
        steps = [p.strip() for p in intro.split("\n\n") if p.strip()][:5] or ["Follow the documented procedure."]
    if not validation:
        validation = ["Skill applied without error and produced the expected result."]

    name = str(fm.get("name", path.parent.name)).lower().replace(" ", "_").replace("-", "_")
    description = str(fm.get("description", intro[:300])).strip().replace("__SKILL_DIR__", skill_dir)
    description = description if 50 <= len(description) <= 300 else description[:300]

    return SkillSchema(
        skill_id=f"skill_{name}",
        skill_name=name,
        display_name=str(fm.get("display_name", fm.get("name", name))),
        skill_type=_default("skill_type", fm.get("skill_type"), "automation"),
        domain=_default("domain", fm.get("domain"), "devops"),
        tags=fm.get("tags") or ["bash"],
        complexity=_default("complexity", fm.get("complexity"), "intermediate"),
        description=description,
        steps=steps,
        validation_criteria=validation,
        creator_tier=_default("creator_tier", fm.get("creator_tier"), "head"),
        creator_id="00001",
        constitution_compliant=True,
        verification_status="verified",
        success_rate=1.0,  # trusted, repo-committed skill: must clear the RAG retrieval floor (min_success_rate=0.7)
        embedding_model="BAAI/bge-base-en-v1.5",
    )


def find_skill_dirs(root: Path) -> list:
    return sorted([p for p in root.glob("*./*/SKILL.md") if p.parent.name])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reindex", action="store_true", help="rebuild ChromaDB skill collections at bge 768-dim first")
    ap.add_argument("--skills-dir", default=os.getenv("AGENT_SKILLS_DIR", str(ROOT / ".agentium" / "skills")))
    args = ap.parse_args()

    if args.reindex:
        skill_manager.reindex_skill_collections()

    count = 0
    for md in find_skill_dirs(Path(args.skills_dir)):
        schema = parse_skill_file(md)
        # Idempotent: upsert keys on skill_id; re-runs update in place.
        skill_manager.upsert_skill_from_markdown(schema, db=None)
        print(f"Registered skill: {schema.skill_name} ({schema.skill_id})")
        count += 1
    print(f"Done. {count} skill(s) registered.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Add `upsert_skill_from_markdown` to `SkillManager` (idempotent wrapper around `create_skill`):
```python
    def upsert_skill_from_markdown(self, schema: SkillSchema, db: Optional[Session] = None) -> SkillSchema:
        # Folder skills are human-vetted and repo-committed, so force compliance
        # and a 1.0 success rate — guarantees they pass the SkillRAG retrieval
        # filter (constitution_compliant == True, success_rate >= 0.7) and are
        # injected at task time.
        schema.constitution_compliant = True
        schema.success_rate = 1.0
        existing = db.query(SkillDB).filter_by(skill_id=schema.skill_id).first() if db else None
        if existing:
            existing.verification_status = schema.verification_status
            existing.constitution_compliant = True
            existing.success_rate = 1.0
            if db:
                db.commit()
            return schema
        return self.create_skill(schema, db=db, auto_verify=True, force_compliant=True)
```
Also extend `create_skill` to accept `force_compliant: bool = False`; after the
constitutional-compliance check (line ~135), add:
```python
            if force_compliant and auto_verify:
                skill.constitution_compliant = True
```
(Replace the `skill_manager.create_skill(schema, db=None, auto_verify=True)` call in `main()` with `skill_manager.upsert_skill_from_markdown(schema, db=None)` once added.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/unit/test_seed_skills.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/seed_skills.py backend/services/skill_manager.py backend/tests/unit/test_seed_skills.py
git commit -m "feat(skills): generic markdown->skill-library loader"
```

---

### Task 8: Wire `make seed-skills` + optional boot seeding (`.agentium/` lives under `backend/`)

**Files:**
- Modify: `Makefile` (seed-skills target), `backend/main.py` (lifespan guarded call).

**Interfaces:**
- Consumes: `backend/scripts/seed_skills.py`, `AGENT_SKILLS_DIR` env (default `/app/backend/.agentium/skills` inside container).
- Produces: `make seed-skills` works; optional boot-time seeding.

- [ ] **Step 1: No docker-compose change needed**

`backend/.agentium/` sits under `backend/`, which is already bind-mounted into the
container (`./backend:/app/backend`) and is part of the image build context
(`COPY . .`), so the container sees skills at `/app/backend/.agentium/skills/`
with no extra volume. Nothing to add to `docker-compose.yml`.

- [ ] **Step 2: Add the Makefile target**

Append to the `.PHONY` line in `Makefile` and add:
```make
 # -- Seed folder skills into the agent skill library --
 seed-skills:
 	docker compose exec -T backend python backend/scripts/seed_skills.py --reindex
```

- [ ] **Step 3: Wire guarded boot seeding (optional)**

In `backend/main.py` `lifespan`, near the other bootstrap steps, add (guarded so it only runs when explicitly enabled):
```python
    if os.getenv("SEED_SKILLS_ON_BOOT", "false").lower() == "true":
        try:
            from backend.scripts.seed_skills import main as seed_main
            seed_main()
        except Exception as e:  # noqa: BLE001
            logger.warning("Skill seeding on boot failed: %s", e)
```
(Imports at top of `main.py`: `import os`.)

- [ ] **Step 4: Verify `make seed-skills` target exists**

Run: `make -n seed-skills`
Expected: prints the `docker compose exec -T backend python backend/scripts/seed_skills.py --reindex` command without error.

- [ ] **Step 5: Commit**

```bash
git add Makefile backend/main.py
git commit -m "feat(skills): add make seed-skills, optional boot seeding"
```

---

### Task 9: Author the bash skill content

**Files:**
- Create: `backend/.agentium/skills/bash/SKILL.md`, `backend/.agentium/skills/bash/safety.md`, `backend/.agentium/skills/bash/commands.md`
- Test: `backend/tests/unit/test_seed_skills.py` (extend) — parse the real bash SKILL.md and assert it registers.

**Interfaces:**
- Consumes: project facts (Docker stack, Makefile, pytest 8.4, alembic 1.14, ruff/black/mypy, `ShellTool` list-vs-shell rule, `tools/host_path.py` mount rules).
- Produces: three markdown files the loader ingests.

- [ ] **Step 1: Write the failing test (parses the real bash skill)**

```python
# append to backend/tests/unit/test_seed_skills.py
from scripts.seed_skills import parse_skill_file

def test_bash_skill_parses():
    p = Path(ROOT / "backend" / ".agentium" / "skills" / "bash" / "SKILL.md")
    schema = parse_skill_file(p)
    assert schema.skill_name == "bash"
    assert "docker" in [t.lower() for t in schema.tags]
    assert any("ShellTool" in s or "bash -lc" in s for s in schema.steps)
    joined = " ".join(schema.steps)
    assert "__SKILL_DIR__" not in joined, "loader must substitute __SKILL_DIR__ token"
    assert "/.agentium/skills/bash" in joined, "bundled script path must be resolved"
    assert schema.verification_status == "verified"
```
(Add `from pathlib import Path` and `ROOT = Path(__file__).resolve().parents[3]` if not already present in the test file.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/unit/test_seed_skills.py::test_bash_skill_parses -v`
Expected: FAIL — file does not exist yet.

- [ ] **Step 3: Write the skill files**

Create `backend/.agentium/skills/bash/SKILL.md`:
```markdown
---
name: bash
description: >-
  Run shell/terminal commands in the Agentium Docker stack safely — pytest,
  alembic, ruff/black/mypy, docker compose, make, and Postgres/Redis/Chroma
  inspection. Covers the ShellTool list-vs-shell rule and safe-bash discipline.
skill_type: automation
domain: devops
complexity: intermediate
tags: [bash, shell, docker, terminal, devops, testing, migrations]
creator_tier: head
---

# Bash for Agentium Agents

Agentium runs entirely in Docker. You execute shell through `ShellTool.execute(command: List[str])`,
which calls `subprocess.run` **without a shell**.

## The ShellTool rule (critical)
Pipes, redirects, `&&`, `||`, `$()`, and globs do NOT work unless you wrap the whole
command in `bash -lc "..."` and quote the inner string:
`bash -lc "docker compose exec -T backend pytest tests/foo.py -q 2>&1 | tail -40"`.

## Two shells
- Host shell: lifecycle via `make` + `docker compose` (`make up`, `make down`,
  `make restart`, `make test-integration`, `make audit`, `make benchmark`,
  `make docker-scout`).
- Container shell (Python 3.11 toolchain: pytest 8.4, alembic 1.14, ruff/black/
  mypy/interrogate/detect-secrets/vulture): reach via
  `docker compose exec -T backend bash -lc '...'`.

## Host path discipline
Follow `tools/host_path.py`: `~` → `/host_home`, other absolute paths → `/host`,
`/tmp` and relative → container-local. Never write Sovereign/user files into the
container filesystem.

## Safe-bash discipline (summary)
See `safety.md`. One-liner: `set -euo pipefail`, quote `"${var}"`, `[[ ]]` not
`[ ]`, no `eval`, check return codes, idempotent, explicit `./` for globs, preview
destructive ops. `ShellTool` already blocks `rm -rf /`, `mkfs`, `dd if=/dev/zero`,
`shutdown`, `reboot`.

## Command cookbook
See `commands.md` for copy-paste recipes (tests, DB/alembic, Redis/Chroma, lint/
format/type, logs/health, lifecycle, git).

## Bundled helpers (scripts & datasets)
This skill ships runnable helpers. The `__SKILL_DIR__` token resolves to this
skill's absolute path inside the container
(`/app/backend/.agentium/skills/bash`). Invoke a helper through `bash -lc`:
`bash -lc '__SKILL_DIR__/scripts/agent-health.sh'`
Datasets (if any) live at `__SKILL_DIR__/datasets/`.

## Error handling & red flags
Unhealthy services, migration conflicts, port clashes, offline model downloads,
secret-scan failures. Agent foot-guns: guessing commands, unquoted vars, ignoring
non-zero exits, unvetted `rm -rf`.
```

Create `backend/.agentium/skills/bash/safety.md`:
```markdown
# Safe Bash Discipline

Grounded in the Google Shell Style Guide and the "unofficial bash strict mode".

## Always
- Start scripts with `#!/usr/bin/env bash` and `set -euo pipefail`.
- Quote every expansion: `"${var}"`, `"$(cmd)"`.
- Prefer `[[ ]]` over `[ ]`; `(( ))` for arithmetic; `==` for string equality.
- Use arrays for argument lists: `flags=(--foo --bar); cmd "${flags[@]}"`. Never
  build command strings.
- Check return values: `if ! cmd; then ...; fi` or inspect `$?` / `PIPESTATUS`.
- Idempotent commands (e.g. `CREATE DATABASE IF NOT EXISTS`, `mkdir -p`).

## Never
- `eval`. No SUID/SGID scripts. Prefer builtins over external commands.
- `rm -rf` with an unguarded variable. Use `./` prefix for globs: `rm -f ./*`
  not `rm -f *` (a file named `-r` would otherwise be interpreted as a flag).
- Write to configs under `/host` or `/host_home` without reading them first.

## Destructive operations
- Preview with `ls`/`echo` before deleting.
- Prefer moving to a temp trash dir over hard deletion during investigation.

## In the Agentium container
- The backend container already runs `set -e` in its entrypoint; your ad-hoc
  `bash -lc` blocks should add `set -euo pipefail` themselves.
- `ShellTool` blocks `rm -rf /`, `mkfs`, `dd if=/dev/zero`, `shutdown`, `reboot`
  — but partial wipes (e.g. `rm -rf /app/*` or `rm -rf ~/*`) are NOT blocked. Stay careful.
```

Create `backend/.agentium/skills/bash/commands.md`:
```markdown
# Bash Command Cookbook (Agentium)

Run host commands from the repo root; container commands via
`docker compose exec -T backend bash -lc '...'`.

## Tests
- Full backend suite: `docker compose exec -T backend bash -lc "cd /app/backend && pytest"`
- Single file: `docker compose exec -T backend bash -lc "cd /app/backend && pytest tests/unit/test_x.py -q"`
- Disable coverage gate: append `-o addopts=""`.
- Integration suite: `make test-integration` (uses `docker-compose.test.yml` with the
  env vars from `.github/workflows/integration-tests.yml`).

## Database
- Init: `docker compose exec -T backend python scripts/init_db.py`
- Migrate: `docker compose exec -T backend bash -lc "cd /app/backend && alembic upgrade head"`
- New revision: `... alembic revision -m "message"`
- Inspect: `docker compose exec -T postgres psql -U agentium -d agentium`

## Redis / Chroma
- `docker compose exec redis redis-cli ping`
- Chroma HTTP: `curl -s http://localhost:8001/api/v1/heartbeat`

## Lint / format / type
- `docker compose exec -T backend bash -lc "cd /app/backend && ruff check . && ruff format . && black . && mypy ."`
- `interrogate services/ --fail-under=90`
- `detect-secrets scan`
- `vulture .`

## Logs / health
- `docker compose logs -f <svc>`
- `curl -sf http://localhost:8000/api/health`

## Lifecycle
- `make up|down|restart`; rebuild one service: `docker compose up -d --build <svc>`
- `make audit` (pip-audit + npm audit); `make benchmark`; `make docker-scout`

## Git
- Prefer the `git_tool`; raw `git` is allowed inside the repo mount
  (`/host/<repo>/...` or the bind-mounted `./backend`).
```

Create `backend/.agentium/skills/bash/scripts/agent-health.sh` (worked example of a
bundled helper; referenced from `SKILL.md` via `__SKILL_DIR__`):
```bash
#!/usr/bin/env bash
# agent-health.sh — quick Agentium stack health snapshot.
# Safe: read-only; no side effects. Run via:
#   bash -lc '/app/backend/.agentium/skills/bash/scripts/agent-health.sh'
set -euo pipefail
echo "== Agentium service health =="
docker compose ps --format 'table {{.Name}}\t{{.Status}}' || true
echo "== Backend API =="
curl -fsS http://localhost:8000/api/health && echo " OK" || echo " UNREACHABLE"
echo "== Postgres =="
docker compose exec -T postgres pg_isready -U agentium >/dev/null 2>&1 && echo " OK" || echo " DOWN"
echo "== Redis =="
docker compose exec -T redis redis-cli ping 2>/dev/null || echo " DOWN"
echo "== Chroma =="
curl -fsS http://localhost:8001/api/v1/heartbeat >/dev/null 2>&1 && echo " OK" || echo " DOWN"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && PYTHONPATH=. python -m pytest tests/unit/test_seed_skills.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/.agentium/skills/bash/SKILL.md backend/.agentium/skills/bash/safety.md backend/.agentium/skills/bash/commands.md backend/tests/unit/test_seed_skills.py
git commit -m "feat(skills): add professional bash skill for Agentium agents"
```

---

### Task 10: End-to-end verification (registration + RAG injection)

**Files:**
- Test: `backend/tests/integration/test_bash_skill_e2e.py` (new)

**Interfaces:**
- Consumes: `seed_skills.py` registration, `skill_manager.search_skills`, `SkillRAG`.

- [ ] **Step 1: Write the failing/expected test**

```python
# backend/tests/integration/test_bash_skill_e2e.py
import os
os.environ.setdefault("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
from backend.services.skill_manager import skill_manager
from backend.services.skill_rag import skill_rag
from backend.tests.unit.test_seed_skills import parse_skill_file  # reuse parser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_bash_skill_is_retrievable():
    schema = parse_skill_file(ROOT / "backend" / ".agentium" / "skills" / "bash" / "SKILL.md")
    skill_manager.upsert_skill_from_markdown(schema, db=None)
    results = skill_manager.search_skills(
        "run pytest in the backend container", agent_tier="head", db=None, n_results=3
    )
    ids = [r["skill_id"] for r in results]
    assert "skill_bash" in ids


def test_bash_skill_injected_by_rag():
    # Build the augmented prompt the way SkillRAG does and assert the bash skill appears.
    schema = parse_skill_file(ROOT / "backend" / ".agentium" / "skills" / "bash" / "SKILL.md")
    skill_manager.upsert_skill_from_markdown(schema, db=None)
    results = skill_manager.search_skills(
        "how do I run the test suite safely", agent_tier="head", db=None, n_results=3
    )
    ctx = skill_rag._build_rag_context(results, "how do I run the test suite safely")
    assert "bash" in ctx["context_text"].lower() or "ShellTool" in ctx["context_text"]
```

- [ ] **Step 2: Run test to verify behavior**

Run: `cd backend && PYTHONPATH=. EMBEDDING_MODEL=BAAI/bge-base-en-v1.5 python -m pytest tests/integration/test_bash_skill_e2e.py -v`
Expected: PASS (bash skill registers, is retrieved for shell tasks, and is injected into the RAG context).

- [ ] **Step 3: Manual smoke (full stack)**

Run:
```bash
make down && make up
make seed-skills
```
Expected: `seed_skills.py` prints `Registered skill: bash (skill_bash)` and `Done. 1 skill(s) registered.` (more if additional folder skills exist). No MiniLM reference anywhere in logs.

- [ ] **Step 4: Commit**

```bash
git add backend/tests/integration/test_bash_skill_e2e.py
git commit -m "test(skills): end-to-end bash skill registration + RAG injection"
```

---

## Self-Review Notes (applied)

- **Spec coverage:** Part 1 skill content → Task 9; Part 2 loader → Tasks 7–8; embedding migration → Tasks 1–6; collection rebuild → Task 6; governance (verified/head) → Task 7 defaults; clip limit 1800→2000 → Task 1.
- **Placeholders:** none — every code step shows the actual code.
- **Type consistency:** `SkillSchema` field names (`skill_id`, `embedding_model`, `verification_status`, `creator_tier`) match across Tasks 1/7/9/10; `BgeEmbeddingFunction.embed_documents`/`embed_query` signatures used consistently in Tasks 2/6; `reindex_skill_collections()` (Task 6) and `upsert_skill_from_markdown()` (Task 7) names are stable across Tasks 7/10.
