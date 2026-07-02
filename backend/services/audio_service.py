"""
Audio Service for Agentium — Phase 10.3.

Wraps OpenAI Whisper (STT) and OpenAI TTS APIs into a reusable service
layer. The existing ``voice.py`` route provides HTTP endpoints; this
service is the logic layer that can also be called by the ChannelManager
for voice messages on external platforms.
"""

import io
from dataclasses import dataclass, field
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
        db: Session,
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
        return identifier.identify(db, audio_bytes)


# ---------------------------------------------------------------------------
# Speaker Identification (Phase 10.3)
# ---------------------------------------------------------------------------

from backend.models.entities.speaker_profile import SpeakerProfile
import uuid
import tempfile
import numpy as np

class SpeakerIdentifier:
    """
    Identifies speakers using voice embedding fingerprints.

    Computes a voice embedding from audio using SpeechBrain ECAPA-TDNN.
    Persists enrolled profiles to the database via SQLAlchemy.

    Usage::

        si = SpeakerIdentifier()
        si.enroll(db, "user-1", "alice", audio_bytes)
        result = si.identify(db, new_audio_bytes)
    """

    # Cosine similarity threshold for positive identification
    IDENTIFICATION_THRESHOLD = 0.70

    def __init__(self):
        """Init."""

        self._classifier = None

    def _get_classifier(self):
        """Lazy-load the ECAPA-TDNN classifier from SpeechBrain."""
        if self._classifier is None:
            try:
                from speechbrain.inference.speaker import EncoderClassifier
                import os
                # By default, downloads to a local cache directory
                run_opts = {}
                if os.environ.get("CUDA_VISIBLE_DEVICES") and os.environ.get("CUDA_VISIBLE_DEVICES") != "-1":
                    run_opts["device"] = "cuda"
                self._classifier = EncoderClassifier.from_hparams(
                    source="speechbrain/spkrec-ecapa-voxceleb",
                    savedir="tmp_speechbrain_model",
                    run_opts=run_opts
                )
            except ImportError:
                logger.warning("speechbrain or torchaudio not installed; speaker ID unavailable")
            except Exception as e:
                logger.error(f"Failed to load SpeechBrain model: {e}")
        return self._classifier

    def _extract_embedding(self, audio_bytes: bytes) -> List[float]:
        """Extract a 1D float array embedding from audio bytes."""
        classifier = self._get_classifier()
        if not classifier:
            return []

        import torchaudio
        
        # Write bytes to a temp file, as torchaudio needs a filepath
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            f.flush()
            tmp_path = f.name
            
        try:
            signal, fs = torchaudio.load(tmp_path)
            # Resample to 16kHz if needed
            if fs != 16000:
                resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
                signal = resampler(signal)
            
            # Predict
            embeddings = classifier.encode_batch(signal)
            # embeddings shape is usually [batch, 1, dims] -> squeeze to 1D
            emd_1d = embeddings.squeeze(0).squeeze(0).detach().cpu().numpy()
            return emd_1d.tolist()
        except Exception as e:
            logger.error(f"Embedding extraction failed: {e}")
            return []
        finally:
            os.remove(tmp_path)

    def enroll(self, db: Session, user_id: Optional[str], username: str, audio_bytes: bytes) -> Optional[SpeakerProfile]:
        """
        Enroll a speaker by storing their voice embedding into the database.
        """
        embedding = self._extract_embedding(audio_bytes)
        if not embedding:
            logger.warning("Enrollment failed: could not extract embedding.")
            return None

        # Check if user already has a profile 
        existing = None
        if user_id:
            existing = db.query(SpeakerProfile).filter(SpeakerProfile.user_id == user_id, SpeakerProfile.is_deleted == False).first()
            if not existing:
                # Fallback to name if user_id matching missed
                existing = db.query(SpeakerProfile).filter(SpeakerProfile.name == username, SpeakerProfile.is_deleted == False).first()
        else:
            existing = db.query(SpeakerProfile).filter(SpeakerProfile.name == username, SpeakerProfile.is_deleted == False).first()

        if existing:
            # We can average embeddings or simply overwrite. For robust updates, keep the new one.
            # Realistically, exponential moving average is better:
            old_emb = np.array(existing.embedding)
            new_emb = np.array(embedding)
            n = existing.sample_count
            updated_emb = ((old_emb * n) + new_emb) / (n + 1)
            
            existing.embedding = updated_emb.tolist()
            existing.sample_count += 1
            existing.name = username
            db.commit()
            db.refresh(existing)
            logger.info(f"Speaker profile updated for {username}")
            return existing

        # Create new 
        profile = SpeakerProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=username,
            embedding=embedding,
            sample_count=1,
            is_deleted=False
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info(f"Speaker enrolled: {username} ({user_id})")
        return profile

    def identify(self, db: Session, audio_bytes: bytes) -> Dict[str, Any]:
        """
        Identify the speaker from audio bytes using cosine similarity against DB.
        """
        profiles = db.query(SpeakerProfile).filter(SpeakerProfile.is_deleted == False).all()
        if not profiles:
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False, "name": "Unknown Speaker"}

        classifier = self._get_classifier()
        if not classifier:
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False, "name": "Unknown Speaker"}

        query_emb_list = self._extract_embedding(audio_bytes)
        if not query_emb_list:
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False, "name": "Unknown Speaker"}

        query_emb = np.array(query_emb_list)
        query_norm = np.linalg.norm(query_emb)
        if query_norm == 0:
            return {"speaker_id": "unknown", "confidence": 0.0, "is_known": False, "name": "Unknown Speaker"}

        best_match = "unknown"
        best_name = "Unknown Speaker"
        best_score = 0.0

        for profile in profiles:
            if not profile.embedding:
                continue
            profile_emb = np.array(profile.embedding)
            profile_norm = np.linalg.norm(profile_emb)
            if profile_norm == 0:
                continue
                
            similarity = float(np.dot(query_emb, profile_emb) / (query_norm * profile_norm))
            if similarity > best_score:
                best_score = similarity
                best_match = profile.id
                best_name = profile.name

        is_known = best_score >= self.IDENTIFICATION_THRESHOLD
        return {
            "speaker_id": best_match if is_known else "unknown",
            "name": best_name if is_known else "Unknown Speaker",
            "confidence": round(best_score, 3),
            "is_known": is_known,
        }

    def list_profiles(self, db: Session) -> List[Dict[str, Any]]:
        """Return summary of all enrolled speaker profiles."""
        profiles = db.query(SpeakerProfile).filter(SpeakerProfile.is_deleted == False).order_by(SpeakerProfile.created_at.desc()).all()
        return [p.to_dict() for p in profiles]


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