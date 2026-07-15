from backend.core.vector_store import BgeEmbeddingFunction

PREFIX = "Represent this sentence for searching relevant passages: "


def test_query_path_prefixed():
    fn = BgeEmbeddingFunction()
    assert fn._with_prefix("how do I spawn an agent").startswith(PREFIX)


def test_document_path_not_prefixed():
    fn = BgeEmbeddingFunction()
    assert not fn._with_prefix("stored passage text").startswith(PREFIX)
