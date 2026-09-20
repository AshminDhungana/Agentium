import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.channel_manager import ChannelManager, SlackAdapter
from backend.models.entities.channels import ExternalChannel, ExternalMessage, ChannelType, ChannelStatus


@pytest.fixture
def slack_channel():
    """Create a mock Slack channel."""
    channel = MagicMock(spec=ExternalChannel)
    channel.id = "test-slack-id"
    channel.agentium_id = "CH0001"
    channel.name = "Test Slack"
    channel.channel_type = ChannelType.SLACK
    channel.status = ChannelStatus.ACTIVE
    channel.config = {"bot_token": "xoxb-test-token"}
    channel.messages_sent = 0
    channel.messages_received = 0
    return channel


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return MagicMock()


@pytest.mark.asyncio
async def test_channel_manager_sends_slack_message(slack_channel, mock_db):
    """Test that ChannelManager.send_response correctly sends a message via SlackAdapter."""
    # Create a mock ExternalMessage that has a channel relationship
    mock_message = MagicMock()
    mock_message.id = "test-msg-123"
    mock_message.channel = slack_channel  # Set the channel relationship
    mock_message.channel_id = slack_channel.id

    # Mock the database query to return our message when filtering by ID
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_message

    # Mock the SlackAdapter.send_message class method to return True (success)
    with patch("backend.services.channel_manager.SlackAdapter.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True

        # Make the mock message's mark_responded method increment the channel's messages_sent
        def mark_responded(content, agent_id):
            slack_channel.messages_sent += 1

        mock_message.mark_responded.side_effect = mark_responded

        # Call ChannelManager.send_response
        result = await ChannelManager.send_response(
            message_id="test-msg-123",
            response_content="Hello from Slack test",
            agent_id="agent-001",
            db=mock_db
        )

        # Verify the result
        assert result is True

        # Verify channel messages_sent was incremented
        assert slack_channel.messages_sent == 1


@pytest.mark.asyncio
async def test_channel_manager_slack_send_failure(slack_channel, mock_db):
    """Test that ChannelManager.send_response handles Slack send failure correctly."""
    # Create a mock ExternalMessage that has a channel relationship
    mock_message = MagicMock()
    mock_message.id = "test-msg-123"
    mock_message.channel = slack_channel  # Set the channel relationship
    mock_message.channel_id = slack_channel.id

    # Mock the database query to return our message when filtering by ID
    mock_db.query.return_value.filter_by.return_value.first.return_value = mock_message

    # Mock the SlackAdapter.send_message class method to return False (failure)
    with patch("backend.services.channel_manager.SlackAdapter.send_message", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = False

        # Make the mock message's mark_responded method do nothing (shouldn't be called on failure)
        mock_message.mark_responded.return_value = None

        # Call ChannelManager.send_response
        result = await ChannelManager.send_response(
            message_id="test-msg-123",
            response_content="Hello from Slack test",
            agent_id="agent-001",
            db=mock_db
        )

        # Verify the result is False
        assert result is False

        # Verify channel messages_sent was NOT incremented (since send failed)
        assert slack_channel.messages_sent == 0