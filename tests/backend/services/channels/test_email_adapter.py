import pytest
from unittest.mock import patch, MagicMock
from backend.services.channels.email import EmailAdapter
from backend.models.entities.channels import ExternalMessage

@pytest.mark.asyncio
async def test_email_adapter_send_message_success():
    # Arrange
    config = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "test@example.com",
        "smtp_pass": "test_password",
        "from_email": "noreply@example.com"
    }
    # Create a simple mock for the channel with config attribute
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = EmailAdapter(mock_channel)
    message = ExternalMessage(
        content="Test email message",
        sender_id="recipient@example.com",  # Recipient email address
    )

    # Mock the SMTP server
    mock_smtp_instance = MagicMock()
    with patch('smtplib.SMTP') as mock_smtp:
        mock_smtp.return_value = mock_smtp_instance

        # Act
        result = await adapter.send_message(message)

        # Assert
        assert result == True
        mock_smtp.assert_called_once_with("smtp.example.com", 587)
        mock_smtp_instance.starttls.assert_called_once()
        mock_smtp_instance.login.assert_called_once_with("test@example.com", "test_password")
        mock_smtp_instance.sendmail.assert_called_once()
        mock_smtp_instance.quit.assert_called_once()

@pytest.mark.asyncio
async def test_email_adapter_validate_config():
    # Arrange
    config = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_user": "test@example.com",
        "smtp_pass": "test_password",
        "from_email": "noreply@example.com"
    }
    mock_channel = MagicMock()
    mock_channel.config = config
    adapter = EmailAdapter(mock_channel)

    # Act & Assert
    assert await adapter.validate_config() == True

    # Test with missing smtp_host
    mock_channel_invalid1 = MagicMock()
    mock_channel_invalid1.config = {
        "smtp_port": 587,
        "smtp_user": "test@example.com",
        "smtp_pass": "test_password",
        "from_email": "noreply@example.com"
    }
    adapter_invalid1 = EmailAdapter(mock_channel_invalid1)
    assert await adapter_invalid1.validate_config() == False

    # Test with missing smtp_user
    mock_channel_invalid2 = MagicMock()
    mock_channel_invalid2.config = {
        "smtp_host": "smtp.example.com",
        "smtp_port": 587,
        "smtp_pass": "test_password",
        "from_email": "noreply@example.com"
    }
    adapter_invalid2 = EmailAdapter(mock_channel_invalid2)
    assert await adapter_invalid2.validate_config() == False

    # Test with empty config
    mock_channel_invalid3 = MagicMock()
    mock_channel_invalid3.config = {}
    adapter_invalid3 = EmailAdapter(mock_channel_invalid3)
    assert await adapter_invalid3.validate_config() == False