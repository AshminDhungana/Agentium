import pytest
from backend.core.chunking import chunk_text


def test_short_text_returns_single_chunk():
    assert chunk_text("hello world", chunk_size=1500) == ["hello world"]


def test_empty_text_returns_empty_list():
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_long_text_splits_into_multiple_chunks():
    text = "\n\n".join(f"Paragraph {i}. " + ("word " * 60) for i in range(20))
    chunks = chunk_text(text, chunk_size=500, overlap=50)
    assert len(chunks) > 1
    assert all(len(c) <= 500 for c in chunks)
    assert all(c.strip() for c in chunks)


def test_chunks_overlap():
    text = ("A" * 300) + " " + ("B" * 300) + " " + ("C" * 300)
    chunks = chunk_text(text, chunk_size=400, overlap=100)
    assert len(chunks) >= 2
    assert chunks[0][-50:] in chunks[1] or chunks[1][:50] in chunks[0]


def test_oversized_single_token_is_hard_split():
    text = "X" * 5000  # no separators at all
    chunks = chunk_text(text, chunk_size=1000, overlap=100)
    assert len(chunks) >= 5
    assert all(len(c) <= 1000 for c in chunks)


def test_invalid_params_raise():
    with pytest.raises(ValueError):
        chunk_text("abc", chunk_size=100, overlap=100)
