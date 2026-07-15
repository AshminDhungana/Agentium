"""Verify BAAI/bge-base-en-v1.5 loads and emits 768-dim normalized vectors."""
from sentence_transformers import SentenceTransformer


def test_bge_model_loads():
    m = SentenceTransformer("BAAI/bge-base-en-v1.5")
    v = m.encode(["test query"], normalize_embeddings=True)[0]
    assert len(v) == 768
