from backend.core.vector_store import VectorStore


def test_v2_collection_side_by_side():
    vs = VectorStore()
    v1 = vs.get_collection("ethos", version="v1")
    v2 = vs.get_collection("ethos", version="v2")
    assert v1.name == "agent_ethos"
    assert v2.name == "agent_ethos_v2"
    v1.upsert(documents=["old"], ids=["e1"], metadatas=[{"t": 1}])
    v2.upsert(documents=["new"], ids=["e2"], metadatas=[{"t": 1}])
    assert v1.get(ids=["e1"])["documents"][0] == "old"
    assert v2.get(ids=["e2"])["documents"][0] == "new"


def test_v2_collection_uses_cosine_space():
    vs = VectorStore()
    v2 = vs.get_collection("ethos", version="v2")
    meta = getattr(v2, "metadata", None) or {}
    conf = getattr(v2, "configuration", None) or {}
    space = meta.get("hnsw:space") or (conf.get("hnsw", {}) or {}).get("space")
    assert space == "cosine"
