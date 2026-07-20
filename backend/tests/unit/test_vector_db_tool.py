"""
Unit tests for the vector_db tool (read + write actions).

Run inside the backend container (chromadb + sentence-transformers present):
    docker compose exec -T backend bash -lc \
        "cd /app/backend && pytest tests/unit/test_vector_db_tool.py -o addopts='' -q"
"""
import pytest

from backend.tools.vector_db_tool import VectorDBTool


@pytest.fixture
def store():
    return VectorDBTool()


async def test_execute_routes_unknown_action(store):
    result = await store.execute(action="frobnicate")
    assert result["success"] is False
    assert "Unknown action" in result["error"]


async def test_help_points_to_skill_file(store):
    result = await store.execute(action="help")
    assert result["success"] is True
    assert "SKILL.md" in result["help"]
    assert ".agentium/skills/vector_db" in result["help"]
    assert "seed-skills" in result["help"]


async def test_list_collections_returns_known_keys(store):
    result = await store.execute(action="list_collections")
    assert result["success"] is True
    keys = result["collections"]
    for k in ("constitution", "council_memory", "task_patterns"):
        assert k in keys
    assert any(".agentium/skills/vector_db" in p for p in result["paths"].values())


async def test_query_requires_query_arg(store):
    result = await store.execute(action="query")
    assert result["success"] is False
    assert "query" in result["error"]


async def test_query_against_test_store(store, monkeypatch):
    class FakeCollection:
        def query(self, query_texts, n_results=5, where=None):
            return {
                "ids": [["doc_1"]],
                "documents": [["Storing execution patterns in ChromaDB."]],
                "metadatas": [[{"type": "execution_pattern"}]],
                "distances": [[0.12]],
            }

    class FakeStore:
        COLLECTIONS = {"task_patterns": "execution_patterns"}

        def get_collection(self, key, version=None):
            return FakeCollection()

        def query_knowledge(self, query, collection_keys=None, n_results=5, filter_dict=None):
            return {
                "ids": [["doc_1"]],
                "documents": [["Storing execution patterns in ChromaDB."]],
                "metadatas": [[{"type": "execution_pattern"}]],
                "distances": [[0.12]],
            }

    monkeypatch.setattr(
        "backend.tools.vector_db_tool.get_vector_store", lambda: FakeStore()
    )
    result = await store.execute(action="query", query="how do I store learnings?", n_results=3)
    assert result["success"] is True
    assert result["count"] == 1
    match = result["matches"][0]
    assert match["id"] == "doc_1"
    assert match["relevance_score"] == pytest.approx(0.88, abs=1e-6)
    assert match["document"] == "Storing execution patterns in ChromaDB."
    assert match["metadata"]["type"] == "execution_pattern"


def test_web_knowledge_is_writable():
    from backend.tools.vector_db_tool import VectorDBTool
    assert "web_knowledge" in VectorDBTool.WRITABLE_COLLECTIONS


# ── Write actions (Task 2) ────────────────────────────────────────────────────

async def test_add_requires_collection_and_documents(store):
    result = await store.execute(action="add")
    assert result["success"] is False
    assert "collection" in result["error"] or "documents" in result["error"]


async def test_add_rejects_protected_collection(store):
    result = await store.execute(
        action="add",
        collection="constitution",
        documents=["Attempt to tamper with the supreme law."],
        ids=["const_evil_1"],
    )
    assert result["success"] is False
    assert "not writable" in result["error"]


async def test_add_rejects_unknown_collection(store):
    result = await store.execute(
        action="add",
        collection="does_not_exist",
        documents=["x"],
        ids=["x1"],
    )
    assert result["success"] is False
    assert "Unknown collection" in result["error"]


async def test_add_writes_to_writable_collection(store, monkeypatch):
    captured = {}

    # Monkeypatch write_knowledge directly so the test is deterministic and
    # independent of the real Chroma client / get_vector_store singleton
    # (which other test modules perturb). This verifies `_add` routes agent
    # writes through the 6.6 schema funnel with the correct collection key.
    import backend.services.knowledge_assist as ka

    async def fake_write_knowledge(parent_id, text, metadata, db, collection_key="web_knowledge"):
        captured["collection_key"] = collection_key
        captured["parent_id"] = parent_id
        captured["metadata"] = metadata
        return {"parent_id": parent_id}

    monkeypatch.setattr(ka, "write_knowledge", fake_write_knowledge)
    monkeypatch.setattr(
        "backend.tools.vector_db_tool.VectorDBTool.WRITABLE_COLLECTIONS",
        ["task_patterns"],
    )
    result = await store.execute(
        action="add",
        collection="task_patterns",
        documents=["Use Docker sandbox for untrusted code."],
        metadatas=[{"type": "execution_pattern", "task_type": "code"}],
        ids=["pattern_docker_1"],
    )
    assert result["success"] is True
    assert result["collection"] == "task_patterns"
    assert result["count"] == 1
    assert result["ids"] == ["pattern_docker_1"]
    assert captured["collection_key"] == "task_patterns"
    assert captured["parent_id"] == "pattern_docker_1"
    assert "revision_id" in captured["metadata"]
