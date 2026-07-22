"""Multi-provider TTS engine for Voice Bridge.

Supports Kokoro (offline) and OpenAI (cloud) providers.
synth(text) returns WAV bytes from the active provider.
play() streams audio to the host speaker via sounddevice; flush() aborts
playback queue for barge-in (<60ms target).
"""
from __future__ import annotations

import io
import os
import queue
import threading
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    from kokoro import KPipeline  # type: ignore
    _KOKORO_AVAILABLE = True
except Exception:
    KPipeline = None  # type: ignore
    _KOKORO_AVAILABLE = False

_DEFAULT_VOICE = os.getenv("VOICE_TTS_VOICE", "am_adam")
_DEFAULT_PROVIDER = os.getenv("VOICE_TTS_PROVIDER", "kokoro")


class KokoroProvider:
    def __init__(self):
        self._pipeline = None
        self._load_model()

    def _load_model(self):
        if not _KOKORO_AVAILABLE:
            return
        try:
            voice = _DEFAULT_VOICE
            self._pipeline = KPipeline(lang_code=voice[0])
        except Exception:
            self._pipeline = None

    @property
    def available(self) -> bool:
        return self._pipeline is not None

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        if not self._pipeline:
            raise RuntimeError("Kokoro not available")
        import soundfile as sf  # type: ignore
        out = io.BytesIO()
        try:
            for _, _, audio in self._pipeline(text, voice=voice, speed=speed):
                arr = audio.cpu().numpy() if hasattr(audio, "cpu") else audio
                sf.write(out, arr, 24000, format="WAV")
        except Exception:
            raise
        return out.getvalue()

    @property
    def voices(self) -> list[dict]:
        return [
            {"id": "am_adam", "name": "Adam", "gender": "male", "provider": "kokoro"},
            {"id": "af_heart", "name": "Heart", "gender": "female", "provider": "kokoro"},
            {"id": "af_bella", "name": "Bella", "gender": "female", "provider": "kokoro"},
            {"id": "bf_emma", "name": "Emma", "gender": "female", "provider": "kokoro"},
            {"id": "bm_george", "name": "George", "gender": "male", "provider": "kokoro"},
            {"id": "af_nicole", "name": "Nicole", "gender": "female", "provider": "kokoro"},
            {"id": "af_sarah", "name": "Sarah", "gender": "female", "provider": "kokoro"},
        ]


class OpenAIProvider:
    def __init__(self, api_key: str = ""):
        self._api_key = api_key
        self._client = None
        if api_key:
            self._init_client()

    def _init_client(self):
        try:
            import openai  # type: ignore
            self._client = openai.OpenAI(api_key=self._api_key)
        except Exception:
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    def synthesize(self, text: str, voice: str, speed: float = 1.0) -> bytes:
        if not self._client:
            raise RuntimeError("OpenAI not configured")
        from pydub import AudioSegment  # type: ignore
        response = self._client.audio.speech.create(
            model="tts-1", voice=voice, input=text, speed=speed
        )
        audio = AudioSegment.from_mp3(io.BytesIO(response.content))
        out = io.BytesIO()
        audio.export(out, format="wav")
        return out.getvalue()

    @property
    def voices(self) -> list[dict]:
        return [
            {"id": "alloy", "name": "Alloy", "gender": "neutral", "provider": "openai"},
            {"id": "echo", "name": "Echo", "gender": "male", "provider": "openai"},
            {"id": "fable", "name": "Fable", "gender": "male", "provider": "openai"},
            {"id": "onyx", "name": "Onyx", "gender": "male", "provider": "openai"},
            {"id": "nova", "name": "Nova", "gender": "female", "provider": "openai"},
            {"id": "shimmer", "name": "Shimmer", "gender": "female", "provider": "openai"},
        ]


class PlaybackQueue:
    def __init__(self):
        self._q: "queue.Queue[bytes]" = queue.Queue()
        self._abort = threading.Event()
        self._thread: Optional[threading.Thread] = None

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
    def __init__(self, voice: str = _DEFAULT_VOICE, provider: str = _DEFAULT_PROVIDER, openai_api_key: str = ""):
        self.voice = voice
        self.provider = provider
        self._kokoro = KokoroProvider()
        self._openai = OpenAIProvider(openai_api_key) if openai_api_key else OpenAIProvider()
        self.available = self._kokoro.available or self._openai.available
        self._samplerate = 24000
        self._queue = PlaybackQueue()
        self._player_thread = threading.Thread(
            target=self._queue.play_loop, args=(self._samplerate,), daemon=True
        )
        self._player_thread.start()

    def set_voice(self, voice: str, provider: Optional[str] = None):
        self.voice = voice
        if provider:
            self.provider = provider
        else:
            self.provider = self._detect_provider(voice)

    def set_provider(self, provider: str, openai_api_key: str = ""):
        self.provider = provider
        if provider == "openai" and openai_api_key:
            self._openai = OpenAIProvider(openai_api_key)

    def _detect_provider(self, voice: str) -> str:
        voice_lower = voice.lower()
        if ":" in voice:
            return voice.split(":")[0]
        if any(voice_lower.startswith(p) for p in ["am_", "af_", "bf_", "bm_", "ef_", "em_"]):
            return "kokoro"
        openai_voices = {"alloy", "echo", "fable", "onyx", "nova", "shimmer"}
        if voice_lower in openai_voices:
            return "openai"
        return self.provider

    def synth(self, text: str) -> bytes:
        if not self.available:
            return b""

        p = self._get_provider(self.provider)
        if not p or not p.available:
            p = self._get_provider("kokoro")
            if not p or not p.available:
                return b""

        try:
            return p.synthesize(text, self.voice)
        except Exception as e:
            logger.warning("[bridge] TTS synthesis failed: %s", e)
            return b""

    def _get_provider(self, name: str):
        if name == "kokoro":
            return self._kokoro
        elif name == "openai":
            return self._openai
        return None

    def play(self, audio: bytes):
        if not audio:
            return
        self._queue.put(audio)

    def flush(self):
        self._queue.abort()


_tts_engine_instance: Optional[TTSEngine] = None


def get_tts_engine(voice: str = _DEFAULT_VOICE, provider: str = _DEFAULT_PROVIDER, openai_api_key: str = "") -> TTSEngine:
    global _tts_engine_instance
    if _tts_engine_instance is None:
        _tts_engine_instance = TTSEngine(voice, provider, openai_api_key)
    return _tts_engine_instance
