"""
Integration tests for context window management (context_manager.py).
Verifies warning/critical thresholds, reincarnation trigger, and wisdom transfer.
"""

import pytest
from backend.services.context_manager import (
    ContextWindowManager,
    context_manager,
    ContextWindowStatus,
)


class TestContextManagerThresholds:
    """Tests for warning/critical thresholds and reincarnation trigger."""

    def setup_method(self):
        """Reset singleton before each test."""
        context_manager.agent_contexts.clear()

    def test_warning_threshold_at_75_percent(self):
        """Register agent (128k limit), update to 96k tokens: is_warning=True, is_critical=False, usage_percentage ≈ 0.75."""
        context_manager.register_agent("test-agent-1", "gpt-4o", initial_tokens=0)
        status = context_manager.update_usage("test-agent-1", tokens_used=96000)

        assert status is not None
        assert status.is_warning is True
        assert status.is_critical is False
        assert abs(status.usage_percentage - 0.75) < 0.01

    def test_critical_threshold_at_90_percent(self):
        """Update to 115k tokens: is_critical=True, is_warning=True."""
        context_manager.register_agent("test-agent-2", "gpt-4o", initial_tokens=0)
        status = context_manager.update_usage("test-agent-2", tokens_used=115200)

        assert status is not None
        assert status.is_critical is True
        assert status.is_warning is True

    def test_absolute_max_at_95_percent(self):
        """Update to 121k tokens: should_reincarnate=True."""
        context_manager.register_agent("test-agent-3", "gpt-4o", initial_tokens=0)
        context_manager.update_usage("test-agent-3", tokens_used=121600)

        should_reinc = context_manager.should_reincarnate("test-agent-3")
        assert should_reinc is True

    def test_unknown_model_uses_default_limit(self):
        """Register with 'unknown-model': max_tokens=128000 (default)."""
        context_manager.register_agent("test-agent-4", "unknown-model", initial_tokens=0)
        status = context_manager.check_status("test-agent-4")

        assert status is not None
        assert status.max_tokens == 128000

    def test_update_usage_sets_current_not_accumulates(self):
        """update_usage(100), then update_usage(200): current_tokens=200 (not 300)."""
        context_manager.register_agent("test-agent-5", "gpt-4o", initial_tokens=0)

        # First update
        context_manager.update_usage("test-agent-5", tokens_used=100)
        status1 = context_manager.check_status("test-agent-5")
        assert status1.current_tokens == 100

        # Second update should REPLACE, not add
        context_manager.update_usage("test-agent-5", tokens_used=200)
        status2 = context_manager.check_status("test-agent-5")
        assert status2.current_tokens == 200
        assert status2.current_tokens != 300


class TestContextManagerWisdomTransfer:
    """Tests for wisdom accumulation and transfer across incarnations."""

    def setup_method(self):
        """Reset singleton before each test."""
        context_manager.agent_contexts.clear()

    def test_add_wisdom_stores_entry(self):
        """add_wisdom(summary='completed X', topics=['A','B']): accumulated_wisdom has 1 entry with timestamp, incarnation, summary, topics, token_count."""
        context_manager.register_agent("test-agent-6", "gpt-4o")
        context_manager.add_wisdom("test-agent-6", "completed dashboard build", ["React", "PostgreSQL"])

        stats = context_manager.get_stats("test-agent-6")
        assert stats["wisdom_entries"] == 1
        assert stats["total_wisdom_tokens"] > 0

        ctx = context_manager.agent_contexts["test-agent-6"]
        wisdom = ctx["accumulated_wisdom"][0]
        assert "timestamp" in wisdom
        assert wisdom["incarnation"] == 1
        assert wisdom["summary"] == "completed dashboard build"
        assert wisdom["topics"] == ["React", "PostgreSQL"]
        assert wisdom["token_count"] > 0

    def test_multiple_wisdom_entries_accumulate(self):
        """add_wisdom 3 times: 3 entries, get_stats shows correct counts."""
        context_manager.register_agent("test-agent-7", "gpt-4o")
        context_manager.add_wisdom("test-agent-7", "first task", ["A"])
        context_manager.add_wisdom("test-agent-7", "second task", ["B"])
        context_manager.add_wisdom("test-agent-7", "third task", ["C"])

        stats = context_manager.get_stats("test-agent-7")
        assert stats["wisdom_entries"] == 3
        assert stats["total_wisdom_tokens"] > 0

    def test_prepare_for_reincarnation_returns_wisdom(self):
        """Add wisdom, call prepare_for_reincarnation: returns incarnation_number, accumulated_wisdom."""
        context_manager.register_agent("test-agent-8", "gpt-4o")
        context_manager.add_wisdom("test-agent-8", "learned about APIs", ["REST", "GraphQL"])

        reinc_data = context_manager.prepare_for_reincarnation("test-agent-8")

        assert "incarnation_number" in reinc_data
        assert reinc_data["incarnation_number"] == 1
        assert "accumulated_wisdom" in reinc_data
        assert len(reinc_data["accumulated_wisdom"]) == 1
        assert reinc_data["accumulated_wisdom"][0]["summary"] == "learned about APIs"
        assert "total_tokens_processed" in reinc_data
        assert "total_messages" in reinc_data
        assert "model" in reinc_data

    def test_transfer_to_successor_inherits_wisdom(self):
        """Create old_id, add wisdom, transfer to new_id: New agent has incarnation=2, copied accumulated_wisdom, fresh current_tokens=0, message_count=0."""
        context_manager.register_agent("old-agent-1", "gpt-4o")
        context_manager.add_wisdom("old-agent-1", "important knowledge", ["topic1"])

        context_manager.transfer_to_successor("old-agent-1", "new-agent-1")

        # Old agent cleaned up
        assert "old-agent-1" not in context_manager.agent_contexts

        # New agent has inherited wisdom
        stats = context_manager.get_stats("new-agent-1")
        assert stats["incarnation"] == 2
        assert stats["wisdom_entries"] == 1
        assert stats["current_tokens"] == 0
        # message_count should be 0 for fresh context

        new_ctx = context_manager.agent_contexts["new-agent-1"]
        assert new_ctx["current_tokens"] == 0
        assert new_ctx["message_count"] == 0
        assert new_ctx["accumulated_wisdom"][0]["summary"] == "important knowledge"

    def test_transfer_cleans_up_old_context(self):
        """After transfer: old_id removed from agent_contexts."""
        context_manager.register_agent("old-agent-2", "gpt-4o")
        context_manager.add_wisdom("old-agent-2", "wisdom", ["topic"])

        context_manager.transfer_to_successor("old-agent-2", "new-agent-2")

        # Old agent should be gone
        assert "old-agent-2" not in context_manager.agent_contexts
        # New agent should exist
        assert "new-agent-2" in context_manager.agent_contexts