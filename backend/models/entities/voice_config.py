from sqlalchemy import Column, String, Boolean, Text, DateTime, func
from sqlalchemy.dialects.postgresql import UUID
import uuid
from models.entities.base import Base

class VoiceConfig(Base):
    """User voice configuration preferences."""
    
    __tablename__ = "voice_configs"
    __table_args__ = {'extend_existing': True}

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(String(255), unique=True, nullable=False, index=True)
    require_wake_word = Column(Boolean, default=True)
    tts_voice = Column(String(100), default="am_adam")  # CHANGED DEFAULT
    tts_provider = Column(String(50), default="kokoro")  # NEW FIELD
    proactive_enabled = Column(Boolean, default=False)
    speaker_identification = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())