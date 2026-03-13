"""
Audio Service for Agentium — Phase 10.3.

Wraps OpenAI Whisper (STT) and OpenAI TTS APIs into a reusable service
layer. The existing ``voice.py`` route provides HTTP endpoints; this
service is the logic layer that can also be called by the ChannelManager
for voice messages on external platforms.
"""

import io
import logging
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_AUDIO_SIZE = 25 * 1024 * 1024  # 25 MB (OpenAI limit)

SUPPORTED_AUDIO_TYPES = [
    "audio/mpeg", "audio/mp3", "audio/mp4", "audio/wav",
    "audio/webm", "audio/ogg", "audio/m4a", "audio/flac",
]

AVAILABLE_TTS_VOICES = [
    {"id": "alloy", "name": "Alloy", "description": "Neutral and balanced"},
    {"id": "echo", "name": "Echo", "description": "Warm and confident"},
    {"id": "fable", "name": "Fable", "description": "British and expressive"},
    {"id": "onyx", "name": "Onyx", "description": "Deep and authoritative"},
    {"id": "nova", "name": "Nova", "description": "Young and bright"},
    {"id": "shimmer", "name": "Shimmer", "description": "Soft and gentle"},
]


# ---------------------------------------------------------------------------
# AudioService
# ---------------------------------------------------------------------------

class AudioService:
    """
    Reusable speech processing service.

    Usage::

        svc = AudioService()
        text = await svc.transcribe(db, user_id, audio_bytes, "en")
        audio = await svc.synthesize(db, user_id, "Hello world")
    """

    def _get_openai_api_key(self, db: Session, user_id: str) -> Optional[str]:
        """Extract OpenAI API key from user's model configurations."""
        try:
            from backend.models.entities import UserModelConfig
            configs = (
                db.query(UserModelConfig)
                .filter(
                    UserModelConfig.user_id == user_id,
                    UserModelConfig.is_active == True,  # noqa: E712
                    UserModelConfig.provider.in_(["openai", "OpenAI"]),
                )
                .all()
            )
            for cfg in configs:
                key = cfg.get_decrypted_api_key()
                if key:
                    return key
        except Exception as exc:
            logger.debug("Could not retrieve OpenAI key: %s", exc)
        return None

    def _get_openai_client(self, api_key: str):
        """Create an OpenAI client instance."""
        from openai import OpenAI
        return OpenAI(api_key=api_key)

    # ── Availability ─────────────────────────────────────────────────────

    def is_available(self, db: Session, user_id: str) -> bool:
        """Check if voice features are available (i.e. OpenAI key configured)."""
        return self._get_openai_api_key(db, user_id) is not None

    def get_status(self, db: Session, user_id: str) -> Dict[str, Any]:
        """Detailed availability status."""
        key = self._get_openai_api_key(db, user_id)
        return {
            "available": key is not None,
            "provider": "openai",
            "stt_model": "whisper-1",
            "tts_model": "tts-1",
            "voices": AVAILABLE_TTS_VOICES,
            "max_audio_size_mb": MAX_AUDIO_SIZE // (1024 * 1024),
        }

    # ── Speech-to-Text ───────────────────────────────────────────────────

    async def transcribe(
        self,
        db: Session,
        user_id: str,
        audio_bytes: bytes,
        language: Optional[str] = None,
        filename: str = "audio.wav",
    ) -> str:
        """
        Transcribe audio bytes to text using OpenAI Whisper.

        Args:
            db: Database session (for key lookup)
            user_id: User requesting transcription
            audio_bytes: Raw audio data
            language: Optional ISO-639-1 language code
            filename: Filename hint for format detection

        Returns:
            The transcribed text.

        Raises:
            ValueError: If no API key is configured or audio is too large.
        """
        api_key = self._get_openai_api_key(db, user_id)
        if not api_key:
            raise ValueError("No OpenAI API key configured for voice features")

        if len(audio_bytes) > MAX_AUDIO_SIZE:
            raise ValueError(
                f"Audio too large: {len(audio_bytes)} bytes "
                f"(max {MAX_AUDIO_SIZE} bytes)"
            )

        client = self._get_openai_client(api_key)

        # Write to temp file (Whisper requires a file-like object)
        suffix = Path(filename).suffix or ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        try:
            with open(tmp_path, "rb") as audio_file:
                kwargs: Dict[str, Any] = {
                    "model": "whisper-1",
                    "file": audio_file,
                }
                if language:
                    kwargs["language"] = language

                transcript = client.audio.transcriptions.create(**kwargs)
                return transcript.text
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # ── Text-to-Speech ────────────────────────────────────────────────────

    async def synthesize(
        self,
        db: Session,
        user_id: str,
        text: str,
        voice: str = "alloy",
        speed: float = 1.0,
    ) -> bytes:
        """
        Synthesize text to speech using OpenAI TTS.

        Args:
            db: Database session (for key lookup)
            user_id: User requesting synthesis
            text: Text to convert to speech
            voice: TTS voice ID (alloy, echo, fable, onyx, nova, shimmer)
            speed: Speed multiplier (0.25 – 4.0)

        Returns:
            MP3 audio bytes.

        Raises:
            ValueError: If no API key is configured.
        """
        api_key = self._get_openai_api_key(db, user_id)
        if not api_key:
            raise ValueError("No OpenAI API key configured for voice features")

        if not text or not text.strip():
            raise ValueError("Text cannot be empty")

        # Clamp speed
        speed = max(0.25, min(4.0, speed))

        # Validate voice
        valid_voices = [v["id"] for v in AVAILABLE_TTS_VOICES]
        if voice not in valid_voices:
            voice = "alloy"

        client = self._get_openai_client(api_key)

        response = client.audio.speech.create(
            model="tts-1",
            voice=voice,
            input=text,
            speed=speed,
        )

        # Collect the audio bytes
        audio_data = b""
        for chunk in response.iter_bytes(chunk_size=4096):
            audio_data += chunk

        return audio_data

    # ── Voice List ─────────────────────────────────────────────────────────

    @staticmethod
    def get_available_voices() -> List[Dict[str, str]]:
        """Return list of available TTS voices."""
        return AVAILABLE_TTS_VOICES

    # ── Speaker Identification (Phase 10.3) ───────────────────────────────

    async def identify_speaker(
        self,
        audio_bytes: bytes,
        speaker_identifier: Optional["SpeakerIdentifier"] = None,
    ) -> Dict[str, Any]:
        """
        Attempt to identify who is speaking from audio bytes.

        Uses the global SpeakerIdentifier (or a provided one) to match
        the voice embedding against enrolled profiles.

        Returns dict with ``speaker_id``, ``confidence``, and ``is_known``.
        """
        identifier = speaker_identifier or get_speaker_identifier()
        return identifier.identify(audio_bytes)


# ---------------------------------------------------------------------------
# Speaker Identification (Phase 10.3)
# ---------------------------------------------------------------------------

@dataclass
class SpeakerProfile:
    """Voice fingerprint for a known speaker."""
    user_id: str
    username: str
    embedding: List[float] = field(default_factory=list)
    enrolled_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    sample_count: int = 0


class SpeakerIdentifier:
    """
    Identifies speakers using voice embedding fingerprints.

    Computes a voice embedding from audio (using the text-embedding
    model as a proxy — in production, replace with a dedicated
    speaker-verification model like ECAPA-TDNN).

    Usage::

        si = SpeakerIdentifier()
        si.enroll("user-1", "alice", audio_bytes)
        result = si.identify(new_audio_bytes)
        # result = {"speaker_id": "user-1", "confidence": 0.87, "is_known": True}
    """

    # Cosine similarity threshold for positive identification
    IDENTIFICATION_THRESHOLD = 0.7

    def __init__(self):
        self._profiles: Dict[str, SpeakerProfile] = {}
        self._model = None

    def _get_model(self):
        """Lazy-load the embedding model."""
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._model = SentenceTransformer(
                    os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
                )
            except ImportError:
                logger.warning("sentence-transformers not installed; speaker ID unavailable")
        return self._model

    def _audio_to_text_repr(self, audio_bytes: bytes) -> str:
        """
        Convert audio bytes to a text representation for embedding.

        This is a lightweight proxy: in production, use a dedicated
        speaker-verification embedding model. Here we use audio byte
        statistics as a fingerprint proxy.
        """
        import hashlib
        # Create a deterministic fingerprint from audio characteristics
        byte_stats = {
            "length": len(audio_bytes),
            "hash": hashlib.sha256(audio_bytes).hexdigest()[:32],
            "energy": sum(audio_bytes) / max(len(audio_bytes), 1),
            "variance": sum((b - 128) ** 2 for b in audio_bytes[:1000]) / min(len(audio_bytes), 1000),
        }
        return f"speaker_voice energy={byte_stats['energy']:.2f} variance={byte_stats['variance']:.2f} hash={byte_stats['hash']}"

    def enroll(self, user_id: str, username: str, audio_bytes: bytes) -> SpeakerProfile:
        """
        Enroll a speaker by storing their voice embedding.

        Multiple enrollments for the same user_id update the profile.
        """
        model = self._get_model()
        text_repr = self._audio_to_text_repr(audio_bytes)

        embedding: List[float] = []
        if model:
            try:
                emb = model.encode([text_repr], convert_to_numpy=True)
                embedding = emb[0].tolist()
            except Exception as exc:
                logger.warning("Speaker enrollment embedding failed: %s", exc)

        existing = self._profiles.get(user_id)
        if existing:
            existing.embedding = embedding
            existing.sample_count += 1
            return existing

        profile = SpeakerProfile(
            user_id=user_id,
            username=username,
            embedding=embedding,
            sample_count=1,
        )
        self._profiles[user_id] = profile
        logger.info("Speaker enrolled: %s (%s)", username, user_id)
        return profile

    def identify(self, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Identify the speaker from audio bytes.

        Returns a dict with speaker_id, confidence, and is_known flag.
        Falls back gracefully if no profiles are enrolled or embedding fails.
        """
        if not self._profiles:
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False}

        model = self._get_model()
        if not model:
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False}

        text_repr = self._audio_to_text_repr(audio_bytes)

        try:
            import numpy as np
            query_emb = model.encode([text_repr], convert_to_numpy=True)[0]

            best_match = "unknown"
            best_score = 0.0

            for user_id, profile in self._profiles.items():
                if not profile.embedding:
                    continue
                profile_emb = np.array(profile.embedding)
                denom = np.linalg.norm(query_emb) * np.linalg.norm(profile_emb)
                if denom == 0:
                    continue
                similarity = float(np.dot(query_emb, profile_emb) / denom)
                if similarity > best_score:
                    best_score = similarity
                    best_match = user_id

            is_known = best_score >= self.IDENTIFICATION_THRESHOLD
            return {
                "speaker_id": best_match if is_known else "unknown",
                "confidence": round(best_score, 3),
                "is_known": is_known,
            }
        except Exception as exc:
            logger.debug("Speaker identification failed: %s", exc)
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False}

    def list_profiles(self) -> List[Dict[str, Any]]:
        """Return summary of all enrolled speaker profiles."""
        return [
            {
                "user_id": p.user_id,
                "username": p.username,
                "enrolled_at": p.enrolled_at,
                "sample_count": p.sample_count,
                "has_embedding": len(p.embedding) > 0,
            }
            for p in self._profiles.values()
        ]


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------

import os
from dataclasses import dataclass, field
from datetime import datetime

_audio_service: Optional[AudioService] = None


def get_audio_service() -> AudioService:
    """Return the singleton AudioService."""
    global _audio_service
    if _audio_service is None:
        _audio_service = AudioService()
    return _audio_service


_speaker_identifier: Optional[SpeakerIdentifier] = None


def get_speaker_identifier() -> SpeakerIdentifier:
    """Return the singleton SpeakerIdentifier."""
    global _speaker_identifier
    if _speaker_identifier is None:
        _speaker_identifier = SpeakerIdentifier()
    return _speaker_identifier
