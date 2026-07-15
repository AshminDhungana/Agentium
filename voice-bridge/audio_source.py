"""Host microphone frame reader for the voice bridge.

Yields fixed-size 16 kHz / 16-bit mono PCM frames so the wake-word and VAD
stages can run continuously without speech_recognition's blocking listen().
"""
from __future__ import annotations

import threading
from typing import Optional

try:
    import pyaudio  # type: ignore
    _PYAUDIO_AVAILABLE = True
except Exception:
    pyaudio = None  # type: ignore
    _PYAUDIO_AVAILABLE = False


class MicrophoneSource:
    RATE = 16000
    FRAME_BYTES = 2560  # 80 ms @ 16 kHz / 16-bit mono

    def __init__(self, rate: int = RATE, frame_bytes: int = FRAME_BYTES):
        self.rate = rate
        self.frame_bytes = frame_bytes
        self._pa = None
        self._stream = None
        self._lock = threading.Lock()
        self._playback_ref: bytes = b""

    @property
    def available(self) -> bool:
        return _PYAUDIO_AVAILABLE

    def open(self) -> None:
        if not _PYAUDIO_AVAILABLE:
            raise RuntimeError("PyAudio not available")
        self._pa = pyaudio.PyAudio()
        self._stream = self._pa.open(
            format=pyaudio.paInt16,
            channels=1,
            rate=self.rate,
            input=True,
            frames_per_buffer=self.frame_bytes // 2,
        )

    def read_frame(self) -> bytes:
        if self._stream is None:
            raise RuntimeError("MicrophoneSource not opened")
        with self._lock:
            return self._stream.read(self.frame_bytes // 2, exception_on_overflow=False)

    def feed_playback(self, audio: bytes) -> None:
        """Provide the audio currently being played back, for AEC reference."""
        with self._lock:
            self._playback_ref = audio

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
        if self._pa is not None:
            try:
                self._pa.terminate()
            except Exception:
                pass
            self._pa = None
