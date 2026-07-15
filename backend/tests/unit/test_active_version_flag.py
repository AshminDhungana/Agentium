from backend.core import config as cm
from backend.core.vector_store import VectorStore


def test_active_version_flag_is_per_collection(monkeypatch):
    monkeypatch.setattr(cm.settings, "EMBEDDING_ACTIVE_VERSIONS", {"ethos": "v2"})
    vs = VectorStore()
    assert vs._collection_name("ethos") == "agent_ethos_v2"
    # other collections unaffected by the per-collection override
    assert vs._collection_name("constitution") == "supreme_law"
    assert vs._collection_name("task_patterns") == "execution_patterns"


def test_global_active_version_default(monkeypatch):
    monkeypatch.setattr(cm.settings, "EMBEDDING_ACTIVE_VERSIONS", {})
    monkeypatch.setattr(cm.settings, "EMBEDDING_ACTIVE_VERSION", "v2")
    vs = VectorStore()
    assert vs._collection_name("ethos") == "agent_ethos_v2"
