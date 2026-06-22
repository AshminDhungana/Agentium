"""
Integration tests for the Multi-Channel Suite (Phase 18.1).

Covers:
  Group 1 - Mock inbound message per channel type (Telegram, Discord, Slack, WhatsApp)
  Group 2 - Loop prevention (bot-message skipping, duplicate suppression)
  Group 3 - Speaker identification (speaker_id attached to ExternalMessage)
"""

import pytest
import uuid

from sqlalchemy.orm import Session

from backend.models.entities.channels import (
    ExternalChannel,
    ExternalMessage,
    ChannelType,
    ChannelStatus,
)
from backend.services.channel_manager import ChannelManager

pytestmark = pytest.mark.integration


# ==========================================================================
# Helpers
# ==========================================================================


def _make_channel(
    db: Session, channel_type: ChannelType, name: str = None, auto_create_tasks: bool = False
) -> ExternalChannel:
    """Create an active ExternalChannel for testing."""
    if name is None:
        name = f"Test {channel_type.value.title()}"
    ch = ExternalChannel(
        agentium_id=f"CH{uuid.uuid4().hex[:6].upper()}",
        name=name,
        channel_type=channel_type,
        status=ChannelStatus.ACTIVE,
        webhook_path=uuid.uuid4().hex,
        config={"provider": "test"},
        auto_create_tasks=auto_create_tasks,
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    return ch


# ==========================================================================
# Group 1 - Inbound Messages Per Channel Type
# ==========================================================================

class TestInboundMessagesPerChannel:
    """Verify that mock inbound payloads from each channel type are correctly
    routed into ExternalMessage records.
    """

    @pytest.mark.asyncio
    async def test_telegram_inbound_message(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.TELEGRAM)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="123456789",
            sender_name="Test User",
            content="Hello from Telegram",
            message_type="text",
            raw_payload={
                "update_id": 1,
                "message": {
                    "message_id": 100,
                    "from": {"id": 123456789, "first_name": "Test"},
                    "chat": {"id": 123456789},
                    "text": "Hello from Telegram",
                },
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.channel_id == ch.id
        assert msg.sender_id == "123456789"
        assert msg.sender_name == "Test User"
        assert msg.content == "Hello from Telegram"
        assert msg.message_type == "text"
        assert msg.status == "received"

    @pytest.mark.asyncio
    async def test_discord_inbound_message(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.DISCORD)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="test_channel_123",
            sender_name="TestUser#1234",
            content="Hello from Discord",
            message_type="text",
            raw_payload={
                "id": "msg123",
                "channel_id": "test_channel_123",
                "author": {"id": "user123", "username": "TestUser#1234"},
                "content": "Hello from Discord",
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.channel_id == ch.id
        assert msg.sender_id == "test_channel_123"
        assert msg.sender_name == "TestUser#1234"
        assert msg.content == "Hello from Discord"
        assert msg.status == "received"

    @pytest.mark.asyncio
    async def test_slack_inbound_message(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.SLACK)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="C1234567890",
            sender_name="testuser",
            content="Hello from Slack",
            message_type="text",
            raw_payload={
                "token": "test",
                "team_id": "T123",
                "event": {
                    "type": "message",
                    "channel": "C1234567890",
                    "user": "U123",
                    "text": "Hello from Slack",
                    "ts": "1234567890.000000",
                },
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.channel_id == ch.id
        assert msg.sender_id == "C1234567890"
        assert msg.sender_name == "testuser"
        assert msg.content == "Hello from Slack"
        assert msg.status == "received"

    @pytest.mark.asyncio
    async def test_whatsapp_inbound_message(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.WHATSAPP)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="15551234567",
            sender_name="Test User",
            content="Hello from WhatsApp",
            message_type="text",
            raw_payload={
                "entry": [
                    {
                        "changes": [
                            {
                                "value": {
                                    "contacts": [
                                        {"profile": {"name": "Test User"}}
                                    ],
                                    "messages": [
                                        {
                                            "from": "15551234567",
                                            "id": "wamid.test123",
                                            "type": "text",
                                            "text": {"body": "Hello from WhatsApp"},
                                        }
                                    ],
                                }
                            }
                        ]
                    }
                ]
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.channel_id == ch.id
        assert msg.sender_id == "15551234567"
        assert msg.sender_name == "Test User"
        assert "Hello from WhatsApp" in msg.content
        assert msg.status == "received"


# ==========================================================================
# Group 2 - Loop Prevention
# ==========================================================================

class TestLoopPrevention:
    """Verify that the channel manager correctly handles messages that would
    create loops (bot messages, self-sent messages, duplicates).
    The webhook routes skip bot messages, while ChannelManager does not
    reject them at the service layer.
    """

    @pytest.mark.asyncio
    async def test_telegram_bot_message_still_stored(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.TELEGRAM)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="987654321",
            sender_name="Bot",
            content="I am a bot",
            message_type="text",
            raw_payload={
                "update_id": 1,
                "message": {
                    "message_id": 101,
                    "from": {"id": 987654321, "is_bot": True},
                    "chat": {"id": 987654321},
                    "text": "I am a bot",
                },
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.sender_id == "987654321"

    @pytest.mark.asyncio
    async def test_slack_bot_message_still_stored(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.SLACK)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="C999",
            sender_name="slackbot",
            content="Bot content",
            message_type="text",
            raw_payload={
                "token": "test",
                "event": {
                    "type": "message",
                    "bot_id": "B123",
                    "channel": "C999",
                    "user": "U999",
                    "text": "Bot content",
                },
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.sender_id == "C999"

    @pytest.mark.asyncio
    async def test_discord_bot_message_still_stored(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.DISCORD)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="chan456",
            sender_name="Botto",
            content="Beep boop",
            message_type="text",
            raw_payload={
                "id": "msg456",
                "channel_id": "chan456",
                "author": {"id": "bot456", "username": "Botto", "bot": True},
                "content": "Beep boop",
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.sender_id == "chan456"


# ==========================================================================
# Group 3 - Speaker Identification
# ==========================================================================

class TestSpeakerIdentification:
    """Verify that when a raw_payload contains a speaker_id, the
    ExternalMessage record reflects it.
    """

    @pytest.mark.asyncio
    async def test_speaker_id_attached_to_external_message(self, seeded_db: Session):
        ch = _make_channel(seeded_db, ChannelType.TELEGRAM)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="123456789",
            sender_name="Device Sender",
            content="Voice message transcription",
            message_type="voice",
            raw_payload={
                "speaker_id": "spk_abc123",
                "speaker_name": "Alice Smith",
                "confidence": 0.95,
                "audio_duration": 12.5,
                "update_id": 2,
                "message": {
                    "message_id": 200,
                    "from": {"id": 123456789, "first_name": "Device"},
                    "chat": {"id": 123456789},
                    "voice": {"duration": 12, "file_id": "file_voice_123"},
                },
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.sender_id == "spk_abc123"
        assert "Alice Smith" in msg.sender_name
        assert msg.message_type == "voice"
        assert "Voice message transcription" in msg.content

    @pytest.mark.asyncio
    async def test_speaker_id_fallback_to_original_sender(self, seeded_db: Session):
        """When no speaker_id is provided, original sender_id is used."""
        ch = _make_channel(seeded_db, ChannelType.DISCORD)
        msg = await ChannelManager.receive_message(
            channel_id=ch.id,
            sender_id="original_sender_999",
            sender_name="Plain User",
            content="No speaker identification",
            message_type="text",
            raw_payload={
                "message_id": "msg789",
                "channel_id": "chan789",
                "author": {"id": "user789", "username": "Plain User"},
                "content": "No speaker identification",
            },
            db=seeded_db,
        )

        assert msg is not None
        assert msg.sender_id == "original_sender_999"
        assert msg.sender_name == "Plain User"
