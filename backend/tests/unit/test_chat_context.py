"""
Unit tests for the token-efficient chat context builder (Task 2.1).

These tests mock the DB session so they run without Postgres/Redis.
"""

import sys
import types
from unittest.mock import MagicMock

import pytest


class _FakeMsg:
    def __init__(self, role, content, is_deleted="N"):
        self.role = role
        self.content = content
        self.is_deleted = is_deleted


def _make_session(rows):
    """Build a mock SQLAlchemy session whose .query(...).all() returns rows."""
    q = MagicMock()
    q.filter.return_value = q
    q.order_by.return_value = q
    q.limit.return_value = q
    q.all.return_value = rows
    session = MagicMock()
    session.query.return_value = q
    return session


@pytest.fixture
def builder():
    from backend.services.chat_context import ChatContextBuilder

    return ChatContextBuilder(window_size=10)


def test_estimate_tokens_positive():
    from backend.services.chat_context import estimate_tokens

    n = estimate_tokens(
        [{"role": "user", "content": "hello world"}, {"role": "assistant", "content": "hi"}],
        system_prompt="You are helpful.",
    )
    assert isinstance(n, int) and n > 0


def test_short_history_not_compressed(builder):
    rows = [_FakeMsg("sovereign", f"m{i}") for i in range(5)]
    rows += [_FakeMsg("head_of_council", f"a{i}") for i in range(5)]
    db = _make_session(rows)

    out = builder.build(db, "u1")
    assert out["context_compressed"] is False
    # 10 turns total, window 10 -> all kept, no separate pin
    assert len(out["history"]) == 10
    assert out["raw_turn_count"] == 10


def test_long_history_pins_first_and_windows(builder):
    # 30 sovereign + 30 head turns => 60 total. Window 10.
    rows = [_FakeMsg("sovereign", f"s{i}") for i in range(30)]
    rows += [_FakeMsg("head_of_council", f"h{i}") for i in range(30)]
    db = _make_session(rows)

    out = builder.build(db, "u1")
    assert out["context_compressed"] is True
    assert out["raw_turn_count"] == 60
    # history = [pinned first] + last 10 turns (no current msg appended yet)
    assert len(out["history"]) == 11
    # First message pinned at head.
    assert out["history"][0]["content"] == "s0"
    # Most recent turn present.
    assert out["history"][-1]["content"] == "h29"


def test_first_message_not_duplicated_when_in_window(builder):
    rows = [_FakeMsg("sovereign", "first")] + [
        _FakeMsg("head_of_council", f"h{i}") for i in range(5)
    ]
    db = _make_session(rows)

    out = builder.build(db, "u1")
    # Window (10) covers everything; first message appears exactly once.
    assert sum(1 for m in out["history"] if m["content"] == "first") == 1
    assert out["context_compressed"] is False


def test_summary_flag_marks_compression(builder):
    rows = [_FakeMsg("sovereign", "only one")]
    db = _make_session(rows)
    out = builder.build(db, "u1", summary='{"key_facts":["x"]}')
    assert out["context_compressed"] is True


def test_format_summary_for_prompt():
    from backend.services.chat_context import format_summary_for_prompt

    text = format_summary_for_prompt(
        '{"key_facts":["a"],"decisions":["b"],"open_threads":["c"]}'
    )
    assert "Key facts" in text and "a" in text
    assert "Decisions" in text and "b" in text


def test_full_history_tool_returns_chronological():
    from backend.services.chat_context import (
        get_full_history,
        set_chat_request,
        clear_chat_request,
    )

    rows = [_FakeMsg("sovereign", "q1"), _FakeMsg("head_of_council", "a1")]
    db = _make_session(rows)
    set_chat_request(user_id="u1", db=db)
    try:
        res = get_full_history(limit=50)
    finally:
        clear_chat_request()
    assert res["status"] == "ok"
    # Both turns are recovered (chronological order is DB-driven; the mock
    # cannot sort by created_at, so assert membership rather than position).
    contents = [m["content"] for m in res["history"]]
    assert "q1" in contents and "a1" in contents
    roles = {m["role"] for m in res["history"]}
    assert "user" in roles and "assistant" in roles
