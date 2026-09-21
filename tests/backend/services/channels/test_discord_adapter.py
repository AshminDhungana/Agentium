import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.channels.discord import DiscordAdapter
from backend.models.entities.channels import ExternalMessage

@pytest.mark.asyncio
async def test_discord_adapter_send_message_success():
    # Arrange
    config = {
        "bot_token": "MjM4NTY5NjczMTQ4NDQwMAAA.test_token",
        "application_id": "123456789012345678"
    }
    # Create a simple mock for the channel with config attribute
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = DiscordAdapter(mock_channel)
    message = ExternalMessage(
        content="Test message",
        sender_id="123456789012345678",  # Discord channel ID
    )

    # Mock the HTTP client and response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"id": "123456789012345678901234567890", "content": "Test message"}

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
async def test_discord_adapter_send_message_failure():
    # Arrange
    config = {
        "bot_token": "invalid-token",
        "application_id": "123456789012345678"
    }
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = DiscordAdapter(mock_channel)
    message = ExternalMessage(
        content="Test message",
        sender_id="123456789012345678",
    )

    # Mock the HTTP client and response for failure
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"message": "401: Unrecognized token provided", "code": 0}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_client):
        # Act
        result = await adapter.send_message(message)

        # Assert
        assert result == False

@pytest.mark.asyncio
async def test_discord_adapter_validate_config():
    # Arrange
    config = {
        "bot_token": "MjM4NTY5NjczMTQ4NDQwMAAA.test_token",
        "application_id": "123456789012345678"
    }
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = DiscordAdapter(mock_channel)

    # Act & Assert
    assert await adapter.validate_config() == True

    # Test with missing bot_token
    mock_channel_invalid1 = MagicMock()
    mock_channel_invalid1.config = {"application_id": "123456789012345678"}
    adapter_invalid1 = DiscordAdapter(mock_channel_invalid1)
    assert await adapter_invalid1.validate_config() == False

    # Test with missing application_id
    mock_channel_invalid2 = MagicMock()
    mock_channel_invalid2.config = {"bot_token": "MjM4NTY5NjczMTQ4NDQwMAAA.test_token"}
    adapter_invalid2 = DiscordAdapter(mock_channel_invalid2)
    assert await adapter_invalid2.validate_config() == False

    # Test with empty config
    mock_channel_invalid3 = MagicMock()
    mock_channel_invalid3.config = {}
    adapter_invalid3 = DiscordAdapter(mock_channel_invalid3)
    assert await adapter_invalid3.validate_config() == False