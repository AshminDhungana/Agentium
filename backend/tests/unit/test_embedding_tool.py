"""
Quick smoke tests for embedding_tool.
"""
import pytest


def test_embedding_tool_embed():
    from backend.tools.embedding_tool import embedding_tool

    result = asyncio_run(embedding_tool.execute(
        action="embed",
        texts=["hello world", "test text"],
        provider="local"
    ))
    assert result["success"] is True
    assert "embeddings" in result
    assert len(result["embeddings"]) == 2
    assert len(result["embeddings"][0]) > 0


def test_embedding_tool_similarity():
    from backend.tools.embedding_tool import embedding_tool

    result = asyncio_run(embedding_tool.execute(
        action="similarity",
        text_a="hello world",
        text_b="hello there",
        provider="local"
    ))
    assert result["success"] is True
    assert "similarity" in result
    assert 0 <= result["similarity"] <= 1


def test_embedding_tool_search():
    from backend.tools.embedding_tool import embedding_tool

    result = asyncio_run(embedding_tool.execute(
        action="search",
        query="test query",
        candidates=["candidate one", "candidate two", "candidate three"],
        provider="local",
        top_k=2
    ))
    assert result["success"] is True
    assert "results" in result
    assert len(result["results"]) <= 2


def test_embedding_tool_cluster():
    from backend.tools.embedding_tool import embedding_tool

    result = asyncio_run(embedding_tool.execute(
        action="cluster",
        texts=["text one", "text two", "text three", "text four"],
        provider="local",
        n_clusters=2
    ))
    assert result["success"] is True
    assert "clusters" in result
    assert len(result["clusters"]) == 2


def test_embedding_tool_missing_action():
    from backend.tools.embedding_tool import embedding_tool

    result = asyncio_run(embedding_tool.execute(
        action="embed",
        texts=["test"]
    ))
    assert result["success"] is True


def test_embedding_tool_invalid_action():
    from backend.tools.embedding_tool import embedding_tool

    result = asyncio_run(embedding_tool.execute(
        action="invalid",
        texts=["test"]
    ))
    assert result["success"] is False


def asyncio_run(coro):
    import asyncio
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)