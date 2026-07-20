import asyncio
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

class FakeStore:
    def __init__(self):
        self.docs = {}  # (collection_key, parent_id) -> (text, metadata)
    def get_collection(self, key):
        return self
    def query_knowledge(self, query, collection_keys=None, n_results=5, filter_dict=None, db=None):
        # Realistic behavior: if a relevant doc is present in the store, return
        # it as a very-close (sufficient) match; otherwise return empty results.
        if self.docs:
            first_key = next(iter(self.docs))
            text, meta = self.docs[first_key]
            return {
                "ids": [[first_key[1]]],
                "documents": [[text]],
                "metadatas": [[meta]],
                "distances": [[0.1]],
            }
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
    for key in ("source_url", "title", "agent_id", "document_type", "decay_score", "citation_boost"):
        assert key in saved_meta, f"missing schema key {key}"


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
    from backend.services.knowledge_assist import _parent_id_for_query
    assert ("web_knowledge", _parent_id_for_query("novel query here")) in store.docs
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
