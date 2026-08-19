"""
Integration tests for ExternalChannel and ExternalMessage models (3.3.9).
Verifies external channels, bridge messages, message state transitions, and channel metrics.
"""
import pytest
from datetime import datetime, timezone
from backend.models.entities.channels import (
    ExternalChannel, ExternalMessage, ChannelMetrics, ChannelType, ChannelStatus, CircuitBreakerState
)


def test_channel_all_types_persist(db_session):
    """Verify all 12 ChannelType enum values round-trip through the DB."""
    for idx, channel_type in enumerate(ChannelType):
        channel = ExternalChannel(
            agentium_id=f"CH00{idx:02d}",
            name=f"Channel {channel_type.value}",
            channel_type=channel_type,
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(channel)
    db_session.commit()

    for idx, channel_type in enumerate(ChannelType):
        fetched = db_session.query(ExternalChannel).filter_by(agentium_id=f"CH00{idx:02d}").first()
        assert fetched is not None
        assert fetched.channel_type == channel_type


def test_channel_status_lifecycle(db_session, sample_channel):
    """Verify ChannelStatus transitions: PENDING -> ACTIVE -> DISCONNECTED -> ARCHIVED."""
    assert sample_channel.status == ChannelStatus.PENDING

    # Transition to ACTIVE
    sample_channel.status = ChannelStatus.ACTIVE
    db_session.commit()
    fetched = db_session.query(ExternalChannel).filter_by(id=sample_channel.id).first()
    assert fetched.status == ChannelStatus.ACTIVE

    # Transition to DISCONNECTED
    sample_channel.status = ChannelStatus.DISCONNECTED
    db_session.commit()
    fetched = db_session.query(ExternalChannel).filter_by(id=sample_channel.id).first()
    assert fetched.status == ChannelStatus.DISCONNECTED

    # Transition to ARCHIVED
    sample_channel.status = ChannelStatus.ARCHIVED
    db_session.commit()
    fetched = db_session.query(ExternalChannel).filter_by(id=sample_channel.id).first()
    assert fetched.status == ChannelStatus.ARCHIVED


def test_channel_message_persist(db_session, sample_channel):
    """Verify ExternalMessage creation and persistence."""
    msg = ExternalMessage(
        agentium_id="EM99001",
        channel_id=sample_channel.id,
        sender_id="+19876543210",
        sender_name="Alice",
        message_type="text",
        content="Hello Agentium, please perform task X.",
        status="received",
    )
    db_session.add(msg)
    db_session.commit()

    fetched = db_session.query(ExternalMessage).filter_by(agentium_id="EM99001").first()
    assert fetched is not None
    assert fetched.channel_id == sample_channel.id
    assert fetched.sender_id == "+19876543210"
    assert fetched.sender_name == "Alice"
    assert fetched.content == "Hello Agentium, please perform task X."
    assert fetched.status == "received"

    d = fetched.to_dict()
    assert d["sender"]["id"] == "+19876543210"
    assert d["status"] == "received"


def test_channel_message_mark_processing(db_session, sample_channel, sample_task_agent):
    """Verify ExternalMessage.mark_processing updates status and assigned_agent_id."""
    msg = ExternalMessage(
        agentium_id="EM99002",
        channel_id=sample_channel.id,
        sender_id="+19876543210",
        content="Process me",
    )
    db_session.add(msg)
    db_session.commit()

    msg.mark_processing(sample_task_agent.id)
    db_session.commit()

    fetched = db_session.query(ExternalMessage).filter_by(id=msg.id).first()
    assert fetched.status == "processing"
    assert fetched.assigned_agent_id == sample_task_agent.id


def test_channel_message_mark_responded(db_session, sample_channel, sample_task_agent):
    """Verify ExternalMessage.mark_responded sets response, timestamp, and increments channel.messages_sent."""
    msg = ExternalMessage(
        agentium_id="EM99003",
        channel_id=sample_channel.id,
        sender_id="+19876543210",
        content="What is the status?",
    )
    db_session.add(msg)
    db_session.commit()

    initial_sent = sample_channel.messages_sent

    msg.mark_responded("Task is 100% complete.", sample_task_agent.id)
    db_session.commit()

    fetched = db_session.query(ExternalMessage).filter_by(id=msg.id).first()
    assert fetched.status == "responded"
    assert fetched.response_content == "Task is 100% complete."
    assert fetched.responded_at is not None
    assert fetched.responded_by_agent_id == sample_task_agent.id
    assert sample_channel.messages_sent == initial_sent + 1


def test_channel_metrics_success_rate(db_session, sample_channel):
    """Verify ChannelMetrics success_rate property calculation."""
    metrics = ChannelMetrics(
        agentium_id="CM99001",
        channel_id=sample_channel.id,
        total_requests=10,
        successful_requests=8,
        failed_requests=2,
        circuit_breaker_state=CircuitBreakerState.CLOSED,
    )
    db_session.add(metrics)
    db_session.commit()

    fetched = db_session.query(ChannelMetrics).filter_by(channel_id=sample_channel.id).first()
    assert fetched is not None
    assert fetched.success_rate == 80.0

    d = fetched.to_dict()
    assert d["success_rate"] == 80.0
    assert d["circuit_breaker_state"] == "closed"


def test_channel_webhook_url_generation(sample_channel):
    """Verify generate_webhook_url method."""
    sample_channel.webhook_path = "whatsapp-webhook-path-123"
    base_url = "https://agentium.ai"
    url = sample_channel.generate_webhook_url(base_url)
    assert url == "https://agentium.ai/webhooks/whatsapp/whatsapp-webhook-path-123"
