from unittest.mock import patch, MagicMock

import numpy as np

from backend.core.vector_store import BgeEmbeddingFunction

PREFIX = "Represent this sentence for searching relevant passages: "


def _fake_encode():
    return np.array([[0.1] * 768])


def test_query_path_prefixed():
    fn = BgeEmbeddingFunction()
    assert fn._with_prefix("how do I spawn an agent").startswith(PREFIX)


def test_document_path_not_prefixed():
    fake = MagicMock()
    fake.encode.return_value = _fake_encode()
    with patch("backend.core.vector_store.SentenceTransformer", return_value=fake):
        fn = BgeEmbeddingFunction()
        fn.embed_documents(["stored passage text"])
        called_text = fake.encode.call_args[0][0]
        assert called_text == ["stored passage text"]  # no prefix on documents
        assert fake.encode.call_args.kwargs.get("normalize_embeddings") is True


def test_query_path_encodes_prefixed():
    fake = MagicMock()
    fake.encode.return_value = _fake_encode()
    with patch("backend.core.vector_store.SentenceTransformer", return_value=fake):
        fn = BgeEmbeddingFunction()
        fn.embed_query("how do I spawn")
        called_text = fake.encode.call_args[0][0]
        assert called_text[0].startswith(PREFIX)
        assert fake.encode.call_args.kwargs.get("normalize_embeddings") is True


def test_embed_query_accepts_list_like_chromadb():
    # ChromaDB 1.5.1 calls embed_query with a list of query texts.
    fake = MagicMock()

    def _multi(texts, **kwargs):
        return np.array([[0.1] * 768 for _ in texts])

    fake.encode.side_effect = _multi
    with patch("backend.core.vector_store.SentenceTransformer", return_value=fake):
        fn = BgeEmbeddingFunction()
        out = fn.embed_query(["q1", "q2"])
        assert isinstance(out, list) and len(out) == 2
        called = fake.encode.call_args[0][0]
        assert called[0].startswith(PREFIX) and called[1].startswith(PREFIX)
