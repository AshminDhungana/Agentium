import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.channels.telegram import TelegramAdapter
from backend.models.entities.channels import ExternalMessage

@pytest.mark.asyncio
async def test_telegram_adapter_send_message_success():
    # Arrange
    config = {"bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"}
    # Create a simple mock for the channel with config attribute
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = TelegramAdapter(mock_channel)
    message = ExternalMessage(
        content="Test message",
        sender_id="123456789"  # Telegram chat ID
    )

    # Mock the HTTP client and response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"ok": True, "result": {"message_id": 1}}

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
async def test_telegram_adapter_send_message_failure():
    # Arrange
    config = {"bot_token": "invalid-token"}
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = TelegramAdapter(mock_channel)
    message = ExternalMessage(
        content="Test message",
        sender_id="123456789"
    )

    # Mock the HTTP client and response for failure
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {"ok": False, "error_code": 401, "description": "Unauthorized"}

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_client):
        # Act
        result = await adapter.send_message(message)

        # Assert
        assert result == False

def test_telegram_adapter_validate_config():
    # Arrange
    config = {"bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"}
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = TelegramAdapter(mock_channel)

    # Act & Assert
    # Need to call the async method properly in a test
    import asyncio
    result = asyncio.run(adapter.validate_config())
    assert result == True

    # Test with invalid config
    mock_channel_invalid = MagicMock()
    mock_channel_invalid.config = {}
    adapter_invalid = TelegramAdapter(mock_channel_invalid)
    result_invalid = asyncio.run(adapter_invalid.validate_config())
    assert result_invalid == False