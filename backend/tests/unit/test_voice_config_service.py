"""
Unit tests for VoiceConfigService.
"""

import pytest
from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from backend.services.voice.voice_config_service import VoiceConfigService
from backend.models.entities.voice_config import VoiceConfig
from backend.core.exceptions import NotFoundError, ConflictError


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


@pytest.fixture
def mock_voice_config():
    config = MagicMock(spec=VoiceConfig)
    config.user_id = "test-user"
    config.require_wake_word = True
    config.tts_voice = "am_adam"
    config.tts_provider = "kokoro"
    config.proactive_enabled = False
    config.speaker_identification = False
    config.created_at = None
    config.updated_at = None
    return config


def test_get_by_user_id_found(mock_db, mock_voice_config):
    """Test getting voice config by user ID when config exists."""
    mock_db.query.return_value.filter.return_value.first.return_value = mock_voice_config
    
    result = VoiceConfigService.get_by_user_id(mock_db, "test-user")
    
    assert result == mock_voice_config
    mock_db.query.return_value.filter.return_value.first.assert_called_once()


def test_get_by_user_id_not_found(mock_db):
    """Test getting voice config by user ID when config doesn't exist."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    result = VoiceConfigService.get_by_user_id(mock_db, "test-user")
    
    assert result is None


def test_get_or_create_default_existing(mock_db, mock_voice_config):
    """Test get_or_create_default when config already exists."""
    mock_db.query.return_value.filter.return_value.first.return_value = mock_voice_config
    
    result = VoiceConfigService.get_or_create_default(mock_db, "test-user")
    
    assert result == mock_voice_config
    mock_db.query.return_value.filter.return_value.first.assert_called_once()
    mock_db.add.assert_not_called()
    mock_db.commit.assert_not_called()


def test_get_or_create_default_new(mock_db):
    """Test get_or_create_default when creating a new config."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    # Mock the create method
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(VoiceConfigService, 'create', MagicMock(return_value=MagicMock(spec=VoiceConfig)))
        
        result = VoiceConfigService.get_or_create_default(mock_db, "test-user")
        
        VoiceConfigService.create.assert_called_once_with(
            db=mock_db,
            user_id="test-user",
            require_wake_word=True,
            tts_voice="am_adam",
            tts_provider="kokoro",
            proactive_enabled=False,
            speaker_identification=False
        )


def test_create_success(mock_db):
    """Test successful creation of voice config."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    # Create a real VoiceConfig instance for testing
    config = VoiceConfig(
        user_id="test-user",
        require_wake_word=True,
        tts_voice="am_adam",
        tts_provider="kokoro",
        proactive_enabled=False,
        speaker_identification=False
    )
    
    # Mock the db operations
    mock_db.add.return_value = None
    mock_db.commit.return_value = None
    mock_db.refresh.return_value = None
    
    result = VoiceConfigService.create(
        db=mock_db,
        user_id="test-user",
        require_wake_word=True,
        tts_voice="am_adam",
        tts_provider="kokoro",
        proactive_enabled=False,
        speaker_identification=False
    )
    
    assert result.user_id == "test-user"
    assert result.tts_provider == "kokoro"
    assert result.tts_voice == "am_adam"
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


def test_create_conflict(mock_db):
    """Test create when config already exists."""
    mock_db.query.return_value.filter.return_value.first.return_value = MagicMock(spec=VoiceConfig)
    
    with pytest.raises(ConflictError) as exc_info:
        VoiceConfigService.create(
            db=mock_db,
            user_id="test-user",
            require_wake_word=True,
            tts_voice="am_adam",
            tts_provider="kokoro",
            proactive_enabled=False,
            speaker_identification=False
        )
    
    assert "already exists" in str(exc_info.value)


def test_create_integrity_error(mock_db):
    """Test create when database integrity error occurs."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    mock_db.commit.side_effect = IntegrityError("test error", {}, None)
    
    with pytest.raises(ConflictError) as exc_info:
        VoiceConfigService.create(
            db=mock_db,
            user_id="test-user",
            require_wake_word=True,
            tts_voice="am_adam",
            tts_provider="kokoro",
            proactive_enabled=False,
            speaker_identification=False
        )
    
    assert "already exists" in str(exc_info.value)


def test_update_success(mock_db, mock_voice_config):
    """Test successful update of voice config."""
    mock_db.query.return_value.filter.return_value.first.return_value = mock_voice_config
    
    result = VoiceConfigService.update(
        db=mock_db,
        user_id="test-user",
        tts_provider="openai",
        tts_voice="nova"
    )
    
    assert result.tts_provider == "openai"
    assert result.tts_voice == "nova"
    mock_db.commit.assert_called_once()
    mock_db.refresh.assert_called_once_with(mock_voice_config)


def test_update_not_found(mock_db):
    """Test update when config doesn't exist."""
    mock_db.query.return_value.filter.return_value.first.return_value = None
    
    with pytest.raises(NotFoundError) as exc_info:
        VoiceConfigService.update(
            db=mock_db,
            user_id="test-user",
            tts_provider="openai"
        )
    
    assert "No voice configuration found" in str(exc_info.value)


def test_update_invalid_provider(mock_db, mock_voice_config):
    """Test update with invalid provider."""
    mock_db.query.return_value.filter.return_value.first.return_value = mock_voice_config
    
    with pytest.raises(ValueError) as exc_info:
        VoiceConfigService.update(
            db=mock_db,
            user_id="test-user",
            tts_provider="invalid"
        )
    
    assert "Invalid TTS provider" in str(exc_info.value)


def test_to_dict(mock_voice_config):
    """Test conversion of voice config to dictionary."""
    # Create proper datetime mocks
    mock_created_at = MagicMock()
    mock_created_at.isoformat.return_value = "2023-01-01T00:00:00"
    mock_voice_config.created_at = mock_created_at
    
    mock_updated_at = MagicMock()
    mock_updated_at.isoformat.return_value = "2023-01-01T01:00:00"
    mock_voice_config.updated_at = mock_updated_at
    
    result = VoiceConfigService.to_dict(mock_voice_config)
    
    assert result == {
        "user_id": "test-user",
        "require_wake_word": True,
        "tts_voice": "am_adam",
        "tts_provider": "kokoro",
        "proactive_enabled": False,
        "speaker_identification": False,
        "created_at": "2023-01-01T00:00:00",
        "updated_at": "2023-01-01T01:00:00"
    }