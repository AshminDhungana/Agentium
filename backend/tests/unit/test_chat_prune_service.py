"""
Unit tests for chat history auto-pruning service.
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
from sqlalchemy.orm import Session

from backend.services.chat_prune_service import (
    get_prune_preferences,
    get_conversations_due_for_soft_delete,
    get_messages_to_soft_delete,
    soft_delete_messages,
    get_soft_deleted_messages_due_for_hard_delete,
    hard_delete_messages,
    run_chat_prune_task,
)
from backend.models.entities.chat_message import ChatMessage, Conversation
from backend.models.entities.user_preference import UserPreference


class TestGetPrunePreferences:
    """Tests for get_prune_preferences function."""

    def test_defaults_when_no_prefs_exist(self):
        """Should return defaults when no preferences stored."""
        mock_db = MagicMock(spec=Session)
        mock_pref_svc = MagicMock()
        mock_pref_svc.get_value.side_effect = lambda key, default=None: default
        
        with patch('backend.services.chat_prune_service.UserPreferenceService', return_value=mock_pref_svc):
            prefs = get_prune_preferences(mock_db)
            
            assert prefs["enabled"] is True
            assert prefs["inactivity_days"] == 7
            assert prefs["hard_delete_days"] == 30
            assert prefs["retain_count"] == 10

    def test_uses_stored_preferences(self):
        """Should use stored preferences when they exist."""
        mock_db = MagicMock(spec=Session)
        mock_pref_svc = MagicMock()
        mock_pref_svc.get_value.side_effect = lambda key, default=None: {
            "chat.prune_enabled": False,
            "chat.prune_inactivity_days": 14,
            "chat.prune_hard_delete_days": 60,
            "chat.prune_retain_count": 20,
        }.get(key, default)
        
        with patch('backend.services.chat_prune_service.UserPreferenceService', return_value=mock_pref_svc):
            prefs = get_prune_preferences(mock_db)
            
            assert prefs["enabled"] is False
            assert prefs["inactivity_days"] == 14
            assert prefs["hard_delete_days"] == 60
            assert prefs["retain_count"] == 20


class TestGetConversationsDueForSoftDelete:
    """Tests for get_conversations_due_for_soft_delete function."""

    def test_returns_conversations_inactive_and_over_retain_count(self):
        """Should return conversations inactive for > inactivity_days with > retain_count messages."""
        mock_db = MagicMock(spec=Session)
        
        # Mock the subquery creation with proper column that supports comparison
        mock_msg_counts_subq = MagicMock()
        mock_msg_counts_subq.c = MagicMock()
        mock_msg_counts_subq.c.conversation_id = MagicMock()
        mock_msg_counts_subq.c.msg_count = MagicMock()
        # Make msg_count > int return a mock filter condition
        mock_msg_counts_subq.c.msg_count.__gt__ = MagicMock(return_value=MagicMock())
        
        # Mock the query chain for subquery - db.query() is called with multiple args
        mock_subq_query = MagicMock()
        mock_subq_query.filter.return_value = mock_subq_query
        mock_subq_query.group_by.return_value = mock_subq_query
        mock_subq_query.subquery.return_value = mock_msg_counts_subq
        
        # Mock the main query
        mock_conversation_query = MagicMock()
        mock_join_query = MagicMock()
        mock_filter_query = MagicMock()
        
        call_count = [0]
        
        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            # First call is for ChatMessage subquery
            if call_count[0] == 1:
                return mock_subq_query
            # Second call is for Conversation
            return mock_conversation_query
        
        mock_db.query.side_effect = query_side_effect
        
        mock_conversation_query.join.return_value = mock_join_query
        mock_join_query.filter.return_value = mock_filter_query
        mock_filter_query.all.return_value = [
            MagicMock(spec=Conversation, id="conv-1"),
            MagicMock(spec=Conversation, id="conv-2"),
        ]
        
        conversations = get_conversations_due_for_soft_delete(mock_db, inactivity_days=7, retain_count=10)
        
        assert len(conversations) == 2
        assert mock_db.query.call_count == 2  # Once for subquery, once for main query

    def test_excludes_recently_active_conversations(self):
        """Should not return conversations with recent activity."""
        mock_db = MagicMock(spec=Session)
        
        # Mock the subquery creation with proper column that supports comparison
        mock_msg_counts_subq = MagicMock()
        mock_msg_counts_subq.c = MagicMock()
        mock_msg_counts_subq.c.conversation_id = MagicMock()
        mock_msg_counts_subq.c.msg_count = MagicMock()
        mock_msg_counts_subq.c.msg_count.__gt__ = MagicMock(return_value=MagicMock())
        
        # Mock the query chain for subquery
        mock_subq_query = MagicMock()
        mock_subq_query.filter.return_value = mock_subq_query
        mock_subq_query.group_by.return_value = mock_subq_query
        mock_subq_query.subquery.return_value = mock_msg_counts_subq
        
        # Mock the main query
        mock_conversation_query = MagicMock()
        mock_join_query = MagicMock()
        mock_filter_query = MagicMock()
        
        call_count = [0]
        
        def query_side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_subq_query
            return mock_conversation_query
        
        mock_db.query.side_effect = query_side_effect
        
        mock_conversation_query.join.return_value = mock_join_query
        mock_join_query.filter.return_value = mock_filter_query
        mock_filter_query.all.return_value = []
        
        conversations = get_conversations_due_for_soft_delete(mock_db, inactivity_days=7, retain_count=10)
        
        assert conversations == []


class TestGetMessagesToSoftDelete:
    """Tests for get_messages_to_soft_delete function."""

    def test_returns_messages_except_last_n(self):
        """Should return all non-deleted messages except the last retain_count."""
        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.limit.return_value = mock_query
        mock_query.subquery.return_value = MagicMock()
        
        # Mock final query result
        final_query = MagicMock()
        mock_db.query.return_value = final_query
        final_query.filter.return_value = final_query
        final_query.all.return_value = [
            MagicMock(spec=ChatMessage, id="msg-1"),
            MagicMock(spec=ChatMessage, id="msg-2"),
        ]
        
        messages = get_messages_to_soft_delete(mock_db, "conv-1", retain_count=10)
        
        assert len(messages) == 2


class TestSoftDeleteMessages:
    """Tests for soft_delete_messages function."""

    def test_soft_deletes_messages_when_not_dry_run(self):
        """Should set is_deleted='Y' and commit when not dry run."""
        mock_db = MagicMock(spec=Session)
        messages = [
            MagicMock(spec=ChatMessage, is_deleted="N"),
            MagicMock(spec=ChatMessage, is_deleted="N"),
        ]
        
        count = soft_delete_messages(mock_db, messages, dry_run=False)
        
        assert count == 2
        assert all(m.is_deleted == "Y" for m in messages)
        mock_db.commit.assert_called_once()

    def test_dry_run_returns_count_without_changes(self):
        """Should return count but not modify messages or commit."""
        mock_db = MagicMock(spec=Session)
        messages = [
            MagicMock(spec=ChatMessage, is_deleted="N"),
        ]
        
        count = soft_delete_messages(mock_db, messages, dry_run=True)
        
        assert count == 1
        assert messages[0].is_deleted == "N"  # unchanged
        mock_db.commit.assert_not_called()

    def test_empty_list_returns_zero(self):
        """Should return 0 for empty list."""
        mock_db = MagicMock(spec=Session)
        
        count = soft_delete_messages(mock_db, [], dry_run=False)
        
        assert count == 0
        mock_db.commit.assert_not_called()


class TestGetSoftDeletedMessagesDueForHardDelete:
    """Tests for get_soft_deleted_messages_due_for_hard_delete function."""

    def test_returns_old_soft_deleted_messages(self):
        """Should return soft-deleted messages older than hard_delete_days."""
        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = [
            MagicMock(spec=ChatMessage, id="msg-1"),
            MagicMock(spec=ChatMessage, id="msg-2"),
        ]
        
        messages = get_soft_deleted_messages_due_for_hard_delete(mock_db, hard_delete_days=30)
        
        assert len(messages) == 2

    def test_excludes_recently_soft_deleted(self):
        """Should not return recently soft-deleted messages."""
        mock_db = MagicMock(spec=Session)
        mock_query = MagicMock()
        mock_db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.all.return_value = []
        
        messages = get_soft_deleted_messages_due_for_hard_delete(mock_db, hard_delete_days=30)
        
        assert messages == []


class TestHardDeleteMessages:
    """Tests for hard_delete_messages function."""

    def test_hard_deletes_messages_when_not_dry_run(self):
        """Should delete messages and commit when not dry run."""
        mock_db = MagicMock(spec=Session)
        messages = [
            MagicMock(spec=ChatMessage),
            MagicMock(spec=ChatMessage),
        ]
        
        count = hard_delete_messages(mock_db, messages, dry_run=False)
        
        assert count == 2
        assert mock_db.delete.call_count == 2
        mock_db.commit.assert_called_once()

    def test_dry_run_returns_count_without_deleting(self):
        """Should return count but not delete or commit."""
        mock_db = MagicMock(spec=Session)
        messages = [MagicMock(spec=ChatMessage)]
        
        count = hard_delete_messages(mock_db, messages, dry_run=True)
        
        assert count == 1
        mock_db.delete.assert_not_called()
        mock_db.commit.assert_not_called()


class TestRunChatPruneTask:
    """Integration tests for run_chat_prune_task function."""

    def test_returns_disabled_when_prefs_disabled(self):
        """Should return early with enabled=False when pruning disabled."""
        with patch('backend.services.chat_prune_service.SessionLocal') as mock_session:
            mock_db = MagicMock(spec=Session)
            mock_session.return_value = mock_db
            
            with patch('backend.services.chat_prune_service.get_prune_preferences', return_value={"enabled": False}):
                result = run_chat_prune_task()
                
                assert result["enabled"] is False
                assert result["soft_deleted_count"] == 0
                assert result["hard_deleted_count"] == 0

    def test_uses_overrides_when_provided(self):
        """Should use override values when provided."""
        with patch('backend.services.chat_prune_service.SessionLocal') as mock_session:
            mock_db = MagicMock(spec=Session)
            mock_session.return_value = mock_db
            
            with patch('backend.services.chat_prune_service.get_prune_preferences', return_value={
                "enabled": True,
                "inactivity_days": 7,
                "hard_delete_days": 30,
                "retain_count": 10,
            }):
                with patch('backend.services.chat_prune_service.get_conversations_due_for_soft_delete', return_value=[]):
                    with patch('backend.services.chat_prune_service.get_soft_deleted_messages_due_for_hard_delete', return_value=[]):
                        result = run_chat_prune_task(
                            override_inactivity_days=14,
                            override_hard_delete_days=60,
                            override_retain_count=20,
                        )
                        
                        assert result["params"]["inactivity_days"] == 14
                        assert result["params"]["hard_delete_days"] == 60
                        assert result["params"]["retain_count"] == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v"])