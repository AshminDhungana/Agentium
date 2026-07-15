from unittest.mock import patch, MagicMock

from backend.core.vector_store import BgeEmbeddingFunction

PREFIX = "Represent this sentence for searching relevant passages: "


def _fake_encode():
    arr = MagicMock()
    arr.tolist.return_value = [[0.1] * 768]
    return arr


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
