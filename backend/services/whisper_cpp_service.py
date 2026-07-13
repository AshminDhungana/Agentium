"""Local speech-to-text via whisper.cpp (whisper-cli subprocess).

Primary STT engine for Agentium. Runs the compiled ``whisper-cli`` binary
and parses its stdout. The caller's fallback chain (see
``backend.services.audio_service.AudioService.transcribe``) moves on to
OpenAI / browser-native when this raises ``LocalSTTError``.
"""
from __future__ import annotations

import asyncio
import ctypes
import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ── Config (env, with defaults) ──────────────────────────────────────────────
WHISPER_CPP_BIN = os.getenv("WHISPER_CPP_BIN", "/usr/local/bin/whisper-cli")
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base.en")
WHISPER_MODEL_DIR = os.getenv("WHISPER_MODEL_DIR", "/opt/whisper/models")
WHISPER_TIMEOUT = float(os.getenv("WHISPER_TIMEOUT", "60"))
WHISPER_MAX_CONCURRENCY = int(os.getenv("WHISPER_MAX_CONCURRENCY", "1"))


class LocalSTTError(Exception):
    """whisper.cpp local STT failed (missing binary/model, crash, timeout)."""


def _model_path() -> Path:
    return Path(WHISPER_MODEL_DIR) / f"ggml-{WHISPER_MODEL}.bin"


def _gpu_available() -> bool:
    """Best-effort: is an NVIDIA GPU usable at runtime?

    A privileged container run with ``--gpus all`` has nvidia-container-toolkit
    mount ``/dev/nvidia0`` and ``libcuda.so.1``. Without them this is False.
    """
    if not os.path.exists("/dev/nvidia0"):
        return False
    try:
        ctypes.CDLL("libcuda.so.1")
        return True
    except OSError:
        return False


class WhisperCppService:
    def __init__(self) -> None:
        self._lock: Optional[asyncio.Lock] = None
        self._gpu = _gpu_available()
        logger.info(
            "[STT] whisper.cpp backend=%s bin=%s model=%s",
            "GPU" if self._gpu else "CPU", WHISPER_CPP_BIN, WHISPER_MODEL,
        )

    def is_available(self) -> bool:
        return Path(WHISPER_CPP_BIN).is_file() and _model_path().is_file()

    async def transcribe(
        self, audio_bytes: bytes, language: Optional[str] = None
    ) -> str:
        if not self.is_available():
            raise LocalSTTError("whisper.cpp binary or model not found")

        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp.write(audio_bytes)
                tmp_path = tmp.name
            try:
                cmd = [
                    WHISPER_CPP_BIN, "-m", str(_model_path()),
                    "-f", tmp_path, "--output-txt", "-np",
                ]
                if language:
                    cmd += ["-l", language]
                try:
                    proc = await asyncio.to_thread(
                        subprocess.run, cmd,
                        text=True, capture_output=True, timeout=WHISPER_TIMEOUT,
                    )
                except subprocess.TimeoutExpired as exc:
                    raise LocalSTTError(
                        f"whisper.cpp timed out after {WHISPER_TIMEOUT}s"
                    ) from exc
                if proc.returncode != 0:
                    raise LocalSTTError(
                        f"whisper-cli exited {proc.returncode}: {proc.stderr[:500]}"
                    )
                text = (proc.stdout or "").strip()
                if not text:
                    raise LocalSTTError("whisper.cpp returned empty transcription")
                return text
            finally:
                Path(tmp_path).unlink(missing_ok=True)


_service: Optional[WhisperCppService] = None


def get_whisper_cpp_service() -> WhisperCppService:
    """Return the singleton WhisperCppService (lazy init)."""
    global _service
    if _service is None:
        _service = WhisperCppService()
    return _service
