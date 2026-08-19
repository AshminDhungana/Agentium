"""
Unit tests for Channel models.
Tests ExternalChannel, ExternalMessage, and ChannelMetrics.
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

try:
    from backend.models.entities.channels import (
        ExternalChannel, ExternalMessage, ChannelMetrics,
        ChannelType, ChannelStatus, CircuitBreakerState
    )
except ImportError:
    from models.entities.channels import (
        ExternalChannel, ExternalMessage, ChannelMetrics,
        ChannelType, ChannelStatus, CircuitBreakerState
    )


class TestChannelType:
    """Tests for ChannelType enum."""

    @pytest.mark.parametrize("channel_type", [
        ChannelType.WHATSAPP, ChannelType.SLACK, ChannelType.TELEGRAM,
        ChannelType.EMAIL, ChannelType.DISCORD, ChannelType.SIGNAL,
        ChannelType.GOOGLE_CHAT, ChannelType.TEAMS, ChannelType.ZALO,
        ChannelType.MATRIX, ChannelType.IMESSAGE, ChannelType.CUSTOM,
    ])
    def test_channel_type_values(self, channel_type):
        """All ChannelType values are valid."""
        assert channel_type in (
            ChannelType.WHATSAPP, ChannelType.SLACK, ChannelType.TELEGRAM,
            ChannelType.EMAIL, ChannelType.DISCORD, ChannelType.SIGNAL,
            ChannelType.GOOGLE_CHAT, ChannelType.TEAMS, ChannelType.ZALO,
            ChannelType.MATRIX, ChannelType.IMESSAGE, ChannelType.CUSTOM,
        )
        assert isinstance(channel_type.value, str)

    def test_channel_type_string_values(self):
        """ChannelType string values match expected."""
        assert ChannelType.WHATSAPP.value == "whatsapp"
        assert ChannelType.SLACK.value == "slack"
        assert ChannelType.EMAIL.value == "email"
        assert ChannelType.CUSTOM.value == "custom"


class TestChannelStatus:
    """Tests for ChannelStatus enum."""

    @pytest.mark.parametrize("status", [
        ChannelStatus.PENDING, ChannelStatus.ACTIVE, ChannelStatus.ERROR,
        ChannelStatus.DISCONNECTED, ChannelStatus.ARCHIVED,
    ])
    def test_channel_status_values(self, status):
        """All ChannelStatus values are valid."""
        assert status in (
            ChannelStatus.PENDING, ChannelStatus.ACTIVE, ChannelStatus.ERROR,
            ChannelStatus.DISCONNECTED, ChannelStatus.ARCHIVED,
        )
        assert isinstance(status.value, str)


class TestCircuitBreakerState:
    """Tests for CircuitBreakerState enum."""

    @pytest.mark.parametrize("state", [
        CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN, CircuitBreakerState.OPEN,
    ])
    def test_circuit_breaker_state_values(self, state):
        """All CircuitBreakerState values are valid."""
        assert state in (
            CircuitBreakerState.CLOSED, CircuitBreakerState.HALF_OPEN, CircuitBreakerState.OPEN,
        )
        assert isinstance(state.value, str)


class TestExternalChannel:
    """Tests for ExternalChannel model."""

    def test_external_channel_creation(self, db_session):
        """ExternalChannel creates with all required fields."""
        channel = ExternalChannel(
            agentium_id="CH00000001",  # Required - ExternalChannel doesn't auto-generate
            name="Support WhatsApp",
            channel_type=ChannelType.WHATSAPP,
            user_id="test-user-id",
            config={"phone_number": "+15551234567", "api_key": "sk_test_123"},
            default_agent_id="agent-uuid-1",
            auto_create_tasks=True,
            require_approval=False,
            webhook_path="abc123",
        )
        db_session.add(channel)
        db_session.commit()
        db_session.refresh(channel)

        assert channel.name == "Support WhatsApp"
        assert channel.channel_type == ChannelType.WHATSAPP
        assert channel.status == ChannelStatus.PENDING
        assert channel.user_id == "test-user-id"
        assert channel.config["phone_number"] == "+15551234567"
        assert channel.config["api_key"] == "sk_test_123"
        assert channel.default_agent_id == "agent-uuid-1"
        assert channel.auto_create_tasks is True
        assert channel.require_approval is False
        assert channel.webhook_path == "abc123"
        assert channel.messages_received == 0
        assert channel.messages_sent == 0
        assert channel.agentium_id == "CH00000001"

    def test_external_channel_defaults(self, db_session):
        """ExternalChannel defaults are correct."""
        channel = ExternalChannel(
            agentium_id="CH00000002",  # Required
            name="Test Channel",
            channel_type=ChannelType.SLACK,
        )
        db_session.add(channel)
        db_session.commit()

        assert channel.status == ChannelStatus.PENDING
        assert channel.config == {}
        assert channel.auto_create_tasks is True
        assert channel.require_approval is False
        assert channel.messages_received == 0
        assert channel.messages_sent == 0

    def test_external_channel_webhook_url_generation(self, db_session):
        """generate_webhook_url() creates correct URL."""
        channel = ExternalChannel(
            agentium_id="CH00000003",  # Required
            name="Test Channel",
            channel_type=ChannelType.EMAIL,
            webhook_path="xyz789",
        )
        db_session.add(channel)
        db_session.commit()

        url = channel.generate_webhook_url("https://api.example.com")
        assert url == "https://api.example.com/webhooks/email/xyz789"

    def test_external_channel_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        channel = ExternalChannel(
            agentium_id="CH00000004",  # Required
            name="Test Channel",
            channel_type=ChannelType.TELEGRAM,
            user_id="user-123",
            config={"api_key": "secret"},
            default_agent_id="agent-uuid-1",
        )
        db_session.add(channel)
        db_session.commit()

        data = channel.to_dict()
        assert data["name"] == "Test Channel"
        assert data["type"] == "telegram"
        assert data["status"] == "pending"
        assert data["user_id"] == "user-123"
        assert "config" in data
        assert data["config"]["has_credentials"] is True
        assert data["routing"]["default_agent"] == "agent-uuid-1"
        assert data["routing"]["auto_create_tasks"] is True
        assert data["stats"]["received"] == 0
        assert data["stats"]["sent"] == 0


class TestExternalMessage:
    """Tests for ExternalMessage model."""

    def test_external_message_creation(self, db_session):
        """ExternalMessage creates with all required fields."""
        # Create parent channel first
        channel = ExternalChannel(
            agentium_id="CH00000005",  # Required
            name="WhatsApp Channel",
            channel_type=ChannelType.WHATSAPP,
        )
        db_session.add(channel)
        db_session.commit()
        db_session.refresh(channel)

        message = ExternalMessage(
            channel_id=channel.id,
            sender_id="+15559876543",
            sender_name="John Doe",
            sender_metadata={"profile_pic_url": "https://example.com/pic.jpg"},
            message_type="text",
            content="Hello, I need help with my account.",
            raw_payload={"message_id": "wamid.xxx", "type": "text"},
        )
        db_session.add(message)
        db_session.commit()
        db_session.refresh(message)

        assert message.channel_id == channel.id
        assert message.sender_id == "+15559876543"
        assert message.sender_name == "John Doe"
        assert message.message_type == "text"
        assert message.content == "Hello, I need help with my account."
        assert message.status == "received"
        assert message.error_count == 0
        assert message.agentium_id.startswith("EM")

    def test_external_message_defaults(self, db_session):
        """ExternalMessage defaults are correct."""
        channel = ExternalChannel(
            agentium_id="CH00000006",  # Required
            name="Test Channel",
            channel_type=ChannelType.SLACK,
        )
        db_session.add(channel)
        db_session.commit()

        message = ExternalMessage(
            channel_id=channel.id,
            sender_id="user123",
            content="Test message",
        )
        db_session.add(message)
        db_session.commit()

        assert message.message_type == "text"
        assert message.status == "received"
        assert message.sender_metadata == {}
        assert message.raw_payload is None
        assert message.media_url is None
        assert message.assigned_agent_id is None
        assert message.task_id is None
        assert message.response_content is None
        assert message.responded_at is None
        assert message.responded_by_agent_id is None
        assert message.error_count == 0
        assert message.last_error is None

    def test_external_message_mark_processing(self, db_session):
        """mark_processing() updates status and assigned_agent."""
        channel = ExternalChannel(
            agentium_id="CH00000007",  # Required
            name="Test Channel",
            channel_type=ChannelType.EMAIL,
        )
        db_session.add(channel)
        db_session.commit()

        message = ExternalMessage(
            channel_id=channel.id,
            sender_id="user123",
            content="Test",
        )
        db_session.add(message)
        db_session.commit()

        message.mark_processing("agent-uuid-1")
        db_session.commit()

        assert message.status == "processing"
        assert message.assigned_agent_id == "agent-uuid-1"

    def test_external_message_mark_responded(self, db_session):
        """mark_responded() updates response fields and increments channel counter."""
        channel = ExternalChannel(
            agentium_id="CH00000008",  # Required
            name="Test Channel",
            channel_type=ChannelType.SLACK,
        )
        db_session.add(channel)
        db_session.commit()

        message = ExternalMessage(
            channel_id=channel.id,
            sender_id="user123",
            content="Test",
        )
        db_session.add(message)
        db_session.commit()

        assert channel.messages_sent == 0

        message.mark_responded("Thanks for your message!", "agent-uuid-1")
        db_session.commit()

        assert message.status == "responded"
        assert message.response_content == "Thanks for your message!"
        assert message.responded_at is not None
        assert message.responded_by_agent_id == "agent-uuid-1"
        assert channel.messages_sent == 1

    def test_external_message_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        channel = ExternalChannel(
            agentium_id="CH00000009",  # Required
            name="WhatsApp Channel",
            channel_type=ChannelType.WHATSAPP,
        )
        db_session.add(channel)
        db_session.commit()

        message = ExternalMessage(
            channel_id=channel.id,
            sender_id="+15551234567",
            sender_name="Jane Smith",
            content="Hello world",
        )
        db_session.add(message)
        db_session.commit()

        data = message.to_dict()
        assert data["channel"]["id"] == channel.id
        assert data["channel"]["name"] == "WhatsApp Channel"
        assert data["channel"]["type"] == "whatsapp"
        assert data["sender"]["id"] == "+15551234567"
        assert data["sender"]["name"] == "Jane Smith"
        assert data["content"] == "Hello world"
        assert data["type"] == "text"
        assert data["status"] == "received"
        assert "timestamp" in data


class TestChannelMetrics:
    """Tests for ChannelMetrics model."""

    def test_channel_metrics_creation(self, db_session):
        """ChannelMetrics creates with all fields."""
        channel = ExternalChannel(
            agentium_id="CH00000010",  # Required
            name="Metrics Test Channel",
            channel_type=ChannelType.DISCORD,
        )
        db_session.add(channel)
        db_session.commit()
        db_session.refresh(channel)

        metrics = ChannelMetrics(
            agentium_id="CM00000001",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel.id,
            total_requests=100,
            successful_requests=95,
            failed_requests=5,
            circuit_breaker_state=CircuitBreakerState.CLOSED,
            consecutive_failures=0,
            rate_limit_hits=2,
            avg_response_time_ms=150,
        )
        db_session.add(metrics)
        db_session.commit()
        db_session.refresh(metrics)

        assert metrics.channel_id == channel.id
        assert metrics.total_requests == 100
        assert metrics.successful_requests == 95
        assert metrics.failed_requests == 5
        assert metrics.circuit_breaker_state == CircuitBreakerState.CLOSED
        assert metrics.consecutive_failures == 0
        assert metrics.rate_limit_hits == 2
        assert metrics.avg_response_time_ms == 150

    def test_channel_metrics_defaults(self, db_session):
        """ChannelMetrics defaults are correct."""
        channel = ExternalChannel(
            agentium_id="CH00000011",  # Required
            name="Default Metrics Channel",
            channel_type=ChannelType.EMAIL,
        )
        db_session.add(channel)
        db_session.commit()

        metrics = ChannelMetrics(
            agentium_id="CM00000002",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel.id
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.total_requests == 0
        assert metrics.successful_requests == 0
        assert metrics.failed_requests == 0
        assert metrics.circuit_breaker_state == CircuitBreakerState.CLOSED
        assert metrics.consecutive_failures == 0
        assert metrics.rate_limit_hits == 0
        assert metrics.avg_response_time_ms is None

    def test_channel_metrics_success_rate_property(self, db_session):
        """success_rate property calculates correctly."""
        channel = ExternalChannel(
            agentium_id="CH00000012",  # Required
            name="Rate Test Channel",
            channel_type=ChannelType.SLACK,
        )
        db_session.add(channel)
        db_session.commit()

        # No requests yet
        metrics = ChannelMetrics(
            agentium_id="CM00000003",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel.id
        )
        db_session.add(metrics)
        db_session.commit()
        assert metrics.success_rate == 100.0

        # Some requests
        metrics.total_requests = 200
        metrics.successful_requests = 180
        metrics.failed_requests = 20
        db_session.commit()
        assert metrics.success_rate == 90.0

        # All successful
        metrics.total_requests = 50
        metrics.successful_requests = 50
        metrics.failed_requests = 0
        db_session.commit()
        assert metrics.success_rate == 100.0

        # All failed
        metrics.total_requests = 10
        metrics.successful_requests = 0
        metrics.failed_requests = 10
        db_session.commit()
        assert metrics.success_rate == 0.0

    def test_channel_metrics_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        channel = ExternalChannel(
            agentium_id="CH00000013",  # Required
            name="Dict Test Channel",
            channel_type=ChannelType.TELEGRAM,
        )
        db_session.add(channel)
        db_session.commit()

        metrics = ChannelMetrics(
            agentium_id="CM00000004",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel.id,
            total_requests=50,
            successful_requests=48,
            failed_requests=2,
            circuit_breaker_state=CircuitBreakerState.HALF_OPEN,
            consecutive_failures=1,
            rate_limit_hits=0,
            avg_response_time_ms=200,
        )
        db_session.add(metrics)
        db_session.commit()

        data = metrics.to_dict()
        assert data["channel_id"] == channel.id
        assert data["total_requests"] == 50
        assert data["successful_requests"] == 48
        assert data["failed_requests"] == 2
        assert data["success_rate"] == 96.0
        assert data["circuit_breaker_state"] == "half_open"
        assert data["consecutive_failures"] == 1
        assert data["rate_limit_hits"] == 0
        assert data["avg_response_time_ms"] == 200


class TestChannelIntegration:
    """Integration tests for channel workflows."""

    def test_channel_with_messages_and_metrics(self, db_session):
        """Full workflow: channel, messages, and metrics linked together."""
        # Create channel
        channel = ExternalChannel(
            agentium_id="CH00000014",  # Required
            name="Integration WhatsApp",
            channel_type=ChannelType.WHATSAPP,
            config={"phone_number": "+15550001111"},
        )
        db_session.add(channel)
        db_session.commit()
        db_session.refresh(channel)

        # Create metrics
        metrics = ChannelMetrics(
            agentium_id="CM00000005",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel.id
        )
        db_session.add(metrics)
        db_session.commit()

        # Receive messages
        msg1 = ExternalMessage(
            channel_id=channel.id,
            sender_id="+15551234567",
            content="First message",
        )
        msg2 = ExternalMessage(
            channel_id=channel.id,
            sender_id="+15557654321",
            content="Second message",
        )
        db_session.add_all([msg1, msg2])
        db_session.commit()

        # Verify relationships
        assert len(channel.messages) == 2  # Using backref
        # Query metrics directly since backref returns list
        from sqlalchemy import select
        retrieved_metrics = db_session.scalar(select(ChannelMetrics).where(ChannelMetrics.channel_id == channel.id))
        assert retrieved_metrics is not None
        assert retrieved_metrics.channel_id == channel.id

        # Simulate processing
        msg1.mark_processing("agent-1")
        retrieved_metrics.total_requests += 1
        retrieved_metrics.successful_requests += 1
        db_session.commit()

        msg1.mark_responded("Response to first", "agent-1")
        retrieved_metrics.total_requests += 1
        retrieved_metrics.successful_requests += 1
        db_session.commit()

        # Verify stats updated
        assert channel.messages_received == 0  # Not auto-incremented by model
        assert channel.messages_sent == 1  # Incremented by mark_responded
        assert retrieved_metrics.total_requests == 2
        assert retrieved_metrics.success_rate == 100.0

    def test_multiple_channels_independent_metrics(self, db_session):
        """Each channel has its own independent metrics."""
        channel1 = ExternalChannel(agentium_id="CH00000015", name="WhatsApp 1", channel_type=ChannelType.WHATSAPP)
        channel2 = ExternalChannel(agentium_id="CH00000016", name="Slack 1", channel_type=ChannelType.SLACK)
        db_session.add_all([channel1, channel2])
        db_session.commit()

        metrics1 = ChannelMetrics(
            agentium_id="CM00000006",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel1.id, total_requests=100)
        metrics2 = ChannelMetrics(
            agentium_id="CM00000007",  # Required - ChannelMetrics doesn't auto-generate
            channel_id=channel2.id, total_requests=50)
        db_session.add_all([metrics1, metrics2])
        db_session.commit()

        assert metrics1.total_requests == 100
        assert metrics2.total_requests == 50
        assert metrics1.channel_id != metrics2.channel_id