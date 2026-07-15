"""Task 20 — rehearse rollback to v1 via the per-collection feature flag.

Uses a local persistent ChromaDB (no docker/postgres needed) to confirm the
EMBEDDING_ACTIVE_VERSIONS flag flips the resolved collection name and that
queries keep working after flipping forward to v2, back to v1, then forward
again.
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
    col = vs.get_collection("ethos", version=version)
    col.upsert(
        documents=["The agent must protect sovereign data."],
        ids=["ethos_seed_1"],
        metadatas=[{"title": "ethos seed"}],
    )
    res = col.query(query_texts=["protect sovereign data"], n_results=1)
    return res["ids"][0] if res.get("ids") else []


def test_rollback_to_v1_then_forward(vs, monkeypatch):
    # Forward to v2.
    monkeypatch.setattr(_settings, "EMBEDDING_ACTIVE_VERSIONS", {"ethos": "v2"})
    assert vs._collection_name("ethos") == "agent_ethos_v2"
    v2_hits = _seed_and_query(vs, "v2")
    assert v2_hits, "v2 query must return results after cutover"

    # Roll back to v1.
    monkeypatch.setattr(_settings, "EMBEDDING_ACTIVE_VERSIONS", {"ethos": "v1"})
    assert vs._collection_name("ethos") == "agent_ethos"
    v1_hits = _seed_and_query(vs, "v1")
    assert v1_hits, "v1 query must still work after rollback"

    # Flip forward to v2 again.
    monkeypatch.setattr(_settings, "EMBEDDING_ACTIVE_VERSIONS", {"ethos": "v2"})
    assert vs._collection_name("ethos") == "agent_ethos_v2"
    v2_again = _seed_and_query(vs, "v2")
    assert v2_again, "v2 query must work again after re-cutover"
