"""Speech/silence detection (Silero VAD) + dynamic endpointing + AEC + NS.

push_frame() buffers 80 ms frames into 512-sample windows and returns the
latest speech probability. should_endpoint() decides when to close the user's
turn based on silence duration AND syntactic completeness of the partial
transcript, so quiet talkers aren't cut and "um"-ending phrases aren't closed
prematurely. apply_aec() cancels played-back audio from the mic (barge-in,
Phase C); apply_noise_suppression() reduces HVAC/appliance noise (Phase H).
"""
from __future__ import annotations

import os
from typing import Optional

import numpy as np

_SILENCE_BASE_MS = float(os.getenv("VAD_SILENCE_MS", "700"))
_NS_ENABLED = os.getenv("VOICE_NS_ENABLED", "true").lower() == "true"

try:
    from silero_vad import load_silero, VADIterator  # type: ignore
    _SILERO_AVAILABLE = True
except Exception:
    load_silero = None  # type: ignore
    VADIterator = None  # type: ignore
    _SILERO_AVAILABLE = False

try:
    from webrtc_audio_processing import Aec  # type: ignore
    _AEC_AVAILABLE = True
except Exception:
    Aec = None  # type: ignore
    _AEC_AVAILABLE = False

try:
    import noisereduce as nr  # type: ignore
    _NS_AVAILABLE = True
except Exception:
    nr = None  # type: ignore
    _NS_AVAILABLE = False


def _load_silero():
    try:
        return load_silero()
    except Exception:
        return None


_INCOMPLETE_TAILS = ("and", "the", "or", "but", "so", "to", "a", "an", "of", "with", "that", "which")


class VAD:
    def __init__(self, threshold: float = 0.5, silence_base_ms: float = _SILENCE_BASE_MS,
                 noise_suppression: bool = _NS_ENABLED):
        self.threshold = threshold
        self.silence_base_ms = silence_base_ms
        self.noise_suppression = noise_suppression and _NS_AVAILABLE
        self.available = _SILERO_AVAILABLE
        self._model = _load_silero() if _SILERO_AVAILABLE else None
        self._iter = VADIterator(self._model) if self._model is not None else None
        self._buf = np.zeros(0, dtype=np.int16)

    def push_frame(self, frame: bytes) -> Optional[float]:
        if not self.available or self._iter is None:
            return None
        if self.noise_suppression:
            frame = self.apply_noise_suppression(frame)
        samples = np.frombuffer(frame, dtype=np.int16)
        self._buf = np.concatenate([self._buf, samples])
        last = 0.0
        while len(self._buf) >= 512:
            window = self._buf[:512].copy()
            self._buf = self._buf[512:]
            try:
                result = self._iter(window)
            except Exception:
                result = {}
            last = 1.0 if result else 0.0
        return last

    def is_speech(self, score: Optional[float]) -> bool:
        return score is not None and score >= self.threshold

    @staticmethod
    def should_endpoint(partial_text: str, silence_ms: int, base_silence_ms: float) -> bool:
        text = (partial_text or "").strip().lower().rstrip(".,!?")
        if not text:
            return silence_ms >= base_silence_ms
        tail = text.split()[-1] if text.split() else ""
        if tail in _INCOMPLETE_TAILS:
            # Syntactically incomplete — extend patience by 60%.
            return silence_ms >= base_silence_ms * 1.6
        return silence_ms >= base_silence_ms

    def apply_aec(self, mic_frame: bytes, playback_frame: bytes) -> bytes:
        """Echo-cancel played-back audio from the mic signal (Phase C)."""
        if not _AEC_AVAILABLE:
            return mic_frame
        try:
            aec = Aec()
            out = aec.process(playback_frame, mic_frame)
            return out
        except Exception:
            return mic_frame

    def apply_noise_suppression(self, frame: bytes) -> bytes:
        if not _NS_AVAILABLE:
            return frame
        try:
            sig = np.frombuffer(frame, dtype=np.int16).astype(np.float32)
            red = nr.reduce_noise(y=sig, sr=16000)
            return np.clip(red, -32768, 32767).astype(np.int16).tobytes()
        except Exception:
            return frame
