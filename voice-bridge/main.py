"""
voice-bridge/main.py — Agentium SecureVoiceBridge
==================================================
Runs on the HOST (outside Docker).  Connects to the backend inside Docker
via HTTP, streams microphone input through STT, sends text to the Head of
Council, speaks the reply with TTS, and pushes the exchange to the browser
via a local WebSocket server on 127.0.0.1:9999.

Start:  python voice-bridge/main.py

── Session-mode wake word behaviour ──────────────────────────────────────────
When REQUIRE_WAKE_WORD=true (default):

  1. Bridge listens passively for the wake word ("agentium").
  2. On detection it says "Yes, how can I help?" and enters SESSION MODE.
  3. In session mode the user can speak commands back-to-back without
     repeating the wake word.  The bridge stays active as long as the user
     keeps talking.
  4. The session ends when:
       a. No speech is heard for SESSION_NO_SPEECH_TIMEOUT seconds  (default 8)
          after the wake word OR after a reply has been spoken, OR
       b. The total session wall-clock time exceeds SESSION_MAX_DURATION
          seconds (default 120).
  5. On session end the bridge returns to passive wake-word listening.

Timing constants (all configurable via env.conf or environment variables):

  SESSION_PAUSE_THRESHOLD      = 1.5s  — silence inside a phrase that marks
                                          end-of-speech. Industry standard from
                                          O'Reilly "Designing Voice User
                                          Interfaces"; Google/Alexa use 1–1.5s.
  SESSION_NO_SPEECH_TIMEOUT    = 8s   — how long to wait for speech to start
                                          after the wake word or after a reply.
                                          Amazon Alexa uses 8s; research
                                          recommends 8–10s for NSP timeout.
  SESSION_MAX_DURATION         = 120s — hard cap on total session length to
                                          prevent runaway microphone capture.
  WAKE_WORD_LISTEN_TIMEOUT     = 8s   — how long each passive listen call
                                          blocks before looping back; keep ≤10s
                                          so KeyboardInterrupt stays responsive.

"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional, Tuple

# ── Jarvis-upgrade module imports (Phases A–H) ──────────────────────────────
# These modules guard their heavy deps internally, so importing them is safe
# even when openWakeWord/Silero/Kokoro are not installed on the host. vad and
# tts_engine are imported lazily inside _run_voice_loop_once so the bridge can
# be imported (and wake-word mode exercised) before those modules land.
from audio_source import MicrophoneSource
from wake_word import WakeWordDetector

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("voice-bridge")

# Thread pool for blocking STT / TTS calls
_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="voice-io")

# ── Read env.conf ──────────────────────────────────────────────────────────────

_ENV_CONF = Path.home() / ".agentium" / "env.conf"


def _load_env_conf() -> dict:
    conf: dict = {}
    try:
        for line in _ENV_CONF.read_text().splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                conf[k.strip()] = v.strip()
        logger.info("[bridge] env.conf loaded from %s", _ENV_CONF)
    except Exception as exc:
        logger.warning("[WARN] Could not read %s: %s — using defaults", _ENV_CONF, exc)
    return conf


_conf = _load_env_conf()

BACKEND_URL:       str  = _conf.get("BACKEND_URL",       os.getenv("BACKEND_URL",       "http://127.0.0.1:8000"))
WS_PORT:           int  = int(_conf.get("WS_PORT",        os.getenv("WS_PORT",           "9999")))
WAKE_WORD:         str  = _conf.get("WAKE_WORD",          os.getenv("WAKE_WORD",          "agentium")).lower()
VOICE_TOKEN:       str  = _conf.get("VOICE_TOKEN",        os.getenv("VOICE_TOKEN",        ""))
# Set REQUIRE_WAKE_WORD=false in env.conf to skip the wake-word step entirely
REQUIRE_WAKE_WORD: bool = _conf.get("REQUIRE_WAKE_WORD",  os.getenv("REQUIRE_WAKE_WORD",  "true")).lower() == "true"

# ── Session timing constants ───────────────────────────────────────────────────
# All values can be overridden in env.conf or via environment variables.
# See module docstring for rationale behind the defaults.

SESSION_PAUSE_THRESHOLD:   float = float(_conf.get("SESSION_PAUSE_THRESHOLD",   os.getenv("SESSION_PAUSE_THRESHOLD",   "1.5")))
SESSION_NO_SPEECH_TIMEOUT: float = float(_conf.get("SESSION_NO_SPEECH_TIMEOUT", os.getenv("SESSION_NO_SPEECH_TIMEOUT", "8.0")))
SESSION_MAX_DURATION:      float = float(_conf.get("SESSION_MAX_DURATION",      os.getenv("SESSION_MAX_DURATION",      "120.0")))
WAKE_WORD_LISTEN_TIMEOUT:  float = float(_conf.get("WAKE_WORD_LISTEN_TIMEOUT",  os.getenv("WAKE_WORD_LISTEN_TIMEOUT",  "8.0")))

# ── Jarvis-upgrade config (Phases A–H) ──────────────────────────────────────
WAKE_CHIME_PATH:      str   = _conf.get("WAKE_CHIME_PATH",      os.getenv("WAKE_CHIME_PATH",      str(Path(__file__).parent / "assets" / "wake_chime.wav")))
WAKE_WORD_MODEL:      str   = _conf.get("WAKE_WORD_MODEL",      os.getenv("WAKE_WORD_MODEL",      ""))
WAKE_WORD_THRESHOLD:  float = float(_conf.get("WAKE_WORD_THRESHOLD", os.getenv("WAKE_WORD_THRESHOLD", "0.5")))
VAD_SILENCE_MS:       float = float(_conf.get("VAD_SILENCE_MS",       os.getenv("VAD_SILENCE_MS",       "700")))
VOICE_TTS_VOICE:      str   = _conf.get("VOICE_TTS_VOICE",      os.getenv("VOICE_TTS_VOICE",      "af_bella"))
VOICE_PERSONA:        str   = _conf.get("VOICE_PERSONA",        os.getenv("VOICE_PERSONA",        ""))
VOICE_PROACTIVE_ENABLED: bool = _conf.get("VOICE_PROACTIVE_ENABLED", os.getenv("VOICE_PROACTIVE_ENABLED", "false")).lower() == "true"
VOICE_PROACTIVE_COOLDOWN_S: float = float(_conf.get("VOICE_PROACTIVE_COOLDOWN_S", os.getenv("VOICE_PROACTIVE_COOLDOWN_S", "300")))
VOICE_NS_ENABLED:     bool  = _conf.get("VOICE_NS_ENABLED",     os.getenv("VOICE_NS_ENABLED",     "true")).lower() == "true"
BACKEND_WS_URL:       str   = _conf.get("BACKEND_WS_URL",       os.getenv("BACKEND_WS_URL",       f"ws://{BACKEND_URL.split('://')[-1].split(':')[0]}:8000/ws"))

# ── Vosk offline-fallback config (B1/B2) ───────────────────────────────────────
# Only used when recognize_google() fails with a RequestError (network/quota/
# 5xx from Google) AND a model directory is present. If no model is found,
# the bridge logs once and continues with Google as the sole engine — exactly
# today's behavior. This is additive, not a replacement.
VOSK_MODEL_PATH: str = _conf.get("VOSK_MODEL_PATH", os.getenv("VOSK_MODEL_PATH", str(Path.home() / ".agentium" / "vosk-model")))

# ── Backend STT relay (whisper.cpp) ────────────────────────────────────────────
# The host bridge captures mic audio and relays it to the backend, which now
# runs whisper.cpp locally. Falls back to the offline Vosk model only if the
# backend STT call fails (backend unreachable / whisper.cpp missing).
STT_BACKEND_URL: str = _conf.get(
    "STT_BACKEND_URL", os.getenv("STT_BACKEND_URL", f"{BACKEND_URL}/api/v1/audio/transcribe")
)
WHISPER_RELAY_TIMEOUT: float = float(_conf.get("WHISPER_RELAY_TIMEOUT", os.getenv("WHISPER_RELAY_TIMEOUT", "30.0")))

# ── Backend call resilience config (B4/R1) ─────────────────────────────────────
BACKEND_QUERY_RETRIES:    int   = int(_conf.get("BACKEND_QUERY_RETRIES",    os.getenv("BACKEND_QUERY_RETRIES",    "2")))
BACKEND_QUERY_RETRY_WAIT: float = float(_conf.get("BACKEND_QUERY_RETRY_WAIT", os.getenv("BACKEND_QUERY_RETRY_WAIT", "1.5")))

# ── Subsystem supervisor config (B5) ────────────────────────────────────────────
SUPERVISOR_RESTART_DELAY: float = float(_conf.get("SUPERVISOR_RESTART_DELAY", os.getenv("SUPERVISOR_RESTART_DELAY", "3.0")))

logger.info(
    "[bridge] BACKEND_URL=%s  WS_PORT=%d  WAKE_WORD='%s'  REQUIRE_WAKE_WORD=%s",
    BACKEND_URL, WS_PORT, WAKE_WORD, REQUIRE_WAKE_WORD,
)
logger.info(
    "[bridge] Session timing — pause_threshold=%.1fs  no_speech_timeout=%.1fs  max_duration=%.0fs",
    SESSION_PAUSE_THRESHOLD, SESSION_NO_SPEECH_TIMEOUT, SESSION_MAX_DURATION,
)

# ── Optional dependency guards ─────────────────────────────────────────────────

SR_AVAILABLE     = False
TTS_AVAILABLE    = False
WS_LIB_AVAILABLE = False
VOSK_AVAILABLE   = False

try:
    import speech_recognition as sr
    SR_AVAILABLE = True
    logger.info("[bridge] SpeechRecognition available")
except ImportError:
    logger.warning("[WARN] SpeechRecognition not installed — voice capture disabled")

try:
    import pyttsx3
    TTS_AVAILABLE = True
    logger.info("[bridge] pyttsx3 available")
except ImportError:
    logger.warning("[WARN] pyttsx3 not installed — TTS disabled")

try:
    import websockets
    WS_LIB_AVAILABLE = True
    logger.info("[bridge] websockets library available")
except ImportError:
    logger.warning("[WARN] websockets not installed — browser sync disabled")

try:
    import vosk  # noqa: F401  (presence check only — model load happens lazily below)
    VOSK_AVAILABLE = True
    logger.info("[bridge] vosk library available")
except ImportError:
    logger.info("[bridge] vosk not installed — offline STT fallback disabled (backend whisper.cpp only)")

import urllib.request
import urllib.error

# ── Vosk lazy model loader (B1/B2) ─────────────────────────────────────────────

_vosk_model = None
_vosk_model_load_attempted = False


def _get_vosk_model():
    """
    Lazily load the Vosk model exactly once. Returns None (and logs once) if
    the model directory doesn't exist or fails to load — callers must treat
    None as "fallback unavailable, keep going with Google only."
    """
    global _vosk_model, _vosk_model_load_attempted
    if not VOSK_AVAILABLE:
        return None
    if _vosk_model_load_attempted:
        return _vosk_model
    _vosk_model_load_attempted = True

    model_dir = Path(VOSK_MODEL_PATH)
    if not model_dir.is_dir():
        logger.info(
            "[bridge] No Vosk model found at %s — offline STT fallback disabled "
            "(download a model and set VOSK_MODEL_PATH to enable it)",
            model_dir,
        )
        return None

    try:
        import vosk
        vosk.SetLogLevel(-1)  # suppress Vosk's own noisy stdout logging
        _vosk_model = vosk.Model(str(model_dir))
        logger.info("[bridge] Vosk offline STT model loaded from %s", model_dir)
    except Exception as exc:
        logger.warning("[WARN] Vosk model failed to load from %s: %s — fallback disabled", model_dir, exc)
        _vosk_model = None
    return _vosk_model


# Vosk's published models (vosk-model-small-en-us, vosk-model-en-us, etc.) are
# all trained at 16 kHz, 16-bit mono — feeding them anything else silently
# degrades accuracy. speech_recognition's AudioData.get_raw_data() can
# resample for us via convert_rate/convert_width, so we always normalize to
# this rate/width regardless of what the microphone itself captured at.
VOSK_SAMPLE_RATE = 16000
VOSK_SAMPLE_WIDTH = 2  # bytes (16-bit PCM)


def _recognize_with_vosk(audio: "sr.AudioData") -> Optional[str]:
    """
    Transcribe an already-captured AudioData object using the local Vosk
    model. Returns None on any failure (model missing, decode error, no
    speech recognized) so the caller can fall back to "no speech detected"
    semantics identical to a Google STT miss.
    """
    model = _get_vosk_model()
    if model is None:
        return None

    try:
        import vosk
        rec = vosk.KaldiRecognizer(model, VOSK_SAMPLE_RATE)
        rec.SetWords(False)
        # Resample to 16kHz/16-bit regardless of the mic's native capture
        # rate — Vosk's bundled models expect this specific format.
        raw = audio.get_raw_data(convert_rate=VOSK_SAMPLE_RATE, convert_width=VOSK_SAMPLE_WIDTH)
        rec.AcceptWaveform(raw)
        result = json.loads(rec.FinalResult())
        text = (result.get("text") or "").strip()
        return text or None
    except Exception as exc:
        logger.warning("[WARN] Vosk transcription failed: %s", exc)
        return None


def _transcribe_via_backend(audio_wav: bytes) -> Optional[str]:
    """
    Relay WAV audio bytes to the backend's whisper.cpp STT endpoint.

    Returns the transcript string, or None if the backend call fails (in
    which case the caller falls back to the offline Vosk model). The backend
    requires an authenticated user; the bridge sends its VOICE_TOKEN.
    """
    import urllib.request
    import urllib.error

    if not VOICE_TOKEN:
        logger.debug("[bridge] No VOICE_TOKEN — cannot call backend STT")
        return None
    try:
        req = urllib.request.Request(
            STT_BACKEND_URL,
            data=audio_wav,
            headers={
                "Content-Type": "audio/wav",
                "Authorization": f"Bearer {VOICE_TOKEN}",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=WHISPER_RELAY_TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            text = (body.get("text") or "").strip()
            return text or None
    except Exception as exc:
        logger.warning("[WARN] Backend STT relay failed: %s — using Vosk", exc)
        return None


# ── TTS ────────────────────────────────────────────────────────────────────────

_tts_engine = None


def _get_tts():
    global _tts_engine
    if not TTS_AVAILABLE:
        return None
    if _tts_engine is None:
        try:
            _tts_engine = pyttsx3.init()
            logger.info("[bridge] TTS engine initialised")
        except Exception as exc:
            logger.warning("[WARN] TTS engine init failed: %s", exc)
    return _tts_engine


def _speak_sync(text: str) -> None:
    """Blocking TTS — runs in thread executor."""
    engine = _get_tts()
    if not engine:
        logger.info("[bridge][TTS-FALLBACK] %s", text)
        return
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        logger.warning("[WARN] TTS speak failed: %s", exc)


async def speak(text: str) -> None:
    """Non-blocking async wrapper around _speak_sync."""
    loop = asyncio.get_event_loop()
    await loop.run_in_executor(_executor, _speak_sync, text)


def _play_wake_chime() -> None:
    """Instant, non-LLM acknowledgment that the wake word was heard."""
    path = WAKE_CHIME_PATH
    if not os.path.isfile(path):
        logger.debug("[bridge] wake chime asset missing at %s", path)
        return
    try:
        import wave
        with wave.open(path, "rb") as w:
            data = w.readframes(w.getnframes())
        try:
            import sounddevice as sd  # type: ignore
            import numpy as np
            arr = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
            sd.play(arr, w.getframerate())
            sd.wait()
        except Exception:
            logger.debug("[bridge] sounddevice unavailable for chime")
    except Exception as exc:
        logger.debug("[bridge] wake chime play failed: %s", exc)


_tts_engine_instance = None


def _get_tts_engine() -> "TTSEngine":
    """Lazily construct and cache the Kokoro-backed TTS engine."""
    global _tts_engine_instance
    if _tts_engine_instance is None:
        from tts_engine import TTSEngine
        _tts_engine_instance = TTSEngine(VOICE_TTS_VOICE)
    return _tts_engine_instance


async def _speak_fallback(text: str) -> None:
    """Used when Kokoro is unavailable: pyttsx3 TTS + text-only WS broadcast."""
    await speak(text)
    await _broadcast({"type": "voice_tts_broadcast", "text": text, "ts": time.time()})


def _load_persona() -> Optional[str]:
    """Default Jarvis persona, overridable by VOICE_PERSONA env / persona.md."""
    if VOICE_PERSONA:
        return VOICE_PERSONA
    p = Path(__file__).parent / "persona.md"
    if p.is_file():
        return p.read_text().strip() or None
    return None


class ProactiveAnnouncer:
    """Rate-limited, quiet-hours-aware proactive voice announcements.

    Subscribes to a narrow slice of the backend WS event bus and speaks a
    one-line summary for an allow-listed subset of event types. Off by default
    (VOICE_PROACTIVE_ENABLED=false). Never announces during quiet hours and
    never repeats the same event class within COOLDOWN_S seconds.
    """

    ALLOWED = {"agent_crashed", "budget_exceeded", "sla_breach", "task_escalated"}
    SUMMARIES = {
        "agent_crashed": "Heads up — an agent just crashed and is being recovered.",
        "budget_exceeded": "Budget threshold reached on a model key.",
        "sla_breach": "A service-level agreement was breached.",
        "task_escalated": "A task was escalated to a higher tier.",
    }
    COOLDOWN_S = float(os.getenv("VOICE_PROACTIVE_COOLDOWN_S", "300"))

    def __init__(self):
        self.enabled = VOICE_PROACTIVE_ENABLED
        self._last: dict = {}

    def _in_quiet_hours(self) -> bool:
        start = os.getenv("BUSINESS_HOURS_START")
        end = os.getenv("BUSINESS_HOURS_END")
        if not start or not end:
            return False
        try:
            h = time.localtime().tm_hour
            s, e = int(start), int(end)
            return not (s <= h < e)
        except Exception:
            return False

    def maybe_announce(self, event_type: str) -> Optional[str]:
        if not self.enabled or event_type not in self.ALLOWED:
            return None
        if self._in_quiet_hours():
            return None
        now = time.monotonic()
        if now - self._last.get(event_type, 0) < self.COOLDOWN_S:
            return None
        self._last[event_type] = now
        return self.SUMMARIES.get(event_type)


async def _run_backend_ws(announcer: "ProactiveAnnouncer") -> None:
    """Connect to the backend WS event bus and announce allowed events.

    Runs as a supervised coroutine alongside the voice loop. No-op if the
    websockets library or backend WS is unavailable, or proactive mode is off.
    """
    if not WS_LIB_AVAILABLE or not announcer.enabled:
        logger.info("[bridge] Proactive announcements disabled — backend WS client idle")
        await asyncio.Future()
        return
    import json as _json
    import websockets  # type: ignore

    async with websockets.connect(BACKEND_WS_URL) as ws:  # type: ignore
        logger.info("[bridge] Connected to backend WS event bus: %s", BACKEND_WS_URL)
        async for raw in ws:
            try:
                msg = _json.loads(raw)
            except (ValueError, TypeError):
                continue
            etype = msg.get("type") or msg.get("event")
            line = announcer.maybe_announce(etype)
            if line:
                await _speak_fallback(line)


# ── STT ────────────────────────────────────────────────────────────────────────

# R2: tracks whether the last listen attempt failed due to missing/unusable
# microphone hardware, so the passive wake-word loop can back off instead of
# hot-looping at full WAKE_WORD_LISTEN_TIMEOUT cadence forever.
_last_mic_error_at: Optional[float] = None
MIC_ERROR_BACKOFF_SECONDS = 30.0


def _listen_sync(
    timeout: float = 8.0,
    phrase_time_limit: float = 15.0,
    pause_threshold: float = 0.8,
) -> Optional[str]:
    """
    Blocking mic capture + STT.

    Parameters
    ----------
    timeout:
        Seconds to wait for any speech to begin before returning None.
        Use WAKE_WORD_LISTEN_TIMEOUT for passive listening, and
        SESSION_NO_SPEECH_TIMEOUT for in-session listening.
    phrase_time_limit:
        Maximum seconds for a single utterance.
    pause_threshold:
        Seconds of trailing silence that mark end-of-speech.
        Use SESSION_PAUSE_THRESHOLD (1.5s) during a session so the bridge
        doesn't cut the user off mid-thought. Use 0.8s for wake-word
        scanning where speed matters more.

    Returns the transcribed string or None on timeout / unrecognised audio.
    """
    global _last_mic_error_at

    if not SR_AVAILABLE:
        return None

    # R2: if the microphone was unusable very recently, don't hammer the OS
    # audio layer at full speed — back off so logs/CPU don't spin uselessly
    # for a user who simply has no mic attached.
    if _last_mic_error_at is not None and (time.monotonic() - _last_mic_error_at) < MIC_ERROR_BACKOFF_SECONDS:
        return None

    recognizer = sr.Recognizer()
    recognizer.energy_threshold         = 300
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold          = pause_threshold

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            logger.info(
                "[bridge] 🎙 Listening (timeout=%.1fs, phrase_limit=%.1fs, pause=%.1fs)…",
                timeout, phrase_time_limit, pause_threshold,
            )
            audio = recognizer.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
    except OSError as exc:
        # R2: distinct from STT-API failures — this means no microphone
        # hardware is available at all. Log once distinctly and start the
        # backoff window so the passive loop doesn't retry at full speed.
        if _last_mic_error_at is None:
            logger.error(
                "[ERROR] No usable microphone detected (%s). Voice input will stay "
                "disabled for %.0fs before retrying — check hardware/permissions.",
                exc, MIC_ERROR_BACKOFF_SECONDS,
            )
        _last_mic_error_at = time.monotonic()
        return None
    except sr.WaitTimeoutError:
        logger.debug("[bridge] Listen timeout — no speech detected")
        return None
    except Exception as exc:
        logger.warning("[WARN] Unexpected mic error: %s", exc)
        return None

    # Microphone worked this time — clear any prior backoff state.
    _last_mic_error_at = None

    logger.debug("[bridge] Audio captured, sending to backend STT (whisper.cpp)…")
    audio_wav = audio.get_wav_data()
    text = _transcribe_via_backend(audio_wav)
    if text:
        logger.info("[bridge] STT result (backend whisper.cpp): '%s'", text)
        return text
    # Backend STT unreachable — fall back to the offline Vosk model.
    logger.warning("[WARN] Backend STT unavailable — trying offline Vosk")
    fallback_text = _recognize_with_vosk(audio)
    if fallback_text:
        logger.info("[bridge] STT result (Vosk fallback): '%s'", fallback_text)
        return fallback_text
    logger.warning("[WARN] Offline fallback unavailable or produced no result")
    return None


async def listen_once(
    timeout: float = 8.0,
    phrase_time_limit: float = 15.0,
    pause_threshold: float = 0.8,
) -> Optional[str]:
    """Non-blocking async wrapper around _listen_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        lambda: _listen_sync(
            timeout=timeout,
            phrase_time_limit=phrase_time_limit,
            pause_threshold=pause_threshold,
        ),
    )


# ── Backend HTTP helper ────────────────────────────────────────────────────────

def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if VOICE_TOKEN:
        headers["Authorization"] = f"Bearer {VOICE_TOKEN}"
    return headers


# B4/R1: The backend only ever exposes ONE real chat endpoint —
# POST /api/v1/chat/send, with request body {"message": "...", "stream": false}
# and response body {"response": "...", "agent_id": "...", ...} — confirmed
# against backend/api/routes/chat.py. The previous implementation guessed at
# 4 candidate URLs (3 of which can never exist given how main.py registers
# routers) and re-probed all 4 on every single voice turn. This resolves the
# endpoint once per process and reuses it, with a small bounded retry for
# transient failures instead of silently giving up after one attempt.
_RESOLVED_CHAT_ENDPOINT = f"{BACKEND_URL}/api/v1/chat/send"


def _post_chat_message(text: str) -> Optional[str]:
    """
    Single POST attempt against the resolved chat endpoint.
    Returns the reply text on success, or None on any failure.
    """
    payload = json.dumps({"message": text, "stream": False}).encode()
    try:
        req = urllib.request.Request(
            _RESOLVED_CHAT_ENDPOINT, data=payload, headers=_auth_headers(), method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            reply = (
                body.get("response")
                or body.get("content")
                or body.get("message")
                or body.get("reply")
                or body.get("text")
                or ""
            )
            if reply:
                return reply
            logger.warning("[WARN] Backend returned empty reply: %s", body)
            return None
    except urllib.error.HTTPError as exc:
        logger.warning("[WARN] HTTP %s from %s: %s", exc.code, _RESOLVED_CHAT_ENDPOINT, exc.reason)
        return None
    except urllib.error.URLError as exc:
        logger.warning("[WARN] Cannot reach %s: %s", _RESOLVED_CHAT_ENDPOINT, exc.reason)
        return None
    except Exception as exc:
        logger.warning("[WARN] Unexpected error querying %s: %s", _RESOLVED_CHAT_ENDPOINT, exc)
        return None


def _query_backend_sync(text: str) -> Optional[str]:
    """
    Blocking HTTP POST to the resolved backend chat endpoint — runs in a
    thread executor. Retries up to BACKEND_QUERY_RETRIES times with a short
    fixed wait, since a transient failure (e.g. backend mid-restart) shouldn't
    silently fail an entire voice turn after a single attempt.
    """
    logger.debug("[bridge] POST %s", _RESOLVED_CHAT_ENDPOINT)

    for attempt in range(1, BACKEND_QUERY_RETRIES + 1):
        reply = _post_chat_message(text)
        if reply:
            logger.info("[bridge] Backend reply (attempt %d): %s", attempt, reply[:120])
            return reply
        if attempt < BACKEND_QUERY_RETRIES:
            logger.debug("[bridge] Retrying backend query in %.1fs (attempt %d/%d)…",
                         BACKEND_QUERY_RETRY_WAIT, attempt + 1, BACKEND_QUERY_RETRIES)
            time.sleep(BACKEND_QUERY_RETRY_WAIT)

    logger.warning("[WARN] Backend query failed after %d attempt(s) for text: '%s'",
                    BACKEND_QUERY_RETRIES, text)
    return None


async def query_backend(text: str) -> Optional[str]:
    """Non-blocking async wrapper around _query_backend_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _query_backend_sync, text)


async def _stream_chat(text: str, persona: Optional[str] = None,
                       speaker_id: Optional[str] = None) -> "asyncio.AsyncIterator[str]":
    """POST to the chat endpoint with stream:true and parse SSE deltas.

    Reuses _RESOLVED_CHAT_ENDPOINT + _auth_headers. Yields text content as it
    arrives so TTS can start on the first sentence (Phase E). Accepts an
    optional persona (Phase F) and speaker_id (Phase G) threaded into the body.
    """
    payload = {"message": text, "stream": True}
    if persona:
        payload["voice_persona"] = persona
    if speaker_id:
        payload["speaker_id"] = speaker_id
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _RESOLVED_CHAT_ENDPOINT, data=data, headers=_auth_headers(), method="POST"
    )
    loop = asyncio.get_event_loop()
    raw = await loop.run_in_executor(_executor, lambda: urllib.request.urlopen(req, timeout=30))
    try:
        for line in raw:
            line = line.decode() if isinstance(line, (bytes, bytearray)) else line
            line = line.strip()
            if not line or not line.startswith("data:"):
                continue
            payload_str = line[len("data:"):].strip()
            if not payload_str:
                continue
            try:
                evt = json.loads(payload_str)
            except json.JSONDecodeError:
                continue
            if evt.get("type") == "content" and evt.get("content"):
                yield evt["content"]
            elif evt.get("type") in ("done", "complete"):
                break
    finally:
        try:
            raw.close()
        except Exception:
            pass


# ── WebSocket broadcast server ─────────────────────────────────────────────────

_connected_browsers: set = set()


async def _ws_handler(websocket) -> None:
    _connected_browsers.add(websocket)
    logger.info("[bridge][WS] Browser connected (%d total)", len(_connected_browsers))
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                logger.debug("[bridge][WS] Message from browser: %s", msg)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("[WARN][WS] Invalid JSON from browser: %s", exc)
    except Exception:
        pass
    finally:
        _connected_browsers.discard(websocket)
        logger.info("[bridge][WS] Browser disconnected (%d remaining)", len(_connected_browsers))


async def _broadcast(event: dict) -> None:
    if not _connected_browsers:
        logger.debug("[bridge] No browsers connected — broadcast skipped")
        return
    payload = json.dumps(event)
    dead = set()
    for ws in list(_connected_browsers):
        try:
            await ws.send(payload)
        except Exception:
            dead.add(ws)
    _connected_browsers.difference_update(dead)
    logger.debug("[bridge] Broadcast sent to %d browser(s)", len(_connected_browsers) - len(dead))


async def _run_ws_server_once() -> None:
    """
    Single attempt at starting the WS server and serving forever.
    Raises on failure (e.g. port already in use) — the supervisor wrapping
    this function decides whether/how to retry. Kept separate from the old
    _start_ws_server() name so the supervisor (B5) has a single-attempt unit
    to wrap with restart logic.
    """
    if not WS_LIB_AVAILABLE:
        logger.warning("[WARN] websockets not available — browser WS server skipped")
        # Block forever without raising — there's nothing to retry here, this
        # is a missing-dependency condition, not a transient failure.
        await asyncio.Future()
        return

    import websockets
    async with websockets.serve(_ws_handler, "127.0.0.1", WS_PORT):
        logger.info("[bridge] WS server listening on ws://127.0.0.1:%d", WS_PORT)
        await asyncio.Future()


# ── Session mode ───────────────────────────────────────────────────────────────

async def _run_session() -> None:
    """
    Run a single voice session after the wake word has been detected.

    The session stays alive as long as the user keeps speaking.  Each time
    a command is processed the no-speech timer resets, so the user can ask
    follow-up questions without saying the wake word again.  The session
    ends when:

      • No speech is heard for SESSION_NO_SPEECH_TIMEOUT seconds, OR
      • The total wall-clock time exceeds SESSION_MAX_DURATION seconds.

    On exit the caller (the main loop) returns to passive wake-word scanning.
    """
    session_start = time.monotonic()
    turn = 0

    logger.info(
        "[bridge] Session started (no_speech_timeout=%.1fs, max_duration=%.0fs)",
        SESSION_NO_SPEECH_TIMEOUT, SESSION_MAX_DURATION,
    )

    while True:
        elapsed = time.monotonic() - session_start

        # Hard cap: end the session if it has run too long
        if elapsed >= SESSION_MAX_DURATION:
            logger.info("[bridge] Session max duration reached (%.0fs) — ending session", elapsed)
            await speak("Session ended. Say 'agentium' to start a new one.")
            return

        remaining = SESSION_MAX_DURATION - elapsed

        # Listen for the next command.  Use the session pause_threshold (1.5s)
        # so mid-sentence pauses do not prematurely cut the user off.
        command = await listen_once(
            timeout=min(SESSION_NO_SPEECH_TIMEOUT, remaining),
            phrase_time_limit=15.0,
            pause_threshold=SESSION_PAUSE_THRESHOLD,
        )

        if not command:
            # No speech within the no-speech timeout — end the session.
            if turn == 0:
                # User said the wake word but never spoke a command.
                await speak("I didn't catch that. Say 'agentium' when you're ready.")
            else:
                logger.info("[bridge] No follow-up in %.1fs — session ended", SESSION_NO_SPEECH_TIMEOUT)
            return

        turn += 1
        logger.info("[bridge] Session turn %d: '%s'", turn, command)

        # Query the backend
        reply = await query_backend(command)
        if not reply:
            reply = "I'm having trouble reaching the backend right now."
            logger.warning("[WARN] Backend returned no reply for: '%s'", command)

        logger.info("[bridge] Reply: '%s'", reply[:120])

        # Speak the reply and broadcast to any connected browser tabs
        await speak(reply)

        await _broadcast({
            "type":  "voice_interaction",
            "user":  command,
            "reply": reply,
            "ts":    time.time(),
        })

        # Loop continues — the no-speech timer effectively resets because the
        # next listen_once() call starts fresh after the reply has been spoken.
        logger.info(
            "[bridge] Staying in session — %.1fs elapsed, %.1fs remaining",
            time.monotonic() - session_start,
            SESSION_MAX_DURATION - (time.monotonic() - session_start),
        )


# ── Main voice loop ────────────────────────────────────────────────────────────

async def _capture_utterance(
    mic: "MicrophoneSource", vad: "Optional[VAD]" = None, timeout: float = SESSION_NO_SPEECH_TIMEOUT
) -> Optional[str]:
    """Capture one VAD-bounded utterance and transcribe it.

    Until the VAD stage (Phase B) is live, falls back to the existing blocking
    energy-gated listener. Returns the transcript string or None on timeout.
    """
    loop = asyncio.get_event_loop()
    if vad is None or not vad.available:
        return await loop.run_in_executor(
            _executor, _listen_sync, timeout, 15.0, SESSION_PAUSE_THRESHOLD
        )
    chunks: list[bytes] = []
    silence_ms = 0.0
    frame_ms = 80.0
    elapsed = 0.0
    while elapsed < timeout * 1000:
        frame = await loop.run_in_executor(_executor, mic.read_frame)
        chunks.append(frame)
        score = await loop.run_in_executor(_executor, vad.push_frame, frame)
        if vad.is_speech(score):
            silence_ms = 0.0
        else:
            silence_ms += frame_ms
            if vad.should_endpoint("", silence_ms, vad.silence_base_ms):
                break
        elapsed += frame_ms
    if not chunks:
        return None
    wav = _frames_to_wav(b"".join(chunks))
    text = await loop.run_in_executor(_executor, _transcribe_via_backend, wav)
    if not text:
        # Vosk needs AudioData; reuse the blocking listener for the fallback.
        return await loop.run_in_executor(_executor, _listen_sync, 1.0, 15.0, SESSION_PAUSE_THRESHOLD)
    return text


def _frames_to_wav(pcm: bytes) -> bytes:
    import wave as _wave
    import io
    buf = io.BytesIO()
    with _wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return buf.getvalue()


async def _process_direct(text: str) -> None:
    """Handle a single utterance in direct (no wake word) mode."""
    reply = await query_backend(text)
    if not reply:
        reply = "I'm having trouble reaching the backend right now."
    tts = _get_tts_engine()
    if tts.available:
        audio = tts.synth(text)
        if audio:
            tts.play(audio)
    else:
        await _speak_fallback(reply)
    await _broadcast({"type": "voice_interaction", "user": text, "reply": reply, "ts": time.time()})


def _split_sentences(text: str):
    """Split a reply into sentence chunks for incremental TTS."""
    parts = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in ".?!" and buf.strip():
            parts.append(buf.strip())
            buf = ""
    if buf.strip():
        parts.append(buf.strip())
    return parts or [text]


class VoiceSession:
    """Asyncio state machine: LISTENING -> THINKING -> SPEAKING -> (INTERRUPTED) -> LISTENING.

    SPEAKING runs a continuous VAD (driven by the mic frames interleaved with
    playback) so the user can barge in: sustained speech (>=250 ms) flushes the
    TTS queue and returns to LISTENING. A false-barge-in guard ignores short
    backchannel noises.
    """

    BARGE_IN_SPEECH_MS = 250.0
    FRAME_MS = 80.0

    def __init__(self, mic, vad, tts, barge_in: bool = True, persona: Optional[str] = None,
                 speaker_id: Optional[str] = None):
        self.mic = mic
        self.vad = vad
        self.tts = tts
        self.barge_in = barge_in
        self.persona = persona
        self.speaker_id = speaker_id
        self.phase = "IDLE"
        self._speech_ms = 0.0
        self._abort = asyncio.Event()

    async def run(self):
        loop = asyncio.get_event_loop()
        while True:
            self.phase = "LISTENING"
            await self._broadcast_state("listening")
            text = await _capture_utterance(self.mic, self.vad)
            if not text:
                return  # no-speech timeout ends the session
            self.phase = "THINKING"
            await self._broadcast_state("thinking")
            self.phase = "SPEAKING"
            await self._broadcast_state("speaking")
            full_reply = await self._speak_reply_stream(text)
            if self._abort.is_set():
                self._abort.clear()
                self.phase = "INTERRUPTED"
                await self._broadcast_state("interrupted")
                continue  # loop back to LISTENING
            await _broadcast({
                "type": "voice_interaction", "user": text, "reply": full_reply,
                "ts": time.time(), "speaker_id": self.speaker_id,
            })

    async def _speak_reply_stream(self, text: str) -> str:
        """Consume the streaming chat response, flushing complete sentences to
        TTS as they form (Phase D). Falls back to the non-streaming call if the
        SSE stream errors. Returns the full assembled reply for broadcast."""
        loop = asyncio.get_event_loop()
        buffer = ""
        full: list[str] = []
        try:
            async for delta in _stream_chat(text, self.persona, self.speaker_id):
                buffer += delta
                full.append(delta)
                while "." in buffer or "?" in buffer or "!" in buffer:
                    idx = max(buffer.find("."), buffer.find("?"), buffer.find("!"))
                    if idx < 0:
                        break
                    sentence = buffer[:idx + 1].strip()
                    buffer = buffer[idx + 1:]
                    if not sentence:
                        continue
                    if self.barge_in and await self._check_barge_in(loop):
                        return "".join(full)
                    audio = self.tts.synth(sentence) if self.tts.available else b""
                    if audio:
                        self.mic.feed_playback(audio)
                        self.tts.play(audio)
                    else:
                        await _speak_fallback(sentence)
        except Exception as exc:
            logger.warning("[WARN] streamed chat failed: %s — using non-streaming", exc)
            fb = await query_backend(text)
            if fb:
                full.append(fb)
                for sentence in _split_sentences(fb):
                    audio = self.tts.synth(sentence) if self.tts.available else b""
                    if audio:
                        self.mic.feed_playback(audio)
                        self.tts.play(audio)
                    else:
                        await _speak_fallback(sentence)
        remainder = buffer.strip()
        if remainder:
            audio = self.tts.synth(remainder) if self.tts.available else b""
            if audio:
                self.mic.feed_playback(audio)
                self.tts.play(audio)
            else:
                await _speak_fallback(remainder)
            full.append(remainder)
        return "".join(full)

    async def _check_barge_in(self, loop) -> bool:
        """Return True if sustained user speech was detected (barge-in)."""
        frame_bytes = await loop.run_in_executor(_executor, self.mic.read_frame)
        if not frame_bytes:
            return False
        score = self.vad.push_frame(frame_bytes)
        if self.vad.is_speech(score):
            self._speech_ms += self.FRAME_MS
            if self._speech_ms >= self.BARGE_IN_SPEECH_MS:
                self._abort.set()
                self.tts.flush()
                return True
        else:
            self._speech_ms = 0.0
        return False

    async def _broadcast_state(self, state: str):
        await _broadcast({"type": "voice_state", "state": state, "ts": time.time()})


async def _run_voice_loop_once() -> None:
    """
    Single pass of the voice loop's outer try/except wrapper. Rewritten for the
    Jarvis upgrade: streams 80 ms mic frames through a continuous wake-word
    detector (instead of recording a full utterance and substring-matching the
    transcript), plays an instant local chime on trigger, then enters the
    session state machine. Direct mode (REQUIRE_WAKE_WORD=false) is preserved.

    An unhandled exception propagates to the supervisor (_supervise) instead of
    being swallowed, so recurring failures stay visible.
    """
    logger.info("[bridge] Voice loop started")

    if not SR_AVAILABLE:
        logger.warning("[WARN] STT unavailable — voice loop idle (WS server still running)")
        await asyncio.Future()
        return

    mic = MicrophoneSource()
    if not mic.available:
        logger.warning("[WARN] Microphone unavailable — voice loop idle")
        await asyncio.Future()
        return
    mic.open()

    from vad import VAD
    from tts_engine import TTSEngine
    detector = WakeWordDetector(WAKE_WORD_MODEL) if REQUIRE_WAKE_WORD else None
    vad = VAD()
    tts = _get_tts_engine()
    loop = asyncio.get_event_loop()

    if REQUIRE_WAKE_WORD:
        logger.info("[bridge] Wake word mode ON — say '%s' to start a session", WAKE_WORD)
    else:
        logger.info("[bridge] Wake word mode OFF — speaking directly starts a session")

    try:
        while True:
            frame = await loop.run_in_executor(_executor, mic.read_frame)
            if REQUIRE_WAKE_WORD and detector is not None:
                if detector.available:
                    score = await loop.run_in_executor(_executor, detector.push_frame, frame)
                    if detector.is_triggered(score):
                        logger.info("[bridge] Wake word detected — starting session")
                        _play_wake_chime()
                        session = VoiceSession(mic, vad, tts, persona=_load_persona())
                        await session.run()
                        continue
                else:
                    # Model missing -> graceful fallback: behave as direct mode.
                    logger.warning("[WARN] Wake-word model unavailable — direct mode")
                    cmd = await _capture_utterance(mic, vad)
                    if cmd:
                        await _process_direct(cmd)
                    continue
            else:
                cmd = await _capture_utterance(mic, vad)
                if cmd:
                    await _process_direct(cmd)
    finally:
        mic.close()


# ── Subsystem supervisor (B5) ───────────────────────────────────────────────────
#
# Previously both the WS server and the voice loop ran under a single
# asyncio.gather(), so an unexpected failure in either one tore down the
# entire process — including the subsystem that was working fine. Each
# subsystem is now supervised independently: on an unhandled exception it
# logs, waits SUPERVISOR_RESTART_DELAY, and restarts itself. A clean
# CancelledError (from process shutdown) still propagates immediately so
# Ctrl+C / SIGTERM continue to work exactly as before.

async def _supervise(name: str, coro_factory) -> None:
    """Run coro_factory() forever, restarting it with a delay on failure."""
    while True:
        try:
            await coro_factory()
            # A subsystem returning normally (rather than running forever)
            # is unexpected for these two coroutines — treat it the same as
            # a failure so we don't silently stop supervising.
            logger.warning("[bridge][supervisor:%s] Subsystem exited unexpectedly — restarting", name)
        except asyncio.CancelledError:
            logger.info("[bridge][supervisor:%s] Cancelled — shutting down", name)
            raise
        except Exception as exc:
            logger.error(
                "[ERROR][supervisor:%s] Subsystem crashed: %s — restarting in %.1fs",
                name, exc, SUPERVISOR_RESTART_DELAY, exc_info=True,
            )
        await asyncio.sleep(SUPERVISOR_RESTART_DELAY)


# ── Entry point ────────────────────────────────────────────────────────────────

async def _main() -> None:
    logger.info("=" * 60)
    logger.info("  Agentium SecureVoiceBridge starting")
    logger.info("  Backend   : %s", BACKEND_URL)
    logger.info("  Chat API  : %s", _RESOLVED_CHAT_ENDPOINT)
    logger.info("  WS port   : %d", WS_PORT)
    logger.info("  Wake word : '%s' (required=%s)", WAKE_WORD, REQUIRE_WAKE_WORD)
    logger.info("  STT       : whisper.cpp (backend relay) + Vosk fallback" if SR_AVAILABLE else "DISABLED")
    logger.info("  STT backend: %s", STT_BACKEND_URL)
    logger.info("  TTS       : %s", "pyttsx3" if TTS_AVAILABLE else "DISABLED")
    logger.info("  Platform  : %s", platform.system())
    logger.info("  Session   : no_speech=%.1fs  max=%.0fs  pause=%.1fs",
                SESSION_NO_SPEECH_TIMEOUT, SESSION_MAX_DURATION, SESSION_PAUSE_THRESHOLD)
    logger.info("  Persona   : %s", "default" if _load_persona() else "none")
    logger.info("  Proactive : %s", "enabled" if VOICE_PROACTIVE_ENABLED else "disabled")
    logger.info("=" * 60)

    # B5: each subsystem is supervised independently now instead of sharing
    # a single asyncio.gather() that dies as one unit. The proactive WS client
    # is supervised too (no-op unless VOICE_PROACTIVE_ENABLED).
    await asyncio.gather(
        _supervise("ws-server", _run_ws_server_once),
        _supervise("voice-loop", _run_voice_loop_once),
        _supervise("backend-ws", lambda: _run_backend_ws(ProactiveAnnouncer())),
    )


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("[bridge] Stopped by user")
    except Exception as exc:
        logger.error("[ERROR] Fatal: %s", exc, exc_info=True)
        sys.exit(1)