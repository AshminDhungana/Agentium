"""Local neural TTS (Kokoro-82M) with pyttsx3 + WS-broadcast fallback.

synth(text) returns WAV bytes from Kokoro when available; otherwise b"" and
the caller falls back to pyttsx3 (blocking) or a text-only WS broadcast.
play() streams audio to the host speaker via sounddevice; flush() aborts the
playback queue for barge-in (<60ms target).
"""
from __future__ import annotations

import os
import queue
import threading
from typing import Optional

try:
    from kokoro import KPipeline  # type: ignore
    _KOKORO_AVAILABLE = True
except Exception:
    KPipeline = None  # type: ignore
    _KOKORO_AVAILABLE = False

_VOICE = os.getenv("VOICE_TTS_VOICE", "af_bella")


def _load_kokoro():
    if not _KOKORO_AVAILABLE:
        return None, None
    try:
        pipe = KPipeline(lang_code=_VOICE[0])  # 'a' for af_*, 'b' for bf_*, etc.
        return pipe, _VOICE
    except Exception:
        return None, None


class PlaybackQueue:
    def __init__(self):
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._abort = threading.Event()
        self._thread = None

    @property
    def aborted(self) -> bool:
        return self._abort.is_set()

    def put(self, audio: bytes):
        self._q.put(audio)

    def abort(self):
        self._abort.set()
        try:
            while True:
                self._q.get_nowait()
        except queue.Empty:
            pass

    def play_loop(self, samplerate: int):
        try:
            import sounddevice as sd  # type: ignore
            import numpy as np
        except Exception:
            return
        self._abort.clear()
        while not self._abort.is_set():
            try:
                audio = self._q.get(timeout=0.05)
            except queue.Empty:
                continue
            arr = np.frombuffer(audio, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(arr, samplerate)
            sd.wait()
            if self._abort.is_set():
                try:
                    sd.stop()
                except Exception:
                    pass
                break


class TTSEngine:
    def __init__(self, voice: str = _VOICE):
        self._pipeline, self._kokoro_voice = _load_kokoro()
        self.available = self._pipeline is not None
        self._samplerate = 24000
        self._queue = PlaybackQueue()
        self._player_thread = threading.Thread(
            target=self._queue.play_loop, args=(self._samplerate,), daemon=True
        )
        self._player_thread.start()

    def synth(self, text: str) -> bytes:
        if not self.available:
            return b""  # caller falls back to pyttsx3 / WS
        import io
        import soundfile as sf  # type: ignore
        out = io.BytesIO()
        try:
            for _, _, audio in self._pipeline(text, voice=self._kokoro_voice):
                arr = audio.cpu().numpy() if hasattr(audio, "cpu") else audio
                sf.write(out, arr, self._samplerate, format="WAV")
        except Exception:
            return b""
        return out.getvalue()

    def play(self, audio: bytes):
        if not audio:
            return
        self._queue.put(audio)

    def flush(self):
        self._queue.abort()
