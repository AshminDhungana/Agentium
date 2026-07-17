import pytest
from backend.core.vector_store import VectorStore
from backend.scripts.backfill_knowledge_chunks import backfill_collection


class FakeColl:
    def __init__(self, rows=None):
        # rows: dict doc_id -> (doc, meta)
        self.data = dict(rows or {})
        self.deleted = []

    def get(self, include=None, limit=None, offset=None):
        ids = list(self.data.keys())
        return {
            "ids": ids,
            "documents": [self.data[i][0] for i in ids],
            "metadatas": [self.data[i][1] for i in ids],
        }

    def upsert(self, ids, documents, metadatas, embeddings=None):
        for i, _id in enumerate(ids):
            self.data[_id] = (documents[i], metadatas[i])

    def delete(self, ids=None, where=None):
        for i in (ids or []):
            self.data.pop(i, None)
            self.deleted.append(i)


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
                return outer.rows.get((self._f.get("collection_key"), self._f.get("parent_id")))

        return Q()

    def add(self, obj):
        self.rows[(obj.collection_key, obj.parent_id)] = obj

    def commit(self):
        pass


@pytest.fixture
def vs(monkeypatch):
    store = VectorStore()
    monkeypatch.setattr(store, "_v2_embedding_fn", _EF())
    return store


def test_backfill_migrates_legacy_doc_and_serves_full_text(vs, monkeypatch):
    long_text = "\n\n".join(f"Para {i} " + "w " * 200 for i in range(10))
    coll = FakeColl({"legacy_1": (long_text, {"type": "execution_pattern"})})
    monkeypatch.setattr(vs, "get_collection", lambda key, version=None: coll)
    db = FakeSession()

    n = backfill_collection(vs, db, "task_patterns")

    assert n == 1
    # Parent store now holds the untruncated text.
    parent = vs.get_parent_document("task_patterns", "legacy_1", db)
    assert parent is not None
    assert parent["full_text"] == long_text
    # Chunk vectors were created.
    assert any(k.startswith("legacy_1#chunk") for k in coll.data)
    # Redundant legacy standalone vector removed.
    assert "legacy_1" in coll.deleted


def test_backfill_skips_chunk_docs(vs, monkeypatch):
    coll = FakeColl({
        "p1#chunk0": ("chunk text", {"parent_id": "p1", "is_chunk": True}),
    })
    monkeypatch.setattr(vs, "get_collection", lambda key, version=None: coll)
    db = FakeSession()

    n = backfill_collection(vs, db, "task_patterns")
    assert n == 0
    # Nothing new migrated; chunk left untouched.
    assert coll.data == {"p1#chunk0": ("chunk text", {"parent_id": "p1", "is_chunk": True})}
