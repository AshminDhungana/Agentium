# backend/tests/unit/test_alert_deduplicator.py
"""
Unit tests for AlertDeduplicator.
Tests Redis TTL-based deduplication logic with fail-open behavior.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.alert_deduplicator import AlertDeduplicator
from backend.models.entities.monitoring import ViolationSeverity


class TestAlertDeduplicator:
    """Test AlertDeduplicator deduplication logic."""

    @pytest.fixture
    def mock_redis(self):
        """Mock Redis client."""
        redis = MagicMock()
        redis.zadd = AsyncMock(return_value=1)
        redis.zremrangebyscore = AsyncMock(return_value=0)
        redis.zcard = AsyncMock(return_value=0)
        redis.expire = AsyncMock(return_value=True)
        return redis

    @pytest.fixture
    def deduplicator(self, mock_redis):
        """Create AlertDeduplicator with mocked Redis."""
        with patch('backend.services.channel_manager.get_redis_client', return_value=mock_redis):
            return AlertDeduplicator()

    @pytest.mark.asyncio
    async def test_should_suppress_first_alert_returns_false(self, deduplicator, mock_redis):
        """First alert of a type should not be suppressed."""
        mock_redis.zcard.return_value = 0

        result = await deduplicator.should_suppress(
            alert_type="test_alert",
            affected_agent_id="agent-001",
            severity=ViolationSeverity.CRITICAL
        )

        assert result is False
        mock_redis.zcard.assert_called_once()

    @pytest.mark.asyncio
    async def test_should_suppress_duplicate_within_window_returns_true(self, deduplicator, mock_redis):
        """Duplicate alert within time window should be suppressed."""
        mock_redis.zcard.return_value = 1  # Existing alert in window

        result = await deduplicator.should_suppress(
            alert_type="test_alert",
            affected_agent_id="agent-001",
            severity=ViolationSeverity.CRITICAL
        )

        assert result is True

    @pytest.mark.asyncio
    async def test_should_suppress_different_agent_not_suppressed(self, deduplicator, mock_redis):
        """Different affected_agent_id should not be suppressed."""
        mock_redis.zcard.return_value = 0

        result = await deduplicator.should_suppress(
            alert_type="test_alert",
            affected_agent_id="agent-002",  # Different agent
            severity=ViolationSeverity.CRITICAL
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_should_suppress_different_severity_not_suppressed(self, deduplicator, mock_redis):
        """Different severity should not be suppressed."""
        mock_redis.zcard.return_value = 0

        result = await deduplicator.should_suppress(
            alert_type="test_alert",
            affected_agent_id="agent-001",
            severity=ViolationSeverity.MAJOR  # Different severity
        )

        assert result is False

    @pytest.mark.asyncio
    async def test_should_suppress_none_affected_agent_uses_system(self, deduplicator, mock_redis):
        """None affected_agent_id should use 'system' in key."""
        mock_redis.zcard.return_value = 0

        result = await deduplicator.should_suppress(
            alert_type="system_alert",
            affected_agent_id=None,
            severity=ViolationSeverity.CRITICAL
        )

        assert result is False
        # Verify key contains 'system'
        call_args = mock_redis.zcard.call_args[0][0]
        assert 'system' in call_args

    @pytest.mark.asyncio
    async def test_record_alert_adds_to_redis(self, deduplicator, mock_redis):
        """record_alert should add entry to Redis sorted set with TTL."""
        await deduplicator.record_alert(
            alert_type="test_alert",
            affected_agent_id="agent-001",
            severity=ViolationSeverity.CRITICAL
        )

        mock_redis.zadd.assert_called_once()
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_fail_open_on_redis_error(self, deduplicator, mock_redis):
        """Redis errors should fail open (return False - don't suppress)."""
        mock_redis.zcard.side_effect = Exception("Redis connection failed")

        result = await deduplicator.should_suppress(
            alert_type="test_alert",
            affected_agent_id="agent-001",
            severity=ViolationSeverity.CRITICAL
        )

        assert result is False  # Fail open

    def test_get_window_seconds_uses_default(self, deduplicator):
        """get_window_seconds returns default for unknown alert types."""
        assert deduplicator.get_window_seconds("unknown_alert") == 300

    def test_get_window_seconds_uses_override(self, deduplicator):
        """get_window_seconds returns configured override for known alert types."""
        # This will be tested after config integration
        pass