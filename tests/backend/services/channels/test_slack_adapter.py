import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.channels.slack import SlackAdapter
from backend.models.entities.channels import ExternalMessage

@pytest.mark.asyncio
async def test_slack_adapter_send_message_success():
    # Arrange
    config = {"bot_token": "xoxb-test-token"}
    # Create a simple mock for the channel with config attribute
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = SlackAdapter(mock_channel)
    message = ExternalMessage(
        content="Test message",
        sender_id="C1234567890"
    )

    # Mock the HTTP client and response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_client):
        # Act
        result = await adapter.send_message(message)

        # Assert
        assert result == True

@pytest.mark.asyncio
async def test_slack_adapter_validate_config():
    # Arrange
    config = {"bot_token": "xoxb-test-token"}
    # Create a simple mock for the channel with config attribute
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = SlackAdapter(mock_channel)

    # Act & Assert
    assert await adapter.validate_config() == True

    # Test with invalid config
    mock_channel_invalid = MagicMock()
    mock_channel_invalid.config = {}
    adapter_invalid = SlackAdapter(mock_channel_invalid)
    assert await adapter_invalid.validate_config() == False