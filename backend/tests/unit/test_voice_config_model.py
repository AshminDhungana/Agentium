from backend.models.entities.voice_config import VoiceConfig
from sqlalchemy import inspect

def test_voice_config_model_structure():
    """Test VoiceConfig model structure and defaults."""
    # Test columns exist by checking the mapper
    mapper = inspect(VoiceConfig)
    columns = [col.name for col in mapper.columns]
    
    assert 'id' in columns
    assert 'user_id' in columns
    assert 'require_wake_word' in columns
    assert 'tts_voice' in columns
    assert 'tts_provider' in columns  # NEW FIELD
    assert 'proactive_enabled' in columns
    assert 'speaker_identification' in columns
    assert 'created_at' in columns
    assert 'updated_at' in columns
    
    # Test defaults
    assert VoiceConfig.tts_voice.default.arg == 'am_adam'
    assert VoiceConfig.tts_provider.default.arg == 'kokoro'  # NEW DEFAULT