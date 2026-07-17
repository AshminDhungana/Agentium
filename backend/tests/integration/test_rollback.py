"""Rollback / version-resolution test for the embedding collection.

v1 (MiniLM) was retired, so there is no v1 to roll back to. This test asserts
the collection always resolves to the v2 (bge, cosine) name and that queries
keep returning results — both for the default and an explicitly requested
"v1" (which must resolve to v2 for backwards compatibility).
"""
import os

os.environ["TESTING"] = "true"

import pytest

from backend.core.vector_store import VectorStore
from backend.core.config import settings as _settings


@pytest.fixture
def vs(tmp_path, monkeypatch):
    monkeypatch.setattr("backend.core.vector_store.CHROMA_HOST", None)
    monkeypatch.setattr("backend.core.vector_store.CHROMA_PERSIST_DIR", str(tmp_path))
    store = VectorStore()
    store.initialize()
    return store


def _seed_and_query(vs, version):
    col = vs.get_collection("task_patterns", version=version)
    col.upsert(
        documents=["The agent must protect sovereign data."],
        ids=["pattern_seed_1"],
        metadatas=[{"title": "pattern seed"}],
    )
    res = col.query(query_texts=["protect sovereign data"], n_results=1)
    return res["ids"][0] if res.get("ids") else []


def test_collection_resolves_to_v2_and_queries_work(vs, monkeypatch):
    # Default resolution is v2.
    monkeypatch.setattr(_settings, "EMBEDDING_ACTIVE_VERSIONS", {"task_patterns": "v2"})
    assert vs._collection_name("task_patterns") == "execution_patterns_v2"
    v2_hits = _seed_and_query(vs, "v2")
    assert v2_hits, "v2 query must return results"

    # A legacy "v1" request must resolve to the same v2 collection (no v1 path).
    monkeypatch.setattr(_settings, "EMBEDDING_ACTIVE_VERSIONS", {"task_patterns": "v1"})
    assert vs._collection_name("task_patterns") == "execution_patterns_v2"
    legacy_hits = _seed_and_query(vs, "v1")
    assert legacy_hits, "v1 request resolves to v2 and must still query"
