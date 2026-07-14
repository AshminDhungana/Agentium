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

from backend.models.entities.speaker_profile import SpeakerProfile
from backend.services.whisper_cpp_service import (
    get_whisper_cpp_service,
    LocalSTTError,
)
from backend.core.exceptions import ServerSTTUnavailable

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
        """Server STT available if whisper.cpp OR an OpenAI key is present."""
        if get_whisper_cpp_service().is_available():
            return True
        return self._get_openai_api_key(db, user_id) is not None

    def get_status(self, db: Session, user_id: str) -> Dict[str, Any]:
        """Detailed availability status."""
        whisper_available = get_whisper_cpp_service().is_available()
        key = self._get_openai_api_key(db, user_id)
        provider = "whisper_cpp" if whisper_available else ("openai" if key else None)
        si = get_speaker_identifier()
        return {
            "available": provider is not None,
            "provider": provider,
            "whisper_cpp_available": whisper_available,
            "stt_model": "ggml-base.en" if whisper_available else "whisper-1",
            "tts_model": "tts-1",
            "voices": AVAILABLE_TTS_VOICES,
            "max_audio_size_mb": MAX_AUDIO_SIZE // (1024 * 1024),
            "speaker_id_enabled": si._config.enabled,
            "speaker_id_available": si.is_available(),
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
        Transcribe audio bytes to text.

        Server-side chain (backend-owned):
          1. Local whisper.cpp (PRIMARY, no API key needed)
          2. OpenAI Whisper (if an API key is configured)
          3. raise ServerSTTUnavailable -> frontend falls back to browser

        Raises:
            ServerSTTUnavailable: No server STT engine is available.
        """
        # 1. Local whisper.cpp (PRIMARY)
        whisper = get_whisper_cpp_service()
        if whisper.is_available():
            try:
                return await whisper.transcribe(audio_bytes, language)
            except LocalSTTError as exc:
                logger.warning("[STT] local whisper.cpp failed: %s — falling back", exc)

        # 2. OpenAI Whisper (if a key is configured)
        api_key = self._get_openai_api_key(db, user_id)
        if api_key:
            return await self._transcribe_openai(db, user_id, audio_bytes, language, filename)

        # 3. Nothing server-side available
        raise ServerSTTUnavailable(
            "No server STT engine available",
            code="STT_UNAVAILABLE",
            detail={"fallback": "browser"},
        )

    async def _transcribe_openai(
        self,
        db: Session,
        user_id: str,
        audio_bytes: bytes,
        language: Optional[str] = None,
        filename: str = "audio.wav",
    ) -> str:
        """Transcribe via OpenAI Whisper (requires an API key)."""
        api_key = self._get_openai_api_key(db, user_id)
        if not api_key:
            raise ValueError("No OpenAI API key configured for voice features")

        if len(audio_bytes) > MAX_AUDIO_SIZE:
            raise ValueError(
                f"Audio too large: {len(audio_bytes)} bytes "
                f"(max {MAX_AUDIO_SIZE} bytes)"
            )

        client = self._get_openai_client(api_key)

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


def get_audio_service() -> "AudioService":
    """Return a fresh AudioService instance (lazy factory used by the API routes)."""
    return AudioService()


# ---------------------------------------------------------------------------
# Speaker Identification (Phase 10.3 / 15.4)
# ---------------------------------------------------------------------------

from dataclasses import dataclass
from typing import Callable, Protocol
import uuid
import tempfile
import numpy as np


@dataclass
class SpeakerIDConfig:
    """Runtime configuration for speaker identification."""
    enabled: bool = True
    model_source: str = "speechbrain/spkrec-ecapa-voxceleb"
    threshold: float = 0.70
    min_duration_s: float = 1.0
    cache_dir: str = "./models/speechbrain"
    require_liveness: bool = False


def load_speaker_id_config() -> SpeakerIDConfig:
    """Build a SpeakerIDConfig from application Settings."""
    from backend.core.config import settings
    return SpeakerIDConfig(
        enabled=settings.SPEAKER_ID_ENABLED,
        model_source=settings.SPEAKER_ID_MODEL_SOURCE,
        threshold=settings.SPEAKER_ID_THRESHOLD,
        min_duration_s=settings.SPEAKER_ID_MIN_DURATION_S,
        cache_dir=settings.SPEAKER_ID_CACHE_DIR,
        require_liveness=settings.SPEAKER_ID_REQUIRE_LIVENESS,
    )


class SpeakerEncoder(Protocol):
    """Embedding backend contract. Implementations turn audio bytes into a vector."""
    def embed(self, audio_bytes: bytes) -> List[float]: ...


class SpeechBrainEncoder:
    """
    SpeechBrain ECAPA-TDNN embedding backend (lazy, optional dependency).

    NOTE (SpeechBrain 1.1.0 API): the class is ``EncoderClassifier`` and it is
    imported from ``speechbrain.inference.classifiers`` (not ``.speaker``).
    It is built with ``EncoderClassifier.from_hparams(...)`` and used via
    ``encode_batch(signal)``.
    """
    def __init__(self, model_source: str, cache_dir: str):
        self._model_source = model_source
        self._cache_dir = cache_dir
        self._classifier = None

    def _ensure(self):
        if self._classifier is None:
            try:
                from speechbrain.inference.classifiers import EncoderClassifier
                import os
                run_opts = {}
                cuda = os.environ.get("CUDA_VISIBLE_DEVICES")
                if cuda not in (None, "", "-1"):
                    run_opts["device"] = "cuda"
                os.makedirs(self._cache_dir, exist_ok=True)
                self._classifier = EncoderClassifier.from_hparams(
                    source=self._model_source,
                    savedir=self._cache_dir,
                    run_opts=run_opts,
                )
            except ImportError:
                logger.warning("speechbrain or torchaudio not installed; speaker ID unavailable")
                raise
            except Exception as e:
                logger.error(f"Failed to load SpeechBrain model: {e}")
                raise
        return self._classifier

    def embed(self, audio_bytes: bytes) -> List[float]:
        import os
        import torchaudio
        classifier = self._ensure()
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(audio_bytes)
            f.flush()
            tmp_path = f.name
        try:
            signal, fs = torchaudio.load(tmp_path)
            if signal.shape[0] > 1:
                signal = signal.mean(0, keepdim=True)
            if fs != 16000:
                resampler = torchaudio.transforms.Resample(orig_freq=fs, new_freq=16000)
                signal = resampler(signal)
            embeddings = classifier.encode_batch(signal)
            emb_1d = embeddings.squeeze(0).squeeze(0).detach().cpu().numpy()
            return emb_1d.tolist()
        except Exception as e:
            logger.error(f"Embedding extraction failed: {e}")
            return []
        finally:
            os.remove(tmp_path)


class SpeakerIdentifier:
    """
    Identifies speakers using voice embedding fingerprints.

    The embedding backend is injectable (``classifier``) so tests and
    environments without SpeechBrain/torchaudio can run. Configuration is
    sourced from application Settings unless overridden. An optional
    ``liveness_check`` provides a (default-off) anti-spoofing seam.
    """

    def __init__(
        self,
        classifier: Optional[SpeakerEncoder] = None,
        config: Optional[SpeakerIDConfig] = None,
        liveness_check: Optional[Callable[[bytes], bool]] = None,
    ):
        self._classifier = classifier
        self._config = config or load_speaker_id_config()
        self._liveness_check = liveness_check
        self.IDENTIFICATION_THRESHOLD = self._config.threshold

    def _get_classifier(self) -> Optional[SpeakerEncoder]:
        if self._classifier is None:
            self._classifier = SpeechBrainEncoder(
                self._config.model_source, self._config.cache_dir
            )
        return self._classifier

    def _backend_importable(self) -> bool:
        try:
            import speechbrain  # noqa: F401
            import torchaudio  # noqa: F401
            return True
        except Exception:
            logger.warning("Speaker ID unavailable: speechbrain/torchaudio not installed")
            return False

    def is_available(self) -> bool:
        if not self._config.enabled:
            return False
        if self._classifier is not None:
            return True
        return self._backend_importable()

    def _validate_min_duration(self, audio_bytes: bytes) -> bool:
        try:
            import wave as _wave
            with _wave.open(io.BytesIO(audio_bytes), "rb") as wf:
                nframes = wf.getnframes()
                framerate = wf.getframerate()
                if framerate <= 0:
                    return True
                return (nframes / framerate) >= self._config.min_duration_s
        except Exception:
            return True

    def enroll(self, db: Session, user_id: Optional[str], username: str, audio_bytes: bytes) -> Optional[SpeakerProfile]:
        if not self._config.enabled:
            logger.warning("Speaker enrollment skipped: speaker ID disabled")
            return None
        if self._config.require_liveness and self._liveness_check is not None:
            if not self._liveness_check(audio_bytes):
                logger.warning("Speaker enrollment rejected: liveness check failed (possible spoof)")
                return None
        if not self._validate_min_duration(audio_bytes):
            logger.warning("Enrollment skipped: audio too short")
            return None

        embedding = self._get_classifier().embed(audio_bytes)
        if not embedding:
            logger.warning("Enrollment failed: could not extract embedding.")
            return None

        existing = None
        if user_id:
            existing = db.query(SpeakerProfile).filter(
                SpeakerProfile.user_id == user_id, SpeakerProfile.is_deleted == False
            ).first()
            if not existing:
                existing = db.query(SpeakerProfile).filter(
                    SpeakerProfile.name == username, SpeakerProfile.is_deleted == False
                ).first()
        else:
            existing = db.query(SpeakerProfile).filter(
                SpeakerProfile.name == username, SpeakerProfile.is_deleted == False
            ).first()

        if existing:
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

        profile = SpeakerProfile(
            id=str(uuid.uuid4()),
            user_id=user_id,
            name=username,
            embedding=embedding,
            sample_count=1,
            is_deleted=False,
        )
        db.add(profile)
        db.commit()
        db.refresh(profile)
        logger.info(f"Speaker enrolled: {username} ({user_id})")
        return profile

    def identify(self, db: Session, audio_bytes: bytes) -> Dict[str, Any]:
        unknown = {
            "speaker_id": "unknown",
            "name": "Unknown Speaker",
            "confidence": 0.0,
            "is_known": False,
        }
        if not self._config.enabled:
            return unknown

        profiles = db.query(SpeakerProfile).filter(SpeakerProfile.is_deleted == False).all()
        if not profiles:
            return unknown
        if not self._validate_min_duration(audio_bytes):
            return unknown
        if self._config.require_liveness and self._liveness_check is not None:
            if not self._liveness_check(audio_bytes):
                logger.warning("Speaker identification rejected: liveness check failed (possible spoof)")
                return unknown

        classifier = self._get_classifier()
        if not classifier:
            return unknown

        query_emb_list = classifier.embed(audio_bytes)
        if not query_emb_list:
            return unknown

        query_emb = np.array(query_emb_list)
        query_norm = np.linalg.norm(query_emb)
        if query_norm == 0:
            return unknown

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
        profiles = db.query(SpeakerProfile).filter(
            SpeakerProfile.is_deleted == False
        ).order_by(SpeakerProfile.created_at.desc()).all()
        return [p.to_dict() for p in profiles]


# ---------------------------------------------------------------------------

_speaker_identifier: Optional[SpeakerIdentifier] = None


def get_speaker_identifier() -> SpeakerIdentifier:
    """Return the process-wide SpeakerIdentifier singleton (lazy)."""
    global _speaker_identifier
    if _speaker_identifier is None:
        _speaker_identifier = SpeakerIdentifier()
    return _speaker_identifier
