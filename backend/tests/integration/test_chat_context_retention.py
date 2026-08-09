"""
Integration tests for chat context sliding window, pinning, and summary injection.
Verifies Task 2.1 token-efficient chat context behavior.
"""

import pytest
from backend.services.chat_context import (
    ChatContextBuilder,
    estimate_tokens,
    summarize_history,
    load_summary,
    format_summary_for_prompt,
    get_full_history,
    search_chat_history,
    set_chat_request,
    clear_chat_request,
)
from backend.models.entities.chat_message import ChatMessage as ChatMsg
from backend.models.entities.user import User


@pytest.mark.integration
class TestChatContextWindowPinning:
    """Tests for sliding window + pinned first message + summary compression."""

    def test_short_history_no_compression(self, seeded_db):
        """5 turns, window=10: no compression, all turns kept, no pin duplicate."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        # Clean any existing messages
        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Seed 5 sovereign + 5 head turns = 10 total
        for i in range(5):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i}",
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        out = builder.build(db, str(user.id))

        assert out["context_compressed"] is False
        assert len(out["history"]) == 10
        assert out["raw_turn_count"] == 10
        # First message appears exactly once (not duplicated as pin)
        first_count = sum(1 for m in out["history"] if m["content"] == "s0")
        assert first_count == 1

    def test_long_history_pins_first_and_windows(self, seeded_db):
        """60 turns, window=10: compressed, history=11 (pinned first + last 10)."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Seed 30 sovereign + 30 head = 60 total
        for i in range(30):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i}",
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        out = builder.build(db, str(user.id))

        assert out["context_compressed"] is True
        assert out["raw_turn_count"] == 60
        # History = [pinned first] + last 10 turns = 11
        assert len(out["history"]) == 11
        # First message pinned at head
        assert out["history"][0]["content"] == "s0"
        # Most recent turn present (h29 is last seeded)
        assert out["history"][-1]["content"] == "h29"

    def test_first_message_not_duplicated_in_window(self, seeded_db):
        """6 turns (first + 5 recent), window=10: first appears once, no compression."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # First message + 5 recent turns
        db.add(ChatMsg(user_id=str(user.id), role="sovereign", content="first"))
        for i in range(5):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        out = builder.build(db, str(user.id))

        # Window (10) covers everything; first message appears exactly once
        assert sum(1 for m in out["history"] if m["content"] == "first") == 1
        assert out["context_compressed"] is False
        assert len(out["history"]) == 6

    def test_summary_flag_marks_compression(self, seeded_db):
        """Any history + summary provided: context_compressed=True regardless of turn count."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Just 1 turn
        db.add(ChatMsg(user_id=str(user.id), role="sovereign", content="only one"))
        db.commit()

        builder = ChatContextBuilder(window_size=10)
        summary_json = '{"key_facts":["x"]}'
        out = builder.build(db, str(user.id), summary=summary_json)

        assert out["context_compressed"] is True

    def test_window_size_configurable(self, seeded_db):
        """window=5, 20 turns: history=6 (pinned + 5 recent)."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None

        db.query(ChatMsg).filter(ChatMsg.user_id == str(user.id)).delete()
        db.commit()

        # Seed 10 sovereign + 10 head = 20 total
        for i in range(10):
            db.add(ChatMsg(
                user_id=str(user.id),
                role="sovereign",
                content=f"s{i}",
            ))
            db.add(ChatMsg(
                user_id=str(user.id),
                role="head_of_council",
                content=f"h{i}",
            ))
        db.commit()

        builder = ChatContextBuilder(window_size=5)
        out = builder.build(db, str(user.id))

        assert out["context_compressed"] is True
        assert out["raw_turn_count"] == 20
        # History = [pinned first] + last 5 turns = 6
        assert len(out["history"]) == 6
        assert out["history"][0]["content"] == "s0"
        assert out["history"][-1]["content"] == "h9"


import json
from unittest.mock import AsyncMock, patch

from backend.services.model_provider import ModelService


@pytest.mark.integration
class TestChatContextSummarizationRecovery:
    """Tests for background summarization and on-demand full history recovery."""

    async def test_summarize_history_creates_structured_json(self, seeded_db, redis_client):
        """55 turns, trigger summarize: summary_json has key_facts, decisions, open_threads; stored in Redis."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        # Seed 55 turns (alternating)
        for i in range(55):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        # Mock model provider to return valid JSON summary
        mock_provider = AsyncMock()
        mock_provider.generate = AsyncMock(return_value={
            "content": json.dumps({
                "key_facts": ["User wants to build a dashboard", "API keys configured"],
                "decisions": ["Use React for frontend", "PostgreSQL for database"],
                "open_threads": ["Need to design schema", "Authentication pending"]
            }),
            "model": "test-model",
            "tokens_used": 150,
            "latency_ms": 500,
        })

        with patch.object(ModelService, 'get_provider', AsyncMock(return_value=mock_provider)):
            summary_json = await summarize_history(db, user_id, model_config_id=None)

        # Verify summary structure
        assert summary_json is not None
        summary = json.loads(summary_json)
        assert "key_facts" in summary
        assert "decisions" in summary
        assert "open_threads" in summary
        assert len(summary["key_facts"]) > 0
        assert len(summary["decisions"]) > 0
        assert len(summary["open_threads"]) > 0

        # Verify stored in Redis
        stored = await load_summary(user_id)
        assert stored is not None
        assert stored == summary_json

        # Verify TTL (~7 days = 604800 seconds)
        ttl = redis_client.ttl(f"agentium:chat_summary:{user_id}")
        assert ttl > 0
        assert ttl <= 604800

    def test_format_summary_for_prompt_renders_readable(self):
        """JSON summary renders to human-readable block with labels."""
        summary_json = json.dumps({
            "key_facts": ["Fact A", "Fact B"],
            "decisions": ["Decision X"],
            "open_threads": ["Thread 1", "Thread 2"]
        })

        rendered = format_summary_for_prompt(summary_json)

        assert "Key facts:" in rendered
        assert "Fact A" in rendered
        assert "Fact B" in rendered
        assert "Decisions:" in rendered
        assert "Decision X" in rendered
        assert "Open threads:" in rendered
        assert "Thread 1" in rendered
        assert "Thread 2" in rendered

    async def test_get_full_history_recovers_middle_turn(self, seeded_db):
        """55 turns seeded, window=10: get_full_history returns all 55; turn-27 present."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        N = 55
        for i in range(N):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        set_chat_request(user_id=user_id, db=db)
        try:
            recovered = get_full_history(limit=200)
        finally:
            clear_chat_request()

        assert recovered["status"] == "ok"
        assert recovered["message_count"] >= N
        contents = [m["content"] for m in recovered["history"]]
        assert "turn-27-unique-marker-27" in contents

    async def test_search_chat_history_finds_query(self, seeded_db):
        """55 turns with unique markers: search_chat_history returns matching turns only."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        N = 55
        for i in range(N):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"turn-{i}-unique-marker-{i}",
            ))
        db.commit()

        set_chat_request(user_id=user_id, db=db)
        try:
            result = search_chat_history(query="turn-27", limit=20)
        finally:
            clear_chat_request()

        assert result["status"] == "ok"
        assert result["query"] == "turn-27"
        assert result["message_count"] >= 1
        # Only turn-27 should match
        for msg in result["history"]:
            assert "turn-27" in msg["content"]

    async def test_summarize_skips_short_conversations(self, seeded_db):
        """5 turns: summarize_history returns None (threshold: 6 turns)."""
        db = seeded_db
        user = db.query(User).filter_by(is_admin=True, is_active=True).first()
        assert user is not None
        user_id = str(user.id)

        db.query(ChatMsg).filter(ChatMsg.user_id == user_id).delete()
        db.commit()

        # Only 5 turns
        for i in range(5):
            role = "sovereign" if i % 2 == 0 else "head_of_council"
            db.add(ChatMsg(
                user_id=user_id,
                role=role,
                content=f"short-{i}",
            ))
        db.commit()

        summary_json = await summarize_history(db, user_id, model_config_id=None)
        assert summary_json is None


@pytest.mark.integration
class TestChatContextTokenEstimation:
    """Tests for token estimation and graceful truncation."""

    def test_estimate_tokens_positive(self):
        """Mixed messages: estimate_tokens returns positive integer."""
        messages = [
            {"role": "user", "content": "Hello, I need help building a dashboard."},
            {"role": "assistant", "content": "Sure! What kind of dashboard are you thinking?"},
            {"role": "user", "content": "A React dashboard with PostgreSQL backend."},
        ]
        system_prompt = "You are a helpful assistant."

        tokens = estimate_tokens(messages, system_prompt)

        assert isinstance(tokens, int)
        assert tokens > 0

    def test_truncate_preserves_pinned(self):
        """History exceeds model_limit: pinned first message never dropped; oldest non-pinned dropped first."""
        # Create a ChatContextBuilder with a small model_limit to force truncation
        builder = ChatContextBuilder(window_size=10, model_limit=100)

        # Create history: pinned first message + many recent messages
        history = [
            {"role": "user", "content": "First message - this is the original intent"},
        ]
        # Add 15 more messages to exceed the limit
        for i in range(15):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"Turn {i+1} - some content here to add tokens"})

        # First message is at index 0 (pinned)
        truncated, compressed = builder._truncate(history, summary=None, pinned_idx=0, limit=100)

        # Pinned message must be preserved
        assert truncated[0]["content"] == "First message - this is the original intent"
        # Should have fewer messages now
        assert len(truncated) < len(history)
        # Compressed should be True
        assert compressed is True

    def test_truncate_with_summary(self):
        """Summary + history exceeds limit: truncation works with summary in system prompt."""
        builder = ChatContextBuilder(window_size=10, model_limit=150)

        summary = json.dumps({
            "key_facts": ["User wants dashboard", "API keys configured"],
            "decisions": ["Use React", "PostgreSQL"],
            "open_threads": ["Design schema", "Auth"]
        })

        history = [
            {"role": "user", "content": "First message - build a dashboard"},
        ]
        # Add many messages
        for i in range(10):
            role = "user" if i % 2 == 0 else "assistant"
            history.append({"role": role, "content": f"Turn {i+1} - detailed discussion about implementation"})

        # Truncate with summary (pinned_idx=0)
        truncated, compressed = builder._truncate(history, summary=summary, pinned_idx=0, limit=150)

        # Pinned message preserved
        assert truncated[0]["content"] == "First message - build a dashboard"
        # Should be compressed
        assert compressed is True
        # Total tokens should be under limit
        total_tokens = estimate_tokens(truncated, summary)
        assert total_tokens <= 150