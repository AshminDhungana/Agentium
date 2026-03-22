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
from typing import Optional

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

import urllib.request
import urllib.error

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


# ── STT ────────────────────────────────────────────────────────────────────────

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
    if not SR_AVAILABLE:
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
        logger.warning("[WARN] Microphone error: %s", exc)
        return None
    except sr.WaitTimeoutError:
        logger.debug("[bridge] Listen timeout — no speech detected")
        return None
    except Exception as exc:
        logger.warning("[WARN] Unexpected mic error: %s", exc)
        return None

    logger.debug("[bridge] Audio captured, sending to STT…")

    try:
        text = recognizer.recognize_google(audio)
        logger.info("[bridge] STT result: '%s'", text)
        return text
    except sr.UnknownValueError:
        logger.debug("[bridge] STT: could not understand audio")
        return None
    except sr.RequestError as exc:
        logger.warning("[WARN] Google STT request failed: %s", exc)
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


def _query_backend_sync(text: str) -> Optional[str]:
    """
    Blocking HTTP POST to backend — runs in thread executor.
    Tries multiple endpoint paths to find whichever the backend exposes.
    """
    endpoints = [
        f"{BACKEND_URL}/api/v1/chat/message",
        f"{BACKEND_URL}/api/v1/chat",
        f"{BACKEND_URL}/api/chat/message",
        f"{BACKEND_URL}/api/chat",
    ]

    payload = json.dumps({"content": text, "source": "voice"}).encode()

    for url in endpoints:
        try:
            logger.debug("[bridge] POST %s", url)
            req = urllib.request.Request(url, data=payload, headers=_auth_headers(), method="POST")
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
                    logger.info("[bridge] Backend reply (%s): %s", url, reply[:120])
                    return reply
                else:
                    logger.warning("[WARN] Backend returned empty reply from %s: %s", url, body)
        except urllib.error.HTTPError as exc:
            logger.warning("[WARN] HTTP %s from %s: %s", exc.code, url, exc.reason)
            continue
        except urllib.error.URLError as exc:
            logger.warning("[WARN] Cannot reach %s: %s", url, exc.reason)
            break
        except Exception as exc:
            logger.warning("[WARN] Unexpected error querying %s: %s", url, exc)
            continue

    logger.warning("[WARN] All backend endpoints failed for text: '%s'", text)
    return None


async def query_backend(text: str) -> Optional[str]:
    """Non-blocking async wrapper around _query_backend_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _query_backend_sync, text)


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


async def _start_ws_server() -> None:
    if not WS_LIB_AVAILABLE:
        logger.warning("[WARN] websockets not available — browser WS server skipped")
        return
    try:
        import websockets
        async with websockets.serve(_ws_handler, "127.0.0.1", WS_PORT):
            logger.info("[bridge] WS server listening on ws://127.0.0.1:%d", WS_PORT)
            await asyncio.Future()
    except OSError as exc:
        if "address already in use" in str(exc).lower():
            logger.error(
                "[ERROR] Port %d already in use — kill the other process or change WS_PORT in env.conf",
                WS_PORT,
            )
        raise


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

async def _voice_loop() -> None:
    logger.info("[bridge] Voice loop started")

    if not SR_AVAILABLE:
        logger.warning("[WARN] STT unavailable — voice loop idle (WS server still running)")
        await asyncio.Future()
        return

    if REQUIRE_WAKE_WORD:
        logger.info("[bridge] Wake word mode ON — say '%s' to start a session", WAKE_WORD)
    else:
        logger.info("[bridge] Wake word mode OFF — speaking directly starts a session")

    while True:
        try:
            # ── Passive scan: listen for the wake word ─────────────────────────
            # Use a tighter pause_threshold (0.8s) here — we only need to catch
            # the two-word trigger, not a full sentence.
            raw = await listen_once(
                timeout=WAKE_WORD_LISTEN_TIMEOUT,
                phrase_time_limit=5.0,
                pause_threshold=0.8,
            )

            if not raw:
                continue

            logger.info("[bridge] Heard: '%s'", raw)

            if REQUIRE_WAKE_WORD:
                if WAKE_WORD not in raw.lower():
                    logger.debug("[bridge] No wake word in '%s' — ignoring", raw)
                    continue

                logger.info("[bridge] Wake word detected — starting session")
                await speak("Yes, how can I help?")
            else:
                # No wake word required — anything heard kicks off a session
                # with the first utterance already captured.
                logger.info("[bridge] Direct mode — processing immediately")
                reply = await query_backend(raw)
                if not reply:
                    reply = "I'm having trouble reaching the backend right now."
                await speak(reply)
                await _broadcast({
                    "type":  "voice_interaction",
                    "user":  raw,
                    "reply": reply,
                    "ts":    time.time(),
                })

            # ── Enter session mode ─────────────────────────────────────────────
            if REQUIRE_WAKE_WORD:
                await _run_session()

        except asyncio.CancelledError:
            logger.info("[bridge] Voice loop cancelled")
            break
        except Exception as exc:
            logger.warning("[WARN] Unhandled error in voice loop: %s", exc, exc_info=True)
            await asyncio.sleep(1)


# ── Entry point ────────────────────────────────────────────────────────────────

async def _main() -> None:
    logger.info("=" * 60)
    logger.info("  Agentium SecureVoiceBridge starting")
    logger.info("  Backend   : %s", BACKEND_URL)
    logger.info("  WS port   : %d", WS_PORT)
    logger.info("  Wake word : '%s' (required=%s)", WAKE_WORD, REQUIRE_WAKE_WORD)
    logger.info("  STT       : %s", "SpeechRecognition+Google" if SR_AVAILABLE else "DISABLED")
    logger.info("  TTS       : %s", "pyttsx3" if TTS_AVAILABLE else "DISABLED")
    logger.info("  Platform  : %s", platform.system())
    logger.info("  Session   : no_speech=%.1fs  max=%.0fs  pause=%.1fs",
                SESSION_NO_SPEECH_TIMEOUT, SESSION_MAX_DURATION, SESSION_PAUSE_THRESHOLD)
    logger.info("=" * 60)

    await asyncio.gather(
        _start_ws_server(),
        _voice_loop(),
    )


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        logger.info("[bridge] Stopped by user")
    except Exception as exc:
        logger.error("[ERROR] Fatal: %s", exc, exc_info=True)
        sys.exit(1)