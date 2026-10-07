# backend/tests/integration/test_alert_deduplication.py
"""
Integration tests for AlertManager with AlertDeduplicator.
Tests that duplicate alerts are suppressed within the deduplication window.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from datetime import datetime

from backend.services.alert_manager import AlertManager, get_alert_manager
from backend.services.alert_deduplicator import get_alert_deduplicator
from backend.models.entities.monitoring import MonitoringAlert, ViolationSeverity
from backend.models.entities.agents import Agent, AgentType


class TestAlertManagerDeduplication:
    """Test AlertManager integration with AlertDeduplicator."""

    @pytest.fixture
    def mock_db(self):
        """Mock database session."""
        db = MagicMock(spec=Session)
        return db

    @pytest.fixture
    def sample_alert(self):
        """Create a sample MonitoringAlert."""
        alert = MonitoringAlert(
            alert_type="test_alert",
            severity=ViolationSeverity.CRITICAL,
            detected_by_agent_id="detector-001",
            affected_agent_id="agent-001",
            message="Test alert message",
            metadata={"auto_generated": True}
        )
        alert.id = "alert-001"
        alert.created_at = datetime.utcnow()
        return alert

    @pytest.fixture
    def alert_manager(self, mock_db):
        """Create AlertManager with mocked dependencies."""
        with patch('backend.services.alert_manager.ChannelManager') as mock_cm:
            mock_cm.return_value = MagicMock()
            return AlertManager(mock_db)

    @pytest.mark.asyncio
    async def test_first_alert_dispatched(self, alert_manager, sample_alert):
        """First alert should be dispatched normally."""
        with patch('backend.services.alert_deduplicator.get_alert_deduplicator') as mock_get_dedup:
            mock_dedup = AsyncMock()
            mock_dedup.should_suppress.return_value = False
            mock_dedup.record_alert = AsyncMock()
            mock_get_dedup.return_value = mock_dedup

            with patch.object(alert_manager, '_broadcast_websocket', AsyncMock()) as mock_ws:
                with patch.object(alert_manager, '_notify_external_channels', AsyncMock()) as mock_ext:
                    with patch.object(alert_manager, '_send_email_alert', AsyncMock()) as mock_email:
                        with patch.object(alert_manager, '_send_webhook_alert', AsyncMock()) as mock_webhook:
                            await alert_manager.dispatch_alert(sample_alert)

                            # Verify dispatch methods called
                            mock_ws.assert_called_once()
                            mock_dedup.should_suppress.assert_called_once()
                            mock_dedup.record_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_duplicate_alert_suppressed(self, alert_manager, sample_alert):
        """Duplicate alert within window should be suppressed (not dispatched)."""
        with patch('backend.services.alert_deduplicator.get_alert_deduplicator') as mock_get_dedup:
            mock_dedup = AsyncMock()
            mock_dedup.should_suppress.return_value = True  # Suppress!
            mock_dedup.record_alert = AsyncMock()
            mock_get_dedup.return_value = mock_dedup

            with patch.object(alert_manager, '_broadcast_websocket', AsyncMock()) as mock_ws:
                with patch.object(alert_manager, '_notify_external_channels', AsyncMock()) as mock_ext:
                    with patch.object(alert_manager, '_send_email_alert', AsyncMock()) as mock_email:
                        with patch.object(alert_manager, '_send_webhook_alert', AsyncMock()) as mock_webhook:
                            await alert_manager.dispatch_alert(sample_alert)

                            # Verify dispatch methods NOT called
                            mock_ws.assert_not_called()
                            mock_ext.assert_not_called()
                            mock_email.assert_not_called()
                            mock_webhook.assert_not_called()
                            # But record_alert should NOT be called for suppressed alerts
                            mock_dedup.record_alert.assert_not_called()

    @pytest.mark.asyncio
    async def test_suppressed_alert_still_persisted_to_db(self, alert_manager, mock_db, sample_alert):
        """Suppressed alert should still be added to DB for audit trail."""
        with patch('backend.services.alert_deduplicator.get_alert_deduplicator') as mock_get_dedup:
            mock_dedup = AsyncMock()
            mock_dedup.should_suppress.return_value = True
            mock_get_dedup.return_value = mock_dedup

            with patch.object(alert_manager, '_broadcast_websocket', AsyncMock()):
                with patch.object(alert_manager, '_notify_external_channels', AsyncMock()):
                    with patch.object(alert_manager, '_send_email_alert', AsyncMock()):
                        with patch.object(alert_manager, '_send_webhook_alert', AsyncMock()):
                            await alert_manager.dispatch_alert(sample_alert)

                            # Alert should still be added to DB (for audit)
                            mock_db.add.assert_called()
                            mock_db.commit.assert_called()

    @pytest.mark.asyncio
    async def test_different_severity_not_suppressed(self, alert_manager, sample_alert):
        """Alert with different severity should not be suppressed."""
        with patch('backend.services.alert_deduplicator.get_alert_deduplicator') as mock_get_dedup:
            mock_dedup = AsyncMock()
            # First call (CRITICAL) returns False, second call (MAJOR) also returns False
            mock_dedup.should_suppress.side_effect = [False, False]
            mock_dedup.record_alert = AsyncMock()
            mock_get_dedup.return_value = mock_dedup

            with patch.object(alert_manager, '_broadcast_websocket', AsyncMock()):
                with patch.object(alert_manager, '_notify_external_channels', AsyncMock()):
                    with patch.object(alert_manager, '_send_email_alert', AsyncMock()):
                        with patch.object(alert_manager, '_send_webhook_alert', AsyncMock()):
                            # First alert - CRITICAL
                            await alert_manager.dispatch_alert(sample_alert)

                            # Second alert - MAJOR (different severity)
                            sample_alert.severity = ViolationSeverity.MAJOR
                            await alert_manager.dispatch_alert(sample_alert)

                            # Both should be dispatched
                            assert mock_dedup.should_suppress.call_count == 2
                            assert mock_dedup.record_alert.call_count == 2