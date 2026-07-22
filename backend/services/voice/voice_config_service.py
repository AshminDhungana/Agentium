"""
Voice Configuration Service for managing user TTS preferences.
"""

from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
import logging

from backend.models.entities.voice_config import VoiceConfig
from backend.core.exceptions import NotFoundError, ConflictError

logger = logging.getLogger(__name__)


class VoiceConfigService:
    """
    Service for managing voice configuration preferences.
    
    Provides CRUD operations for VoiceConfig entities and handles
    default configuration for new users.
    """

    @staticmethod
    def get_by_user_id(db: Session, user_id: str) -> Optional[VoiceConfig]:
        """
        Get voice configuration for a specific user.
        
        Args:
            db: Database session
            user_id: User ID to look up
            
        Returns:
            VoiceConfig if found, None otherwise
        """
        return db.query(VoiceConfig).filter(VoiceConfig.user_id == user_id).first()

    @staticmethod
    def get_or_create_default(db: Session, user_id: str) -> VoiceConfig:
        """
        Get voice configuration for a user, or create a default one if not found.
        
        Args:
            db: Database session
            user_id: User ID to look up or create for
            
        Returns:
            VoiceConfig (existing or newly created)
        """
        config = VoiceConfigService.get_by_user_id(db, user_id)
        if config:
            return config
            
        # Create default configuration
        return VoiceConfigService.create(
            db=db,
            user_id=user_id,
            require_wake_word=True,
            tts_voice="am_adam",
            tts_provider="kokoro",
            proactive_enabled=False,
            speaker_identification=False
        )

    @staticmethod
    def create(
        db: Session,
        user_id: str,
        require_wake_word: bool = True,
        tts_voice: str = "am_adam",
        tts_provider: str = "kokoro",
        proactive_enabled: bool = False,
        speaker_identification: bool = False
    ) -> VoiceConfig:
        """
        Create a new voice configuration for a user.
        
        Args:
            db: Database session
            user_id: User ID
            require_wake_word: Whether wake word is required
            tts_voice: TTS voice to use
            tts_provider: TTS provider ("kokoro" or "openai")
            proactive_enabled: Whether proactive voice is enabled
            speaker_identification: Whether speaker identification is enabled
            
        Returns:
            Created VoiceConfig
            
        Raises:
            ConflictError: If a configuration already exists for this user
        """
        existing = VoiceConfigService.get_by_user_id(db, user_id)
        if existing:
            raise ConflictError(
                f"Voice configuration already exists for user {user_id}",
                code="VOICE_CONFIG_CONFLICT"
            )
            
        config = VoiceConfig(
            user_id=user_id,
            require_wake_word=require_wake_word,
            tts_voice=tts_voice,
            tts_provider=tts_provider,
            proactive_enabled=proactive_enabled,
            speaker_identification=speaker_identification
        )
        
        db.add(config)
        try:
            db.commit()
            db.refresh(config)
            logger.info(f"Created voice configuration for user {user_id}")
            return config
        except IntegrityError as e:
            db.rollback()
            logger.error(f"Failed to create voice configuration for user {user_id}: {e}")
            raise ConflictError(
                f"Voice configuration already exists for user {user_id}",
                code="VOICE_CONFIG_CONFLICT"
            )

    @staticmethod
    def update(
        db: Session,
        user_id: str,
        require_wake_word: Optional[bool] = None,
        tts_voice: Optional[str] = None,
        tts_provider: Optional[str] = None,
        proactive_enabled: Optional[bool] = None,
        speaker_identification: Optional[bool] = None
    ) -> VoiceConfig:
        """
        Update an existing voice configuration.
        
        Args:
            db: Database session
            user_id: User ID to update
            require_wake_word: New wake word requirement (optional)
            tts_voice: New TTS voice (optional)
            tts_provider: New TTS provider (optional)
            proactive_enabled: New proactive enabled setting (optional)
            speaker_identification: New speaker identification setting (optional)
            
        Returns:
            Updated VoiceConfig
            
        Raises:
            NotFoundError: If no configuration exists for this user
        """
        config = VoiceConfigService.get_by_user_id(db, user_id)
        if not config:
            raise NotFoundError(
                f"No voice configuration found for user {user_id}",
                code="VOICE_CONFIG_NOT_FOUND"
            )
            
        if require_wake_word is not None:
            config.require_wake_word = require_wake_word
            
        if tts_voice is not None:
            config.tts_voice = tts_voice
            
        if tts_provider is not None:
            # Validate provider
            if tts_provider not in ["kokoro", "openai"]:
                raise ValueError(f"Invalid TTS provider: {tts_provider}. Must be 'kokoro' or 'openai'")
            config.tts_provider = tts_provider
            
        if proactive_enabled is not None:
            config.proactive_enabled = proactive_enabled
            
        if speaker_identification is not None:
            config.speaker_identification = speaker_identification
            
        db.commit()
        db.refresh(config)
        logger.info(f"Updated voice configuration for user {user_id}")
        return config

    @staticmethod
    def to_dict(config: VoiceConfig) -> Dict[str, Any]:
        """
        Convert a VoiceConfig to a dictionary for API responses.
        
        Args:
            config: VoiceConfig to convert
            
        Returns:
            Dictionary representation of the configuration
        """
        return {
            "user_id": config.user_id,
            "require_wake_word": config.require_wake_word,
            "tts_voice": config.tts_voice,
            "tts_provider": config.tts_provider,
            "proactive_enabled": config.proactive_enabled,
            "speaker_identification": config.speaker_identification,
            "created_at": config.created_at.isoformat() if config.created_at else None,
            "updated_at": config.updated_at.isoformat() if config.updated_at else None
        }