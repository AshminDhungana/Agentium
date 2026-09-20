import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.channels.slack import SlackAdapter
from backend.models.entities.channels import ExternalChannel, ChannelType, ChannelStatus


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
    return channel


@pytest.fixture
def slack_adapter(slack_channel):
    """Create a SlackAdapter instance."""
    return SlackAdapter(slack_channel)


@pytest.mark.asyncio
async def test_slack_adapter_validate_config_valid(slack_adapter):
    """Test validate_config returns True when bot_token is present."""
    assert await slack_adapter.validate_config() is True


@pytest.mark.asyncio
async def test_slack_adapter_validate_config_missing_token(slack_channel):
    """Test validate_config returns False when bot_token is missing."""
    slack_channel.config = {}
    adapter = SlackAdapter(slack_channel)
    assert await adapter.validate_config() is False


@pytest.mark.asyncio
async def test_slack_adapter_send_message_success(slack_adapter):
    """Test send_message returns True when Slack API returns success."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await slack_adapter.send_message(
            MagicMock(content="Test message", sender_id="C123456")
        )
        assert result is True

        # Verify the request was made correctly
        mock_client.__aenter__.return_value.post.assert_called_once()
        args, kwargs = mock_client.__aenter__.return_value.post.call_args
        assert args[0] == "https://slack.com/api/chat.postMessage"
        assert kwargs["json"]["channel"] == "C123456"
        assert kwargs["json"]["text"] == "Test message"
        assert kwargs["headers"]["Authorization"] == "Bearer xoxb-test-token"


@pytest.mark.asyncio
async def test_slack_adapter_send_message_api_error(slack_adapter):
    """Test send_message returns False when Slack API returns error."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": False, "error": "invalid_auth"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await slack_adapter.send_message(
            MagicMock(content="Test message", sender_id="C123456")
        )
        assert result is False


@pytest.mark.asyncio
async def test_slack_adapter_send_message_http_error(slack_adapter):
    """Test send_message returns False when Slack API returns HTTP error."""
    mock_response = MagicMock()
    mock_response.status_code = 400

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.return_value = mock_response

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await slack_adapter.send_message(
            MagicMock(content="Test message", sender_id="C123456")
        )
        assert result is False


@pytest.mark.asyncio
async def test_slack_adapter_send_message_exception(slack_adapter):
    """Test send_message returns False when an exception occurs."""
    mock_client = AsyncMock()
    mock_client.__aenter__.return_value.post.side_effect = Exception("Network error")

    with patch("httpx.AsyncClient", return_value=mock_client):
        result = await slack_adapter.send_message(
            MagicMock(content="Test message", sender_id="C123456")
        )
        assert result is False