"""
Audio WebSocket streaming endpoints — Phase 10.3.

Provides WebSocket-based audio streaming for real-time voice interaction
and thin REST wrappers around the AudioService.
"""

import logging
from typing import Optional

from fastapi import (
    APIRouter, Depends, File, Form,
    UploadFile, WebSocket, WebSocketDisconnect,
)

from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from sqlalchemy.orm import Session

from backend.api.routes.auth import get_current_active_user
from backend.core.auth import get_current_user
from backend.models.database import get_db
from backend.models.entities.user import User
from backend.models.entities.speaker_profile import SpeakerProfile
from backend.services.audio_service import get_audio_service, get_speaker_identifier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audio", tags=["Audio Streaming"])


# ── REST Endpoints ────────────────────────────────────────────────────────────

@router.get("/status")
async def audio_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Check audio service availability for the current user."""
    svc = get_audio_service()
    return svc.get_status(db, str(current_user.id))


@router.post("/transcribe")
async def transcribe_audio(
    audio: UploadFile = File(...),
    language: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Single-shot audio transcription via OpenAI Whisper."""
    svc = get_audio_service()
    identifier = get_speaker_identifier()
    try:
        audio_bytes = await audio.read()
        text = await svc.transcribe(
            db,
            str(current_user.id),
            audio_bytes,
            language=language,
            filename=audio.filename or "audio.wav",
        )
        speaker_info = identifier.identify(db, audio_bytes)
        return {
            "text": text,
            "language": language,
            "speaker_id": speaker_info.get("speaker_id"),
            "speaker_name": speaker_info.get("name"),
            "speaker_confidence": speaker_info.get("confidence")
        }
    except ValueError as exc:
        raise BadRequestError(error=str(exc), code="STREXC")
    except Exception as exc:
        logger.error("Transcription failed: %s", exc)
        raise InternalServerError(error="Transcription failed", code="TRANSCRIPTION_FAILED")


@router.post("/synthesize")
async def synthesize_speech(
    text: str = Form(...),
    voice: str = Form("alloy"),
    speed: float = Form(1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Single-shot text-to-speech via OpenAI TTS. Returns MP3."""
    from fastapi.responses import Response

    svc = get_audio_service()
    try:
        audio_bytes = await svc.synthesize(
            db, str(current_user.id), text, voice=voice, speed=speed,
        )
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "attachment; filename=speech.mp3"},
        )
    except ValueError as exc:
        raise BadRequestError(error=str(exc), code="STREXC")
    except Exception as exc:
        logger.error("Synthesis failed: %s", exc)
        raise InternalServerError(error="Speech synthesis failed", code="SPEECH_SYNTHESIS_FAILED")

# ── Speaker Identification Endpoints ────────────────────────────────────────────

@router.post("/speakers/register")
async def register_speaker(
    audio: UploadFile = File(...),
    name: str = Form("Unknown Speaker"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Enroll a new speaker by uploading a voice sample and an associated name."""
    identifier = get_speaker_identifier()
    try:
        audio_bytes = await audio.read()
        profile = identifier.enroll(db, str(current_user.id), name, audio_bytes)
        if not profile:
            raise BadRequestError(error="Failed to extract embedding from audio sample.", code="FAILED_TO_EXTRACT_EMBEDDING_FROM")
        return profile.to_dict()
    except Exception as exc:
        logger.error("Speaker registration failed: %s", exc)
        raise InternalServerError(error="Speaker registration failed", code="SPEAKER_REGISTRATION_FAILED")

@router.get("/speakers")
async def get_speakers(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """List all enrolled speaker profiles."""
    identifier = get_speaker_identifier()
    return {"speakers": identifier.list_profiles(db)}

@router.delete("/speakers/{speaker_id}")
async def delete_speaker(
    speaker_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Soft delete a speaker profile."""
    profile = db.query(SpeakerProfile).filter(SpeakerProfile.id == speaker_id, SpeakerProfile.is_deleted == False).first()
    if not profile:
        raise NotFoundError(error="Speaker profile not found", code="SPEAKER_PROFILE_NOT_FOUND")
    profile.is_deleted = True
    db.commit()
    return {"status": "success", "message": "Speaker profile deleted"}


# ── WebSocket Streaming ──────────────────────────────────────────────────────

@router.websocket("/stream")
async def audio_stream(websocket: WebSocket):
    """
    Bidirectional audio WebSocket.

    Client sends:
        - Binary audio chunks (PCM/WAV/WebM)

    Server responds:
        - JSON: {"type": "transcript", "text": "..."}
        - Binary: TTS audio response (MP3)
        - JSON: {"type": "error", "message": "..."}

    Protocol:
        1. Client sends JSON: {"action": "start", "language": "en"}
        2. Client streams binary audio frames
        3. Client sends JSON: {"action": "stop"} to end recording
        4. Server responds with transcript + optional TTS reply
    """
    await websocket.accept()
    logger.info("Audio WebSocket connected")

    db: Session = next(get_db())
    svc = get_audio_service()
    audio_buffer = bytearray()
    language: Optional[str] = None

    try:
        while True:
            data = await websocket.receive()

            if "text" in data:
                import json
                msg = json.loads(data["text"])
                action = msg.get("action", "")

                if action == "start":
                    audio_buffer.clear()
                    language = msg.get("language")
                    await websocket.send_json({"type": "status", "message": "recording"})

                elif action == "stop":
                    if not audio_buffer:
                        await websocket.send_json({
                            "type": "error",
                            "message": "No audio data received",
                        })
                        continue

                    try:
                        # Get user from token if available
                        user_id = msg.get("user_id", "system")
                        audio_b = bytes(audio_buffer)
                        text = await svc.transcribe(
                            db, user_id, audio_b,
                            language=language,
                        )

                        identifier = get_speaker_identifier()
                        speaker_info = identifier.identify(db, audio_b)

                        await websocket.send_json({
                            "type": "transcript",
                            "text": text,
                            "speaker_id": speaker_info.get("speaker_id"),
                            "speaker_name": speaker_info.get("name"),
                        })

                        # Optionally respond with TTS
                        if msg.get("auto_respond"):
                            try:
                                tts_bytes = await svc.synthesize(
                                    db, user_id, text,
                                    voice=msg.get("voice", "alloy"),
                                )
                                await websocket.send_bytes(tts_bytes)
                            except Exception as tts_err:
                                logger.debug("TTS response failed: %s", tts_err)

                    except Exception as exc:
                        await websocket.send_json({
                            "type": "error",
                            "message": str(exc),
                        })

                    audio_buffer.clear()

                elif action == "ping":
                    await websocket.send_json({"type": "pong"})

            elif "bytes" in data:
                audio_buffer.extend(data["bytes"])

    except WebSocketDisconnect:
        logger.info("Audio WebSocket disconnected")
    except Exception as exc:
        logger.error("Audio WebSocket error: %s", exc)
    finally:
        db.close()
