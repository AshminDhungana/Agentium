"""Host microphone frame reader for the voice bridge.

Yields fixed-size 16 kHz / 16-bit mono PCM frames so the wake-word and VAD
stages can run continuously without speech_recognition's blocking listen().
Supports PyAudio (preferred) and sounddevice (fallback with Python 3.14 wheels).
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

try:
    import pyaudio  # type: ignore
    _PYAUDIO_AVAILABLE = True
except Exception:
    pyaudio = None  # type: ignore
    _PYAUDIO_AVAILABLE = False

try:
    import sounddevice as sd  # type: ignore
    import numpy as np
    _SOUNDDEVICE_AVAILABLE = True
except Exception:
    sd = None  # type: ignore
    np = None  # type: ignore
    _SOUNDDEVICE_AVAILABLE = False


class _PyAudioImpl:
    """Microphone backend using PyAudio (legacy, widely compatible)."""

    def __init__(self, rate: int, frame_bytes: int):
        self.rate = rate
        self.frame_bytes = frame_bytes
        self._pa: Optional[pyaudio.PyAudio] = None
        self._stream = None

    def open(self) -> None:
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
            raise RuntimeError("PyAudio backend not opened")
        return self._stream.read(self.frame_bytes // 2, exception_on_overflow=False)

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


class _SoundDeviceImpl:
    """Microphone backend using sounddevice (modern, Python 3.12+ wheels)."""

    def __init__(self, rate: int, frame_bytes: int):
        self.rate = rate
        self.frame_bytes = frame_bytes
        self._stream: Optional[sd.InputStream] = None
        self._queue: queue.Queue = queue.Queue()

    def open(self) -> None:
        self._stream = sd.InputStream(
            samplerate=self.rate,
            channels=1,
            dtype="int16",
            blocksize=self.frame_bytes // 2,
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time, status) -> None:
        if status:
            pass
        self._queue.put(indata.copy().tobytes())

    def read_frame(self) -> bytes:
        return self._queue.get()

    def close(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None


class MicrophoneSource:
    RATE = 16000
    FRAME_BYTES = 2560  # 80 ms @ 16 kHz / 16-bit mono

    def __init__(self, rate: int = RATE, frame_bytes: int = FRAME_BYTES):
        self.rate = rate
        self.frame_bytes = frame_bytes
        self._impl: Optional[object] = None

    @property
    def available(self) -> bool:
        return _PYAUDIO_AVAILABLE or _SOUNDDEVICE_AVAILABLE

    def open(self) -> None:
        if _PYAUDIO_AVAILABLE:
            self._impl = _PyAudioImpl(self.rate, self.frame_bytes)
        elif _SOUNDDEVICE_AVAILABLE:
            self._impl = _SoundDeviceImpl(self.rate, self.frame_bytes)
        else:
            raise RuntimeError("No audio backend available - install PyAudio >= 0.2.14 or sounddevice >= 0.4.6")
        self._impl.open()

    def read_frame(self) -> bytes:
        if self._impl is None:
            raise RuntimeError("MicrophoneSource not opened")
        return self._impl.read_frame()

    def feed_playback(self, audio: bytes) -> None:
        pass

    def close(self) -> None:
        if self._impl is not None:
            self._impl.close()
            self._impl = None
