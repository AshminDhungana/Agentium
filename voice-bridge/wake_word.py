"""Streaming wake-word detection via openWakeWord.

Buffers 80 ms mic frames into 1 s windows and runs openWakeWord inference.
Degrades to `available=False` if the library or model is missing so the
caller can fall back to REQUIRE_WAKE_WORD=false behavior.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Optional

import numpy as np

_WAKE_MODEL_ENV = os.getenv("WAKE_WORD_MODEL") or (Path.home() / ".agentium" / "openwakeword").as_posix()
_WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.5"))


def _load_model(model_path: Optional[str]):
    try:
        from openwakeword.model import Model  # type: ignore
        names = None
        if model_path and Path(model_path).is_file():
            names = [Path(model_path).name]
        return Model(wake_word_names=names)
    except Exception:
        return None


class WakeWordDetector:
    def __init__(self, model_path: Optional[str] = None):
        self._model = _load_model(model_path or _WAKE_MODEL_ENV)
        self.available = self._model is not None
        self._buf = np.zeros(0, dtype=np.int16)
        self.threshold = _WAKE_WORD_THRESHOLD

    def push_frame(self, frame: bytes) -> Optional[float]:
        """Append one 80 ms frame; return best score once 1 s is buffered."""
        if not self.available:
            return None
        samples = np.frombuffer(frame, dtype=np.int16)
        self._buf = np.concatenate([self._buf, samples])
        if len(self._buf) < 16000:
            return None
        window = self._buf[:16000].copy()
        self._buf = self._buf[16000:]  # slide, keep remainder
        try:
            scores: Dict[str, float] = self._model.predict(window)
        except Exception:
            return None
        return self.best_score(scores)

    @staticmethod
    def best_score(scores: Dict[str, float]) -> float:
        return max(scores.values()) if scores else 0.0

    def is_triggered(self, score: Optional[float]) -> bool:
        return score is not None and score >= self.threshold
