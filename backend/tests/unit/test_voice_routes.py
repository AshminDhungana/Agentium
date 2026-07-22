"""
Unit tests for voice configuration API endpoints.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.routes.voice import (
    get_voice_configuration,
    update_voice_configuration,
    get_voice_configuration_status,
    list_tts_providers,
    VoiceConfigUpdateRequest
)
from backend.models.entities.user import User
from backend.models.entities.voice_config import VoiceConfig
from backend.core.exceptions import NotFoundError, ConflictError


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_user():
    return {
        "sub": "test-user-id",
        "email": "test@example.com",
        "is_admin": False
    }


@pytest.fixture
def mock_voice_config():
    config = MagicMock(spec=VoiceConfig)
    config.user_id = "test-user-id"
    config.require_wake_word = True
    config.tts_voice = "am_adam"
    config.tts_provider = "kokoro"
    config.proactive_enabled = False
    config.speaker_identification = False
    config.created_at = None
    config.updated_at = None
    return config


@pytest.fixture
def mock_audio_service():
    service = MagicMock()
    service.get_status.return_value = {
        "kokoro_available": True,
        "openai_available": True,
        "tts_provider": "kokoro",
        "current_voice": "am_adam"
    }
    service.get_available_voices.return_value = {
        "kokoro": [{"id": "am_adam", "name": "Adam"}],
        "openai": [{"id": "alloy", "name": "Alloy"}]
    }
    return service


async def test_get_voice_configuration_success(mock_db, mock_user, mock_voice_config):
    """Test successful retrieval of voice configuration."""
    with patch('backend.services.voice.voice_config_service.VoiceConfigService.get_or_create_default') as mock_get:
        mock_get.return_value = mock_voice_config
        
        with patch('backend.services.voice.voice_config_service.VoiceConfigService.to_dict') as mock_to_dict:
            mock_to_dict.return_value = {
                "user_id": "test-user-id",
                "require_wake_word": True,
                "tts_voice": "am_adam",
                "tts_provider": "kokoro",
                "proactive_enabled": False,
                "speaker_identification": False
            }
            
            result = await get_voice_configuration(mock_db, mock_user)
            
            assert result == mock_to_dict.return_value
            mock_get.assert_called_once_with(mock_db, "test-user-id")


async def test_update_voice_configuration_success(mock_db, mock_user, mock_voice_config):
    """Test successful update of voice configuration."""
    update_data = VoiceConfigUpdateRequest(
        tts_provider="openai",
        tts_voice="alloy"
    )
    
    with patch('backend.services.voice.voice_config_service.VoiceConfigService.update') as mock_update:
        mock_update.return_value = mock_voice_config
        
        with patch('backend.services.voice.voice_config_service.VoiceConfigService.to_dict') as mock_to_dict:
            mock_to_dict.return_value = {
                "user_id": "test-user-id",
                "require_wake_word": True,
                "tts_voice": "alloy",
                "tts_provider": "openai",
                "proactive_enabled": False,
                "speaker_identification": False
            }
            
            result = await update_voice_configuration(update_data, mock_db, mock_user)
            
            assert result == mock_to_dict.return_value
            mock_update.assert_called_once_with(
                db=mock_db,
                user_id="test-user-id",
                require_wake_word=None,
                tts_voice="alloy",
                tts_provider="openai",
                proactive_enabled=None,
                speaker_identification=None
            )


async def test_update_voice_configuration_invalid_provider(mock_db, mock_user):
    """Test update with invalid provider."""
    update_data = VoiceConfigUpdateRequest(
        tts_provider="invalid"
    )
    
    with patch('backend.services.voice.voice_config_service.VoiceConfigService.update') as mock_update:
        mock_update.side_effect = ValueError("Invalid TTS provider")
        
        with pytest.raises(ValueError) as exc_info:
            await update_voice_configuration(update_data, mock_db, mock_user)
        
            assert "Invalid TTS provider" in str(exc_info.value)


async def test_get_voice_configuration_status(mock_db, mock_user, mock_voice_config, mock_audio_service):
    """Test getting voice configuration status."""
    with patch('backend.services.voice.voice_config_service.VoiceConfigService.get_or_create_default') as mock_get_config:
            mock_get_config.return_value = mock_voice_config
    
            with patch('backend.services.voice.voice_config_service.VoiceConfigService.to_dict') as mock_to_dict:
                mock_to_dict.return_value = {
                    "user_id": "test-user-id",
                    "tts_provider": "kokoro"
                }
                
                with patch('backend.services.audio_service.AudioService') as mock_audio_class:
                    mock_audio_class.return_value = mock_audio_service
                
                result = await get_voice_configuration_status(mock_db, mock_user)
                
                assert "kokoro_available" in result
                assert "current_config" in result
                # The result should use the mock_to_dict return value
                assert result["current_config"]["tts_provider"] == "kokoro"


async def test_list_tts_providers(mock_db, mock_user, mock_audio_service):
    """Test listing TTS providers."""
    with patch('backend.services.audio_service.AudioService') as mock_audio_class:
            mock_audio_class.return_value = mock_audio_service
            
            # Mock the audio service methods
            mock_audio_service._is_kokoro_available.return_value = True
            mock_audio_service._get_openai_api_key.return_value = "test-key"
            
            result = await list_tts_providers(mock_db, mock_user)
            
            assert "providers" in result
            assert "kokoro" in result["providers"]
            assert "openai" in result["providers"]
            assert result["providers"]["kokoro"]["available"] == True
            assert result["providers"]["openai"]["available"] == True