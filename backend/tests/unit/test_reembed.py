from backend.core.vector_store import VectorStore, CHROMA_PERSIST_DIR
from backend.scripts.reembed_knowledge import backfill_collection


def test_backfill_preserves_metadata(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "backend.core.vector_store.CHROMA_PERSIST_DIR", str(tmp_path)
    )
    vs = VectorStore()
    monkeypatch.setattr("backend.core.vector_store.get_vector_store", lambda: vs)

    v1 = vs.get_collection("ethos", version="v1")
    v1.upsert(
        ids=["e1", "e2"],
        documents=["doc a", "doc b"],
        metadatas=[
            {"agent_id": "x", "decay_score": 0.9},
            {"knowledge_type": "ethos", "citation_boost": 1.1},
        ],
    )

    stats = backfill_collection("ethos", dry_run=False)
    assert stats["v1_count"] == 2
    assert stats["v2_count"] == 2
    assert stats["metadata_mismatch"] == 0

    v2 = vs.get_collection("ethos", version="v2")
    got = v2.get(ids=["e1"], include=["metadatas"])["metadatas"][0]
    assert got["agent_id"] == "x"
    assert float(got["decay_score"]) == 0.9
