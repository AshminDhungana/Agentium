import asyncio
from typing import Any, Dict, List, Optional


class FakeStore:
    def __init__(self):
        self.docs = {}
        self.queries = []
    def get_collection(self, key):
        return self
    def query_knowledge(self, query, collection_keys=None, n_results=5, filter_dict=None, db=None):
        self.queries.append(query)
        return {"ids": [[]], "documents": [[]], "metadatas": [[]], "distances": [[]]}
    def get_parent_document(self, collection_key, parent_id, db):
        return None
    def upsert_document(self, collection_key, parent_id, text, metadata, db):
        self.docs[(collection_key, parent_id)] = (text, dict(metadata))
        return {"parent_id": parent_id}


def test_checkpoint_write_web_success_writes_back(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "T1", "url": "http://a", "snippet": "snip A"},
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_x"
        description = "explain noveltopicium"
    class FakeAgent:
        agentium_id = "30001"

    out = asyncio.run(ka.checkpoint_write("received", FakeTask(), FakeAgent(), db=None))
    assert out.stage == "received"
    assert out.queried_chroma is True
    assert out.searched_web is True
    assert out.wrote_back is True
    assert out.fallback_used is False
    assert out.parent_id is not None
    # a web_knowledge doc with the 6.6 schema got written
    (text, meta), = [v for k, v in store.docs.items() if k[0] == "web_knowledge"]
    assert meta["stage"] == "received"
    assert meta["task_id"] == "task_x"
    assert meta["type"] == "agent_learning"
    assert meta["source"] == "agent"
    assert meta["revision_id"]
    assert meta["parent_id"]


def test_checkpoint_write_web_failure_falls_back(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "error", "error": "all providers failed"}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_y"
        description = "explain othertopic"
    class FakeAgent:
        agentium_id = "30001"

    # must NOT raise; empty Chroma + web failure still records a marker checkpoint
    out = asyncio.run(ka.checkpoint_write("completed", FakeTask(), FakeAgent(), db=None))
    assert out.searched_web is True
    assert out.fallback_used is True
    assert out.wrote_back is True  # empty-marker checkpoint recorded for traceability


def test_checkpoint_write_mid_uses_provided_query(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    captured = {}
    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            captured["query"] = query
            return {"status": "success", "query": query, "results": [
                {"index": 0, "title": "T", "url": "http://b", "snippet": "s"}
            ]}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_z"
        description = "original description"
    class FakeAgent:
        agentium_id = "30001"

    out = asyncio.run(ka.checkpoint_write("mid", FakeTask(), FakeAgent(), db=None,
                                           query="the specific gap query"))
    assert captured["query"] == "the specific gap query"
    assert out.stage == "mid"


def test_checkpoint_write_rejects_unknown_stage():
    from backend.services import knowledge_assist as ka
    class FakeTask:
        agentium_id = "t"
        description = "d"
    class FakeAgent:
        agentium_id = "30001"
    try:
        asyncio.run(ka.checkpoint_write("bogus", FakeTask(), FakeAgent(), db=None))
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_checkpoint_write_records_marker_when_both_empty(monkeypatch):
    from backend.services import knowledge_assist as ka
    store = FakeStore()
    ka.get_vector_store = lambda: store

    class FakeWeb:
        async def execute(self, query, provider="auto", max_results=5):
            return {"status": "error", "error": "all providers failed"}
    ka.web_search_tool = FakeWeb()

    class FakeTask:
        agentium_id = "task_empty"
        description = "a query with no knowledge anywhere"
    class FakeAgent:
        agentium_id = "30001"

    out = asyncio.run(ka.checkpoint_write("received", FakeTask(), FakeAgent(), db=None))
    # Chroma empty + web failed -> still records the checkpoint (traceability)
    assert out.wrote_back is True
    assert out.fallback_used is True
    (text, meta), = [v for k, v in store.docs.items() if k[0] == "web_knowledge"]
    assert meta["empty"] is True
    assert meta["stage"] == "received"
