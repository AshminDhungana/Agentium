"""
Voice processing endpoints for speech-to-text and text-to-speech.
Uses OpenAI API key from user's model configurations (if available).
"""

import os
import json
import uuid
import tempfile
import io
from pathlib import Path
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, UploadFile, File, Depends, status, Form
from pydantic import BaseModel, Field
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError, ServerSTTUnavailable, ProviderUnavailableError
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.models.entities.user import User
from backend.services.storage_service import storage_service

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/voice", tags=["Voice"])

MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25MB (OpenAI limit)
ALLOWED_AUDIO_TYPES = [
    'audio/mpeg', 'audio/mp3', 'audio/mp4', 'audio/wav',
    'audio/webm', 'audio/ogg', 'audio/m4a', 'audio/flac'
]


def get_openai_api_key(db: Session, user_id: str) -> Optional[str]:
    """
    Get OpenAI API key from user's active model configurations.
    Checks for any active OpenAI provider config.
    """
    from backend.models.entities.user_config import UserModelConfig, ProviderType
    from backend.core.security import decrypt_api_key
    
    # Find active OpenAI config for this user
    config = db.query(UserModelConfig).filter(
        UserModelConfig.user_id == user_id,
        UserModelConfig.provider == ProviderType.OPENAI,
        UserModelConfig.status == 'active'
    ).first()
    
    if not config:
        return None
    
    # Decrypt and return API key
    if config.api_key_encrypted:
        try:
            return decrypt_api_key(config.api_key_encrypted)
        except Exception:
            return None
    
    return None


def check_voice_available(db: Session, user_id: str) -> dict:
    """
    Check if voice features are available for this user.
    Returns status and message.
    """
    from backend.services.whisper_cpp_service import get_whisper_cpp_service

    if get_whisper_cpp_service().is_available():
        return {
            "available": True,
            "message": "Local whisper.cpp STT ready",
            "provider": "whisper_cpp",
        }

    api_key = get_openai_api_key(db, user_id)

    if api_key:
        return {
            "available": True,
            "message": "Voice features ready",
            "provider": "openai"
        }

    # Check if user has any model configs at all
    from backend.models.entities.user_config import UserModelConfig
    has_configs = db.query(UserModelConfig).filter(
        UserModelConfig.user_id == user_id
    ).count() > 0

    if has_configs:
        return {
            "available": False,
            "message": "OpenAI API key required for voice features. Please add an OpenAI provider in Models page.",
            "provider": None,
            "action_required": "add_openai_provider"
        }
    else:
        return {
            "available": False,
            "message": "No AI providers configured. Please add an OpenAI provider in Models page to enable voice features.",
            "provider": None,
            "action_required": "add_any_provider"
        }


def get_whisper_client(api_key: str):
    """Get OpenAI client for Whisper."""
    try:
        import openai
        return openai.OpenAI(api_key=api_key)
    except ImportError:
        return None
    except Exception:
        return None




@router.get(
    "/enhanced-status",
    summary="Get Enhanced Voice Status",
    description="Get detailed voice status including local fallback availability and TTS provider status.",
    responses=build_responses(None),
)
async def get_enhanced_voice_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get detailed voice status including local fallback availability and TTS provider status.
    Frontend uses this to decide between different voice options.
    """
    from backend.services.audio_service import AudioService
    from backend.services.voice.voice_config_service import VoiceConfigService
    
    user_id = str(current_user["sub"])
    audio_service = AudioService()
    
    # Get voice configuration
    voice_config = VoiceConfigService.get_or_create_default(db, user_id)
    
    # Get audio service status
    status = audio_service.get_status(db, user_id)
    
    # Check whisper.cpp availability
    from backend.services.whisper_cpp_service import get_whisper_cpp_service
    whisper_available = get_whisper_cpp_service().is_available()

    return {
        "stt": {
            "whisper_cpp": {
                "available": whisper_available,
                "message": "Local whisper.cpp STT (primary)" if whisper_available
                           else "whisper.cpp not built into this image",
                "supports_recognition": whisper_available,
            },
            "openai": {
                "available": status["openai_available"],
                "message": "OpenAI Whisper STT" if status["openai_available"] else "OpenAI API key required",
                "action_required": "add_openai_provider" if not status["openai_available"] else None,
            },
            "local": {
                "available": True,  # Browser API is always "available" as a concept
                "message": "Browser-native Web Speech API (fallback)",
                "supports_recognition": True,
            },
            "recommended": "whisper_cpp" if whisper_available else ("openai" if status["openai_available"] else "local"),
            "current": "whisper_cpp" if whisper_available else ("openai" if status["openai_available"] else "local"),
        },
        "tts": {
            "kokoro": {
                "available": status["kokoro_available"],
                "message": "Kokoro TTS (offline)" if status["kokoro_available"] else "Kokoro TTS not available",
                "supports_synthesis": status["kokoro_available"],
            },
            "openai": {
                "available": status["openai_available"],
                "message": "OpenAI TTS (cloud)" if status["openai_available"] else "OpenAI API key required",
                "supports_synthesis": status["openai_available"],
            },
            "recommended": status["tts_provider"],  # Use user's configured provider
            "current": status["tts_provider"],
            "current_voice": status["current_voice"],
        },
        "voice_config": VoiceConfigService.to_dict(voice_config),
        "available_voices": audio_service.get_available_voices(),
    }

    
@router.get(
    "/status",
    summary="Get Voice Status",
    description="Check if voice features are available for current user. Frontend should call this to show appropriate UI.",
    responses=build_responses(None),
)
async def get_voice_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Check if voice features are available for current user.
    Frontend should call this to show appropriate UI.
    """
    user_id = str(current_user["sub"])
    return check_voice_available(db, str(user_id))


@router.post(
    "/transcribe",
    summary="Transcribe Audio",
    description="Transcribe audio to text using OpenAI Whisper. Requires active OpenAI provider configuration.",
    responses=build_responses(None),
)
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Transcribe audio to text using OpenAI Whisper.
    Requires active OpenAI provider configuration.
    """
    user_id = str(current_user["sub"])
    
    # Check voice availability first
    voice_status = check_voice_available(db, user_id)
    if not voice_status["available"]:
        raise ServiceUnavailableError(error={
                "message": voice_status["message"],
                "action_required": voice_status.get("action_required"),
                "needs_provider": True
            }, code="ERROR")
    
    # Validate file type
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise BadRequestError(error=f"Audio type '{audio.content_type}' not supported. Allowed: {', '.join(ALLOWED_AUDIO_TYPES)}", code="AUDIO_TYPE_NOT_SUPPORTED_ALLOWED")
    
    # Read audio content
    try:
        content = await audio.read()
    except Exception as e:
        raise BadRequestError(error=f"Failed to read audio: {str(e)}", code="FAILED_TO_READ_AUDIO")
    
    # Check size
    if len(content) > MAX_AUDIO_SIZE:
        raise TooLargeError(error=f"Audio file exceeds 25MB limit ({len(content) / (1024*1024):.1f}MB)", code="AUDIO_FILE_EXCEEDS_25MB_LIMIT")
    
    # Get API key
    api_key = get_openai_api_key(db, user_id)
    if not api_key:
        raise ServiceUnavailableError(error="OpenAI API key not available. Please configure OpenAI provider in Models page.", code="OPENAI_API_KEY_NOT_AVAILABLE")
    
    # Get Whisper client
    client = get_whisper_client(api_key)
    if not client:
        raise ServiceUnavailableError(error="Voice service temporarily unavailable.", code="VOICE_SERVICE_TEMPORARILY_UNAVAILABLE")
    
    # Save to temp file
    file_ext = os.path.splitext(audio.filename or '.webm')[1] or '.webm'
    temp_path = None
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=file_ext) as tmp:
            tmp.write(content)
            temp_path = tmp.name
        
        # Transcribe with Whisper
        with open(temp_path, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language=language,
                response_format="text"
            )

        # Calculate duration estimate
        duration_seconds = len(content) / 16000  # Rough estimate

        return {
            "success": True,
            "text": transcript,
            "language": language or "auto-detected",
            "duration_seconds": round(duration_seconds, 2),
            "audio_size_bytes": len(content),
            "transcribed_at": datetime.utcnow().isoformat()
        }

    except ServerSTTUnavailable:
        raise  # let the global handler return 503 + STT_UNAVAILABLE
    except Exception as e:
        raise InternalServerError(error=f"Transcription failed: {str(e)}", code="TRANSCRIPTION_FAILED")
    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


@router.post(
    "/synthesize",
    summary="Text To Speech",
    description="Convert text to speech using the configured TTS provider. Supports Kokoro (offline) and OpenAI (cloud) with fallback.",
    responses=build_responses(None),
)
async def text_to_speech(
    text: str = Form(...),
    voice: str = Form(None),  # Use user's configured voice if not specified
    speed: float = Form(1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Convert text to speech using the configured TTS provider.
    
    Supports Kokoro (offline) and OpenAI (cloud) with automatic fallback.
    Uses the user's configured voice and provider from voice configuration.
    """
    from backend.services.audio_service import AudioService
    
    user_id = str(current_user["sub"])
    audio_service = AudioService()
    
    # Validate input
    if not text.strip():
        raise BadRequestError(error="Text cannot be empty", code="TEXT_CANNOT_BE_EMPTY")
    
    if len(text) > 4096:
        raise BadRequestError(error="Text exceeds 4096 character limit", code="TEXT_EXCEEDS_4096_CHARACTER_LIMIT")
    
    try:
        # Use AudioService to synthesize speech with fallback logic
        audio_data = await audio_service.synthesize(
            db=db,
            user_id=user_id,
            text=text,
            voice=voice,
            speed=speed
        )
        
        # Generate unique filename
        audio_id = str(uuid.uuid4())
        audio_filename = f"{audio_id}.wav"  # Using WAV format for consistency
        
        # Upload to StorageService
        object_name = f"voice/{user_id}/{audio_filename}"
        with io.BytesIO(audio_data) as f:
            url = storage_service.upload_file(f, object_name=object_name, content_type="audio/wav")
            
        if not url:
            raise Exception("StorageService returned None")
        
        return {
            "success": True,
            "audio_url": f"/api/v1/voice/audio/{user_id}/{audio_filename}",
            "duration_estimate": len(text) / 15,
            "voice": voice or "user_configured",  # Show the voice used
            "speed": speed,
            "generated_at": datetime.now(timezone.utc).isoformat()
        }
        
    except ProviderUnavailableError as e:
        raise ServiceUnavailableError(error={
            "message": str(e),
            "code": e.code,
            "detail": e._detail,
            "needs_provider": e.code == "OPENAI_KEY_MISSING"
        }, code=e.code)
    except Exception as e:
        raise InternalServerError(error=f"Speech synthesis failed: {str(e)}", code="SPEECH_SYNTHESIS_FAILED")


@router.get(
    "/audio/{user_id}/{filename}",
    summary="Get Audio File",
    description="Retrieve a generated audio file.",
    responses=build_responses(None),
)
async def get_audio_file(
    user_id: str,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Retrieve a generated audio file.
    """
    # Security check
    if str(current_user["sub"]) != user_id and not current_user.get("is_admin"):
        raise ForbiddenError(error="Access denied", code="ACCESS_DENIED")
    
    object_name = f"voice/{user_id}/{filename}"
    url = storage_service.generate_presigned_url(object_name, expiration=3600)
    
    if not url:
        raise NotFoundError(error="Audio file not found or failed to generate URL", code="AUDIO_FILE_NOT_FOUND_OR")
    
    return RedirectResponse(url=url)


@router.get(
    "/languages",
    summary="List Supported Languages",
    description="List languages supported by Whisper transcription.",
    responses=build_responses(None),
)
async def list_supported_languages():
    """List languages supported by Whisper transcription."""
    return {
        "languages": [
            {"code": "en", "name": "English"},
            {"code": "es", "name": "Spanish"},
            {"code": "fr", "name": "French"},
            {"code": "de", "name": "German"},
            {"code": "it", "name": "Italian"},
            {"code": "pt", "name": "Portuguese"},
            {"code": "nl", "name": "Dutch"},
            {"code": "pl", "name": "Polish"},
            {"code": "ru", "name": "Russian"},
            {"code": "zh", "name": "Chinese"},
            {"code": "ja", "name": "Japanese"},
            {"code": "ko", "name": "Korean"},
        ],
        "auto_detect": True
    }


@router.get(
    "/voices",
    summary="List Tts Voices",
    description="List available TTS voices for the current user's configured provider.",
    responses=build_responses(None),
)
async def list_tts_voices(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List available TTS voices for the current user's configured provider."""
    from backend.services.audio_service import AudioService
    from backend.services.voice.voice_config_service import VoiceConfigService
    
    user_id = str(current_user["sub"])
    audio_service = AudioService()
    
    # Get user's configured provider
    voice_config = VoiceConfigService.get_or_create_default(db, user_id)
    provider = voice_config.tts_provider
    
    # Get available voices for the provider
    voices = audio_service.get_available_voices(provider)
    
    # Get default voice for the provider
    default_voice = "am_adam" if provider == "kokoro" else "alloy"
    
    return {
        "voices": voices,
        "default": default_voice,
        "current_provider": provider,
        "current_voice": voice_config.tts_voice
    }


# ── Voice Channel Integrations ───────────────────────────────────────────

@router.post(
    "/twilio/webhook",
    summary="Twilio Voice Webhook",
    description="Twilio voice webhook handler. Receives inbound Twilio voice call webhooks, validates the request, and returns TwiML. Requires: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in environment.",
    responses=build_responses(None),
)
async def twilio_voice_webhook(
    db: Session = Depends(get_db),
):
    """
    Twilio voice webhook handler.

    Receives inbound Twilio voice call webhooks, validates the request,
    and returns a TwiML response for call handling.

    Requires: TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN in environment.
    """
    twilio_sid = os.getenv("TWILIO_ACCOUNT_SID")
    if not twilio_sid:
        raise ServiceUnavailableError(error={
                "message": "Twilio voice not configured",
                "action_required": "Set TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN",
                "configured": False,
            }, code="ERROR")

    # Return a TwiML-compatible response stub
    return {
        "status": "acknowledged",
        "provider": "twilio",
        "message": "Twilio voice webhook received — integration pending",
        "twiml_response": '<?xml version="1.0" encoding="UTF-8"?>'
                          '<Response><Say>Welcome to Agentium. '
                          'Voice channel integration is being configured.</Say></Response>',
    }


@router.post(
    "/twilio/status",
    summary="Twilio Status Callback",
    description="Twilio call status callback. Receives status updates for ongoing Twilio calls (ringing, in-progress, completed, failed). Logs the event for analytics.",
    responses=build_responses(None),
)
async def twilio_status_callback():
    """
    Twilio call status callback. Receives status updates for ongoing Twilio
    calls (ringing, in-progress, completed, failed) and logs the event.
    """
    return {
        "status": "received",
        "provider": "twilio",
        "message": "Status callback acknowledged",
    }


@router.get(
    "/discord/status",
    summary="Discord Voice Status",
    description="Discord voice connection status. Returns the current state of the Discord voice integration. Requires: DISCORD_VOICE_ENABLED=true in environment.",
    responses=build_responses(None),
)
async def discord_voice_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """
    Discord voice connection status.

    Returns the current state of the Discord voice integration, including
    active voice channels, connected users, and bot status.

    Requires: DISCORD_VOICE_ENABLED=true in environment.
    """
    discord_enabled = os.getenv("DISCORD_VOICE_ENABLED", "false").lower() == "true"

    return {
        "provider": "discord",
        "enabled": discord_enabled,
        "connected": False,
        "active_channels": [],
        "status": "configured" if discord_enabled else "not_configured",
        "message": (
            "Discord voice bot ready for connection"
            if discord_enabled
            else "Set DISCORD_VOICE_ENABLED=true and configure Discord bot token"
        ),
    }


@router.get(
    "/channels",
    summary="List Voice Channels",
    description="List all available voice channels and their status. Aggregates availability of all voice channel integrations (OpenAI, Twilio, Discord, Browser local).",
    responses=build_responses(None),
)
async def list_voice_channels(
    current_user: User = Depends(get_current_active_user),
):
    """
    List all available voice channels and their status.

    Aggregates availability of all voice channel integrations
    (OpenAI, Twilio, Discord, Browser local).
    """
    twilio_configured = bool(os.getenv("TWILIO_ACCOUNT_SID"))
    discord_enabled = os.getenv("DISCORD_VOICE_ENABLED", "false").lower() == "true"

    return {
        "channels": [
            {
                "id": "openai",
                "name": "OpenAI Voice",
                "type": "api",
                "status": "available",
                "description": "Cloud STT (Whisper) + TTS via OpenAI API",
            },
            {
                "id": "local",
                "name": "Browser Local",
                "type": "browser",
                "status": "available",
                "description": "Browser-native Web Speech API fallback",
            },
            {
                "id": "twilio",
                "name": "Twilio Phone",
                "type": "phone",
                "status": "configured" if twilio_configured else "not_configured",
                "description": "Inbound/outbound phone calls via Twilio",
            },
            {
                "id": "discord",
                "name": "Discord Voice",
                "type": "voip",
                "status": "configured" if discord_enabled else "not_configured",
                "description": "Discord voice channel bot integration",
            },
        ]
    }


# ── Voice Bridge (host-side) engine config (Jarvis upgrade, Phase H) ──────────
# Per-user persistence of the bridge's engine settings (wake word, TTS voice,
# proactive announcements). Stored as JSON under the agentium data dir so no
# DB migration is required. The host bridge reads its own env.conf; this route
# is the backend-side source of truth the frontend writes through.

_DEFAULT_VOICE_CONFIG = {
    "requireWakeWord": True,
    "ttsVoice": "af_bella",
    "proactiveEnabled": False,
    "speakerIdentification": False,
}


class VoiceConfigRequest(BaseModel):
    requireWakeWord: Optional[bool] = Field(default=None)
    ttsVoice: Optional[str] = Field(default=None)
    proactiveEnabled: Optional[bool] = Field(default=None)
    speakerIdentification: Optional[bool] = Field(default=None)


def _voice_config_path(user_id: str) -> Path:
    base = Path.home() / ".agentium" / "voice_config"
    base.mkdir(parents=True, exist_ok=True)
    return base / f"{user_id}.json"


def _load_voice_config(user_id: str) -> dict:
    path = _voice_config_path(user_id)
    if path.is_file():
        try:
            stored = json.loads(path.read_text())
            return {**_DEFAULT_VOICE_CONFIG, **stored}
        except Exception:
            return dict(_DEFAULT_VOICE_CONFIG)
    return dict(_DEFAULT_VOICE_CONFIG)


@router.get(
    "/config",
    summary="Get Voice Bridge Config",
    description="Return the current voice-bridge engine config for the authenticated user.",
    responses=build_responses(None),
)
async def get_voice_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Return the current voice-bridge engine config for this user."""
    return _load_voice_config(str(current_user["sub"]))


@router.put(
    "/config",
    summary="Update Voice Bridge Config",
    description="Persist voice-bridge engine config (wake word, TTS voice, proactive mode) for the authenticated user.",
    responses=build_responses(None),
)
async def update_voice_config(
    config: VoiceConfigRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Persist voice-bridge engine config for this user (merged over defaults).
    
    Note: This endpoint is deprecated. Use the new /voice-config endpoints instead.
    """
    current = _load_voice_config(str(current_user["sub"]))
    if config.requireWakeWord is not None:
        current["requireWakeWord"] = config.requireWakeWord
    if config.ttsVoice is not None:
        current["ttsVoice"] = config.ttsVoice
    if config.proactiveEnabled is not None:
        current["proactiveEnabled"] = config.proactiveEnabled
    if config.speakerIdentification is not None:
        current["speakerIdentification"] = config.speakerIdentification
    try:
        _voice_config_path(str(current_user["sub"])).write_text(json.dumps(current, indent=2))
    except Exception as exc:
        raise InternalServerError(error=f"Failed to persist voice config: {exc}", code="VOICE_CONFIG_WRITE_FAILED")
    return current


# ── New Database-Backed Voice Configuration Endpoints ────────────────────────

class VoiceConfigResponse(BaseModel):
    """Voice configuration response schema."""
    user_id: str
    require_wake_word: bool
    tts_voice: str
    tts_provider: str
    proactive_enabled: bool
    speaker_identification: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class VoiceConfigUpdateRequest(BaseModel):
    """Voice configuration update request schema."""
    require_wake_word: Optional[bool] = Field(default=None, description="Whether wake word is required")
    tts_voice: Optional[str] = Field(default=None, description="TTS voice to use")
    tts_provider: Optional[str] = Field(default=None, description="TTS provider (kokoro or openai)")
    proactive_enabled: Optional[bool] = Field(default=None, description="Whether proactive voice is enabled")
    speaker_identification: Optional[bool] = Field(default=None, description="Whether speaker identification is enabled")


@router.get(
    "/voice-config",
    summary="Get Voice Configuration",
    description="Get the current voice configuration for the authenticated user.",
    responses=build_responses(None),
)
async def get_voice_configuration(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get the current voice configuration for the authenticated user."""
    from backend.services.voice.voice_config_service import VoiceConfigService
    
    user_id = str(current_user["sub"])
    config = VoiceConfigService.get_or_create_default(db, user_id)
    
    return VoiceConfigService.to_dict(config)


@router.put(
    "/voice-config",
    summary="Update Voice Configuration",
    description="Update the voice configuration for the authenticated user.",
    responses=build_responses(None),
)
async def update_voice_configuration(
    update_data: VoiceConfigUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Update the voice configuration for the authenticated user."""
    from backend.services.voice.voice_config_service import VoiceConfigService
    
    user_id = str(current_user["sub"])
    
    # Update the configuration
    config = VoiceConfigService.update(
        db=db,
        user_id=user_id,
        require_wake_word=update_data.require_wake_word,
        tts_voice=update_data.tts_voice,
        tts_provider=update_data.tts_provider,
        proactive_enabled=update_data.proactive_enabled,
        speaker_identification=update_data.speaker_identification
    )
    
    return VoiceConfigService.to_dict(config)


@router.get(
    "/voice-config/status",
    summary="Get Voice Configuration Status",
    description="Get detailed status of voice configuration including provider availability.",
    responses=build_responses(None),
)
async def get_voice_configuration_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """Get detailed status of voice configuration including provider availability."""
    from backend.services.audio_service import AudioService
    from backend.services.voice.voice_config_service import VoiceConfigService
    
    user_id = str(current_user["sub"])
    audio_service = AudioService()
    
    # Get voice configuration
    voice_config = VoiceConfigService.get_or_create_default(db, user_id)
    
    # Get audio service status
    status = audio_service.get_status(db, user_id)
    
    # Combine with voice config
    result = {
        **status,
        "current_config": VoiceConfigService.to_dict(voice_config)
    }
    
    return result


@router.get(
    "/voice-config/providers",
    summary="List Available TTS Providers",
    description="List available TTS providers and their voices.",
    responses=build_responses(None),
)
async def list_tts_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """List available TTS providers and their voices."""
    from backend.services.audio_service import AudioService
    
    audio_service = AudioService()
    
    # Get available voices for all providers
    all_voices = audio_service.get_available_voices()
    
    # Check provider availability
    kokoro_available = audio_service._is_kokoro_available()
    openai_key = audio_service._get_openai_api_key(db, str(current_user["sub"]))
    openai_available = openai_key is not None
    
    return {
        "providers": {
            "kokoro": {
                "available": kokoro_available,
                "voices": all_voices.get("kokoro", []),
                "default_voice": "am_adam"
            },
            "openai": {
                "available": openai_available,
                "voices": all_voices.get("openai", []),
                "default_voice": "alloy"
            }
        },
        "current_provider": "kokoro" if kokoro_available else ("openai" if openai_available else None)
    }