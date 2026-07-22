"""
Unit tests for AudioService with multi-provider TTS support.
"""

import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from sqlalchemy.orm import Session

from backend.services.audio_service import AudioService
from backend.models.entities.voice_config import VoiceConfig
from backend.core.exceptions import ProviderUnavailableError


@pytest.fixture
def audio_service():
    return AudioService()


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_voice_config():
    config = MagicMock(spec=VoiceConfig)
    config.user_id = "test-user"
    config.tts_provider = "kokoro"
    config.tts_voice = "am_adam"
    config.require_wake_word = True
    config.proactive_enabled = False
    config.speaker_identification = False
    return config


@pytest.mark.asyncio
async def test_synthesize_with_kokoro_primary(audio_service, mock_db, mock_voice_config):
    """Test TTS synthesis with Kokoro as primary provider."""
    
    # Mock VoiceConfigService to return our test config
    with patch('backend.services.audio_service.VoiceConfigService.get_or_create_default') as mock_get_config:
        mock_get_config.return_value = mock_voice_config
        
        # Mock Kokoro to return test audio
        with patch.object(audio_service, '_synthesize_kokoro', new_callable=AsyncMock) as mock_kokoro:
            mock_kokoro.return_value = b"test-wav-data"
            
            # Mock OpenAI to ensure it's not called
            with patch.object(audio_service, '_synthesize_openai', new_callable=AsyncMock) as mock_openai:
                result = await audio_service.synthesize(
                    db=mock_db,
                    user_id="test-user",
                    text="Hello world"
                )
                
                # Should use Kokoro and return its result
                assert result == b"test-wav-data"
                mock_kokoro.assert_called_once()
                mock_openai.assert_not_called()


@pytest.mark.asyncio
async def test_synthesize_with_openai_primary(audio_service, mock_db, mock_voice_config):
    """Test TTS synthesis with OpenAI as primary provider."""
    
    # Set OpenAI as primary provider
    mock_voice_config.tts_provider = "openai"
    
    # Mock VoiceConfigService to return our test config
    with patch('backend.services.audio_service.VoiceConfigService.get_or_create_default') as mock_get_config:
        mock_get_config.return_value = mock_voice_config
        
        # Mock OpenAI to return test audio
        with patch.object(audio_service, '_synthesize_openai', new_callable=AsyncMock) as mock_openai:
            mock_openai.return_value = b"test-wav-data"
            
            # Mock Kokoro to ensure it's not called
            with patch.object(audio_service, '_synthesize_kokoro', new_callable=AsyncMock) as mock_kokoro:
                result = await audio_service.synthesize(
                    db=mock_db,
                    user_id="test-user",
                    text="Hello world"
                )
                
                # Should use OpenAI and return its result
                assert result == b"test-wav-data"
                mock_openai.assert_called_once()
                mock_kokoro.assert_not_called()


@pytest.mark.asyncio
async def test_synthesize_fallback_from_kokoro_to_openai(audio_service, mock_db, mock_voice_config):
    """Test TTS synthesis fallback from Kokoro to OpenAI."""
    
    # Mock VoiceConfigService to return our test config
    with patch('backend.services.audio_service.VoiceConfigService.get_or_create_default') as mock_get_config:
        mock_get_config.return_value = mock_voice_config
        
        # Mock Kokoro to fail
        with patch.object(audio_service, '_synthesize_kokoro', new_callable=AsyncMock) as mock_kokoro:
            mock_kokoro.side_effect = ProviderUnavailableError("Kokoro failed", code="KOKORO_FAILED")
            
            # Mock OpenAI to succeed
            with patch.object(audio_service, '_synthesize_openai', new_callable=AsyncMock) as mock_openai:
                mock_openai.return_value = b"test-wav-data"
                
                result = await audio_service.synthesize(
                    db=mock_db,
                    user_id="test-user",
                    text="Hello world"
                )
                
                # Should fallback to OpenAI and return its result
                assert result == b"test-wav-data"
                mock_kokoro.assert_called_once()
                mock_openai.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_fallback_from_openai_to_kokoro(audio_service, mock_db, mock_voice_config):
    """Test TTS synthesis fallback from OpenAI to Kokoro."""
    
    # Set OpenAI as primary provider
    mock_voice_config.tts_provider = "openai"
    
    # Mock VoiceConfigService to return our test config
    with patch('backend.services.audio_service.VoiceConfigService.get_or_create_default') as mock_get_config:
        mock_get_config.return_value = mock_voice_config
        
        # Mock OpenAI to fail
        with patch.object(audio_service, '_synthesize_openai', new_callable=AsyncMock) as mock_openai:
            mock_openai.side_effect = ProviderUnavailableError("OpenAI failed", code="OPENAI_FAILED")
            
            # Mock Kokoro to succeed
            with patch.object(audio_service, '_synthesize_kokoro', new_callable=AsyncMock) as mock_kokoro:
                mock_kokoro.return_value = b"test-wav-data"
                
                result = await audio_service.synthesize(
                    db=mock_db,
                    user_id="test-user",
                    text="Hello world"
                )
                
                # Should fallback to Kokoro and return its result
                assert result == b"test-wav-data"
                mock_openai.assert_called_once()
                mock_kokoro.assert_called_once()


@pytest.mark.asyncio
async def test_synthesize_no_providers_available(audio_service, mock_db, mock_voice_config):
    """Test TTS synthesis when no providers are available."""
    
    # Mock VoiceConfigService to return our test config
    with patch('backend.services.audio_service.VoiceConfigService.get_or_create_default') as mock_get_config:
        mock_get_config.return_value = mock_voice_config
        
        # Mock both providers to fail
        with patch.object(audio_service, '_synthesize_kokoro', new_callable=AsyncMock) as mock_kokoro:
            mock_kokoro.side_effect = ProviderUnavailableError("Kokoro failed", code="KOKORO_FAILED")
            
            with patch.object(audio_service, '_synthesize_openai', new_callable=AsyncMock) as mock_openai:
                mock_openai.side_effect = ProviderUnavailableError("OpenAI failed", code="OPENAI_FAILED")
                
                # Should raise ProviderUnavailableError
                with pytest.raises(ProviderUnavailableError) as exc_info:
                    await audio_service.synthesize(
                        db=mock_db,
                        user_id="test-user",
                        text="Hello world"
                    )
                
                assert exc_info.value.code == "OPENAI_FAILED"
                mock_kokoro.assert_called_once()
                mock_openai.assert_called_once()


def test_get_available_voices(audio_service):
    """Test getting available voices for different providers."""
    
    # Test getting all voices
    all_voices = audio_service.get_available_voices()
    assert "openai" in all_voices
    assert "kokoro" in all_voices
    assert len(all_voices["openai"]) == 6
    assert len(all_voices["kokoro"]) > 10
    
    # Test getting OpenAI voices
    openai_voices = audio_service.get_available_voices("openai")
    assert len(openai_voices) == 6
    assert openai_voices[0]["id"] == "alloy"
    
    # Test getting Kokoro voices
    kokoro_voices = audio_service.get_available_voices("kokoro")
    assert len(kokoro_voices) > 10
    assert kokoro_voices[0]["id"] == "am_adam"
    
    # Test getting voices for unknown provider
    unknown_voices = audio_service.get_available_voices("unknown")
    assert len(unknown_voices) == 0


def test_get_status(audio_service, mock_db):
    """Test getting audio service status."""
    
    # Mock VoiceConfigService
    mock_config = MagicMock(spec=VoiceConfig)
    mock_config.tts_provider = "kokoro"
    mock_config.tts_voice = "am_adam"
    mock_config.require_wake_word = True
    mock_config.proactive_enabled = False
    
    with patch('backend.services.audio_service.VoiceConfigService.get_or_create_default') as mock_get_config:
        mock_get_config.return_value = mock_config
        
        # Mock provider availability
        with patch.object(audio_service, '_is_kokoro_available') as mock_kokoro_avail:
            mock_kokoro_avail.return_value = True
            
            with patch.object(audio_service, '_get_openai_api_key') as mock_openai_key:
                mock_openai_key.return_value = "test-key"
                
                status = audio_service.get_status(mock_db, "test-user")
                
                # Check status fields
                assert status["tts_provider"] == "kokoro"
                assert status["current_voice"] == "am_adam"
                assert status["kokoro_available"] == True
                assert status["openai_available"] == True
                assert "voices" in status