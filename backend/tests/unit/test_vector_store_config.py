from backend.core import config as config_mod
from backend.core.vector_store import AgentiumEmbeddingFunction

def test_embedding_fn_uses_config_model(monkeypatch):
    monkeypatch.setattr(config_mod.settings, "EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
    fn = AgentiumEmbeddingFunction()  # no explicit model_name
    assert fn.model_name == "BAAI/bge-base-en-v1.5"
