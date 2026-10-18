# tests/unit/core/test_constitutional_guard_session.py
import pytest
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from backend.core.constitutional_guard import ConstitutionalGuard


class TestConstitutionalGuardSessionIsolation:
    """Test that Redis cache keys are namespaced with session_id for isolation."""

    def test_embedding_cache_key_includes_session_id(self):
        """Test that embedding cache key includes session_id when provided."""
        guard = ConstitutionalGuard(db=None)

        # Test without session_id (backward compatibility) - uses hash of text
        text = "test action"
        expected_hash = hashlib.sha256(text.encode()).hexdigest()[:16]
        key_without = guard._embedding_cache_key(text)
        assert key_without == f"constitutional_guard:semantic:{expected_hash}"

        # Test with session_id - should include session_id in key
        key_with = guard._embedding_cache_key(text, session_id="session123")
        assert "session123" in key_with
        assert key_with == f"constitutional_guard:semantic:session123:{expected_hash}"

    def test_embedding_cache_key_different_sessions_different_keys(self):
        """Test that different sessions produce different cache keys for same action."""
        guard = ConstitutionalGuard(db=None)

        key1 = guard._embedding_cache_key("test action", session_id="session1")
        key2 = guard._embedding_cache_key("test action", session_id="session2")

        assert key1 != key2
        assert "session1" in key1
        assert "session2" in key2

    @pytest.mark.asyncio
    async def test_embedding_cache_result_uses_session_id(self):
        """Test that embedding cache result uses session_id in key."""
        guard = ConstitutionalGuard(db=None)
        guard._redis = AsyncMock()
        guard._redis.get = AsyncMock(return_value=None)

        # Call with session_id
        await guard._get_cached_embedding_result("test action", session_id="session456")

        # Verify redis.get was called with session-specific key
        guard._redis.get.assert_called()
        call_args = guard._redis.get.call_args[0][0]
        assert "session456" in call_args

    @pytest.mark.asyncio
    async def test_cache_embedding_result_uses_session_id(self):
        """Test that caching embedding result uses session_id in key."""
        from backend.core.constitutional_guard import ConstitutionalDecision, Verdict, ViolationSeverity

        guard = ConstitutionalGuard(db=None)
        guard._redis = AsyncMock()
        guard._redis.setex = AsyncMock()

        decision = ConstitutionalDecision(
            verdict=Verdict.ALLOW,
            severity=ViolationSeverity.LOW,
            explanation="Test"
        )

        # Call with session_id
        await guard._cache_embedding_result("test action", decision, session_id="session789")

        # Verify redis.setex was called with session-specific key
        guard._redis.setex.assert_called()
        call_args = guard._redis.setex.call_args[0][0]
        assert "session789" in call_args