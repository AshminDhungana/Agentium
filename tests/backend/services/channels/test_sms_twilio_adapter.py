import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.channels.sms_twilio import SMSAdapter
from backend.models.entities.channels import ExternalMessage

@pytest.mark.asyncio
async def test_sms_adapter_send_message_success():
    # Arrange
    config = {
        "account_sid": "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "auth_token": "your_auth_token",
        "from_number": "+15017122661"
    }
    # Create a simple mock for the channel with config attribute
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = SMSAdapter(mock_channel)
    message = ExternalMessage(
        content="Test SMS message",
        sender_id="+15017122662",  # Recipient phone number
    )

    # Mock the HTTP client and response for success
    mock_response = MagicMock()
    mock_response.status_code = 201  # Twilio success status
    mock_response.json.return_value = {
        "sid": "SMXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "date_created": "Thu, 19 Aug 2021 00:00:00 +0000",
        "date_updated": "Thu, 19 Aug 2021 00:00:00 +0000",
        "date_sent": "Thu, 19 Aug 2021 00:00:00 +0000",
        "account_sid": "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "to": "+15017122662",
        "from": "+15017122661",
        "body": "Test SMS message",
        "status": "queued",
        "num_segments": "1",
        "num_media": "0",
        "direction": "outbound-api",
        "api_version": "2010-04-01",
        "price": "-0.0075",
        "price_unit": "USD",
        "error_code": None,
        "error_message": None
    }

    mock_client = AsyncMock()
    mock_client.__aenter__.return_value = mock_client
    mock_client.__aexit__.return_value = None
    mock_client.post.return_value = mock_response

    with patch('httpx.AsyncClient', return_value=mock_client):
        # Act
        result = await adapter.send_message(message)

        # Assert
        assert result == True
        mock_client.post.assert_called_once()

@pytest.mark.asyncio
async def test_sms_adapter_send_message_failure():
    # Arrange
    config = {
        "account_sid": "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "auth_token": "invalid_token",
        "from_number": "+15017122661"
    }
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = SMSAdapter(mock_channel)
    message = ExternalMessage(
        content="Test SMS message",
        sender_id="+15017122662",
    )

    # Mock the HTTP client and response for failure
    mock_response = MagicMock()
    mock_response.status_code = 401
    mock_response.json.return_value = {
        "message": "Authentication Error - Invalid username/password",
        "code": 401,
        "more_info": "https://www.twilio.com/docs/errors/401",
        "status": 401
    }

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
async def test_sms_adapter_validate_config():
    # Arrange
    config = {
        "account_sid": "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "auth_token": "your_auth_token",
        "from_number": "+15017122661"
    }
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = SMSAdapter(mock_channel)

    # Act & Assert
    assert await adapter.validate_config() == True

    # Test with missing account_sid
    mock_channel_invalid1 = MagicMock()
    mock_channel_invalid1.config = {
        "auth_token": "your_auth_token",
        "from_number": "+15017122661"
    }
    adapter_invalid1 = SMSAdapter(mock_channel_invalid1)
    assert await adapter_invalid1.validate_config() == False

    # Test with missing auth_token
    mock_channel_invalid2 = MagicMock()
    mock_channel_invalid2.config = {
        "account_sid": "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "from_number": "+15017122661"
    }
    adapter_invalid2 = SMSAdapter(mock_channel_invalid2)
    assert await adapter_invalid2.validate_config() == False

    # Test with missing from_number
    mock_channel_invalid3 = MagicMock()
    mock_channel_invalid3.config = {
        "account_sid": "ACXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "auth_token": "your_auth_token"
    }
    adapter_invalid3 = SMSAdapter(mock_channel_invalid3)
    assert await adapter_invalid3.validate_config() == False

    # Test with empty config
    mock_channel_invalid4 = MagicMock()
    mock_channel_invalid4.config = {}
    adapter_invalid4 = SMSAdapter(mock_channel_invalid4)
    assert await adapter_invalid4.validate_config() == False