import pytest
from backend.core.vector_store import VectorStore


class FakeColl:
    def __init__(self, rows):
        self.rows = rows  # list of (id, doc, meta, dist)

    def query(self, query_texts, n_results=5, where=None):
        r = self.rows
        return {"ids": [[x[0] for x in r]],
                "documents": [[x[1] for x in r]],
                "metadatas": [[x[2] for x in r]],
                "distances": [[x[3] for x in r]]}


@pytest.fixture
def vs(monkeypatch):
    store = VectorStore()
    coll = FakeColl([
        ("p1#chunk0", "chunk zero text", {"parent_id": "p1", "is_chunk": True}, 0.10),
        ("p1#chunk1", "chunk one text", {"parent_id": "p1", "is_chunk": True}, 0.40),
        ("p2#chunk0", "other doc chunk", {"parent_id": "p2", "is_chunk": True}, 0.20),
    ])
    monkeypatch.setattr(store, "get_collection", lambda key, version=None: coll)
    parents = {
        ("task_patterns", "p1"): {"parent_id": "p1", "full_text": "FULL DOC ONE (long)", "metadata": {"t": 1}, "chunk_count": 2},
        ("task_patterns", "p2"): {"parent_id": "p2", "full_text": "FULL DOC TWO", "metadata": {"t": 2}, "chunk_count": 1},
    }
    monkeypatch.setattr(store, "get_parent_document",
                        lambda ck, pid, db=None: parents.get((ck, pid)))
    return store


def test_query_dedups_by_parent_and_returns_full_text(vs):
    res = vs.query_knowledge("anything", collection_keys=["task_patterns"], n_results=5, db=object())
    ids = res["ids"][0]
    docs = res["documents"][0]
    assert ids == ["p1", "p2"]
    assert docs[0] == "FULL DOC ONE (long)"
    assert docs[1] == "FULL DOC TWO"


def test_query_falls_back_to_chunk_when_parent_missing(vs, monkeypatch):
    monkeypatch.setattr(vs, "get_parent_document", lambda ck, pid, db=None: None)
    res = vs.query_knowledge("anything", collection_keys=["task_patterns"], n_results=5, db=object())
    assert res["documents"][0][0] == "chunk zero text"


def test_query_respects_n_results(vs):
    res = vs.query_knowledge("anything", collection_keys=["task_patterns"], n_results=1, db=object())
    assert len(res["ids"][0]) == 1
    assert res["ids"][0] == ["p1"]
