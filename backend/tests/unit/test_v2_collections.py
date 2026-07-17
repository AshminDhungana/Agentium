from backend.core.vector_store import VectorStore


def test_v2_collection_is_default_and_cosine():
    vs = VectorStore()
    # v1 was retired; both explicit v2 and the default resolve to the v2 name.
    v2 = vs.get_collection("task_patterns", version="v2")
    default = vs.get_collection("task_patterns")
    assert v2.name == "execution_patterns_v2"
    assert default.name == "execution_patterns_v2"
    # A "v1" request is accepted for compatibility but resolves to v2.
    legacy = vs.get_collection("task_patterns", version="v1")
    assert legacy.name == "execution_patterns_v2"

    v2.upsert(documents=["new"], ids=["e2"], metadatas=[{"t": 1}])
    assert v2.get(ids=["e2"])["documents"][0] == "new"


def test_v2_collection_uses_cosine_space():
    vs = VectorStore()
    v2 = vs.get_collection("task_patterns", version="v2")
    meta = getattr(v2, "metadata", None) or {}
    conf = getattr(v2, "configuration", None) or {}
    space = meta.get("hnsw:space") or (conf.get("hnsw", {}) or {}).get("space")
    assert space == "cosine"
