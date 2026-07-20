from backend.core.vector_store import VectorStore


def test_web_knowledge_collection_registered():
    assert "web_knowledge" in VectorStore.COLLECTIONS
    store = VectorStore()
    # get_collection must resolve without raising
    coll = store.get_collection("web_knowledge")
    assert coll is not None
