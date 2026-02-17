"""
Voice processing endpoints for speech-to-text and text-to-speech.
Uses OpenAI API key from user's model configurations (if available).
"""

import os
import uuid
import tempfile
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.models.entities.user import User

router = APIRouter(prefix="/voice", tags=["Voice"])


# Configuration - use /tmp as primary storage (temporary)
def get_upload_dir() -> Path:
    """Get upload directory in /tmp."""
    path = Path("/tmp/agentium_uploads/voice")
    path.mkdir(parents=True, exist_ok=True)
    return path

UPLOAD_DIR = get_upload_dir()
print(f"[Voice] Using upload directory: {UPLOAD_DIR}")

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


@router.get("/status")
async def get_voice_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Check if voice features are available for current user.
    Frontend should call this to show appropriate UI.
    """
    user_id = current_user.id if hasattr(current_user, 'id') else current_user.get('id')
    return check_voice_available(db, str(user_id))


@router.post("/transcribe")
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
    user_id = str(current_user.id)
    
    # Check voice availability first
    status = check_voice_available(db, user_id)
    if not status["available"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": status["message"],
                "action_required": status.get("action_required"),
                "needs_provider": True
            }
        )
    
    # Validate file type
    if audio.content_type not in ALLOWED_AUDIO_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Audio type '{audio.content_type}' not supported. Allowed: {', '.join(ALLOWED_AUDIO_TYPES)}"
        )
    
    # Read audio content
    try:
        content = await audio.read()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to read audio: {str(e)}"
        )
    
    # Check size
    if len(content) > MAX_AUDIO_SIZE:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Audio file exceeds 25MB limit ({len(content) / (1024*1024):.1f}MB)"
        )
    
    # Get API key
    api_key = get_openai_api_key(db, user_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key not available. Please configure OpenAI provider in Models page."
        )
    
    # Get Whisper client
    client = get_whisper_client(api_key)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service temporarily unavailable."
        )
    
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
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Transcription failed: {str(e)}"
        )
    finally:
        # Cleanup temp file
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except:
                pass


@router.post("/synthesize")
async def text_to_speech(
    text: str = Form(...),
    voice: str = Form("alloy"),
    speed: float = Form(1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Convert text to speech using OpenAI TTS.
    Requires active OpenAI provider configuration.
    """
    user_id = str(current_user.id)
    
    # Check voice availability first
    status = check_voice_available(db, user_id)
    if not status["available"]:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": status["message"],
                "action_required": status.get("action_required"),
                "needs_provider": True
            }
        )
    
    # Validate input
    if not text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text cannot be empty"
        )
    
    if len(text) > 4096:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Text exceeds 4096 character limit"
        )
    
    # Validate voice
    allowed_voices = ['alloy', 'echo', 'fable', 'onyx', 'nova', 'shimmer']
    if voice not in allowed_voices:
        voice = 'alloy'
    
    # Get API key
    api_key = get_openai_api_key(db, user_id)
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OpenAI API key not available. Please configure OpenAI provider in Models page."
        )
    
    # Get client
    client = get_whisper_client(api_key)
    if not client:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Voice service temporarily unavailable."
        )
    
    try:
        # Generate speech
        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            speed=speed
        )
        
        # Save to file
        audio_id = str(uuid.uuid4())
        audio_filename = f"{audio_id}.mp3"
        user_dir = UPLOAD_DIR / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        
        audio_path = user_dir / audio_filename
        response.stream_to_file(str(audio_path))
        
        return {
            "success": True,
            "audio_url": f"/api/v1/voice/audio/{user_id}/{audio_filename}",
            "duration_estimate": len(text) / 15,
            "voice": voice,
            "speed": speed,
            "generated_at": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Speech synthesis failed: {str(e)}"
        )


@router.get("/audio/{user_id}/{filename}")
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
    if str(current_user.id) != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )
    
    audio_path = UPLOAD_DIR / user_id / filename
    
    if not audio_path.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Audio file not found"
        )
    
    return FileResponse(
        path=audio_path,
        media_type="audio/mpeg",
        filename=filename
    )


@router.get("/languages")
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


@router.get("/voices")
async def list_tts_voices():
    """List available TTS voices."""
    return {
        "voices": [
            {"id": "alloy", "name": "Alloy", "description": "Neutral, balanced"},
            {"id": "echo", "name": "Echo", "description": "Male, warm"},
            {"id": "fable", "name": "Fable", "description": "Male, British accent"},
            {"id": "onyx", "name": "Onyx", "description": "Male, deep"},
            {"id": "nova", "name": "Nova", "description": "Female, professional"},
            {"id": "shimmer", "name": "Shimmer", "description": "Female, bright"},
        ],
        "default": "alloy"
    }