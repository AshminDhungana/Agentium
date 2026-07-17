import pytest
from backend.core.vector_store import VectorStore


class FakeColl:
    def __init__(self):
        self.data = {}

    def upsert(self, ids, documents, metadatas, embeddings=None):
        for i, _id in enumerate(ids):
            self.data[_id] = (documents[i], metadatas[i])

    def get(self, ids=None, where=None, include=None):
        if ids:
            present = [i for i in ids if i in self.data]
            return {"ids": present,
                    "documents": [self.data[i][0] for i in present],
                    "metadatas": [self.data[i][1] for i in present]}
        items = list(self.data.items())
        if where and "parent_id" in where:
            pid = where["parent_id"]
            items = [(k, v) for k, v in items if v[1].get("parent_id") == pid]
        return {"ids": [k for k, _ in items],
                "documents": [v[0] for _, v in items],
                "metadatas": [v[1] for _, v in items]}

    def delete(self, ids=None, where=None):
        if ids:
            for i in ids:
                self.data.pop(i, None)
        elif where and "parent_id" in where:
            pid = where["parent_id"]
            for k in [k for k, v in self.data.items() if v[1].get("parent_id") == pid]:
                self.data.pop(k, None)


class _EF:
    def embed_documents(self, docs):
        return [[0.1, 0.2, 0.3] for _ in docs]


class FakeSession:
    def __init__(self):
        self.rows = {}

    def query(self, model):
        outer = self

        class Q:
            def __init__(self):
                self._f = {}

            def filter_by(self, **kw):
                self._f = kw
                return self

            def first(self):
                key = (self._f.get("collection_key"), self._f.get("parent_id"))
                return outer.rows.get(key)

        return Q()

    def add(self, obj):
        self.rows[(obj.collection_key, obj.parent_id)] = obj

    def commit(self):
        pass


@pytest.fixture
def vs(monkeypatch):
    store = VectorStore()
    coll = FakeColl()
    monkeypatch.setattr(store, "get_collection", lambda key, version=None: coll)
    monkeypatch.setattr(store, "_v2_embedding_fn", _EF())
    return store, coll


def test_upsert_short_doc_single_chunk(vs):
    store, coll = vs
    db = FakeSession()
    res = store.upsert_document("task_patterns", "pattern_1", "short text", {"type": "x"}, db)
    assert res["chunk_count"] == 1
    assert "pattern_1#chunk0" in coll.data
    assert coll.data["pattern_1#chunk0"][1]["is_chunk"] is True
    assert coll.data["pattern_1#chunk0"][1]["parent_id"] == "pattern_1"


def test_upsert_long_doc_multiple_chunks(vs):
    store, coll = vs
    db = FakeSession()
    long_text = "\n\n".join(f"Para {i} " + "w " * 200 for i in range(10))
    res = store.upsert_document("task_patterns", "pattern_2", long_text, {}, db)
    assert res["chunk_count"] > 1
    chunk_ids = [k for k in coll.data if k.startswith("pattern_2#chunk")]
    assert len(chunk_ids) == res["chunk_count"]


def test_upsert_replaces_stale_chunks(vs):
    store, coll = vs
    db = FakeSession()
    long_text = "\n\n".join(f"Para {i} " + "w " * 200 for i in range(10))
    store.upsert_document("task_patterns", "pattern_2", long_text, {}, db)
    first_count = len([k for k in coll.data if k.startswith("pattern_2#chunk")])
    assert first_count > 1
    # Re-upsert with short text -> stale chunks removed, single chunk remains
    store.upsert_document("task_patterns", "pattern_2", "now short", {}, db)
    remaining = [k for k in coll.data if k.startswith("pattern_2#chunk")]
    assert remaining == ["pattern_2#chunk0"]


def test_upsert_rejects_empty(vs):
    store, _ = vs
    with pytest.raises(ValueError):
        store.upsert_document("task_patterns", "p", "   ", {}, FakeSession())


def test_get_parent_document(vs):
    store, _ = vs
    db = FakeSession()
    store.upsert_document("task_patterns", "pattern_3", "hello world body", {"k": "v"}, db)
    got = store.get_parent_document("task_patterns", "pattern_3", db)
    assert got["full_text"] == "hello world body"
    assert got["metadata"]["k"] == "v"


def test_get_parent_document_missing_returns_none(vs):
    store, _ = vs
    assert store.get_parent_document("task_patterns", "nope", FakeSession()) is None
