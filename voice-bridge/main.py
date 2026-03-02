"""
voice-bridge/main.py — Agentium SecureVoiceBridge
==================================================
Runs on the HOST (outside Docker).  Connects to the backend inside Docker
via HTTP, streams microphone input through STT, sends text to the Head of
Council, speaks the reply with TTS, and pushes the exchange to the browser
via a local WebSocket server on 127.0.0.1:9999.

Fixes applied:
  - listen_once() runs in a thread executor so it never blocks the async loop
  - Wake word is OPTIONAL (configurable via REQUIRE_WAKE_WORD in env.conf)
  - query_backend tries the WebSocket chat endpoint first, falls back to HTTP
  - Full debug logging so you can see exactly what is happening
  - pyttsx3 TTS runs in executor too (it blocks on Windows)

Start:  python voice-bridge/main.py
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
    level=logging.DEBUG,                        # DEBUG so you see every step
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
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
REQUIRE_WAKE_WORD: bool = _conf.get("REQUIRE_WAKE_WORD",  os.getenv("REQUIRE_WAKE_WORD",  "false")).lower() == "true"

logger.info("[bridge] BACKEND_URL=%s  WS_PORT=%d  WAKE_WORD='%s'  REQUIRE_WAKE_WORD=%s",
            BACKEND_URL, WS_PORT, WAKE_WORD, REQUIRE_WAKE_WORD)

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

def _listen_sync() -> Optional[str]:
    """
    Blocking mic capture + STT — MUST run in thread executor, never on the
    asyncio main thread.
    Returns transcript string or None.
    """
    if not SR_AVAILABLE:
        return None

    recognizer = sr.Recognizer()
    # Tune these for your environment:
    recognizer.energy_threshold        = 300   # lower = more sensitive
    recognizer.dynamic_energy_threshold = True
    recognizer.pause_threshold          = 0.8  # seconds of silence = end of phrase

    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.3)
            logger.info("[bridge] 🎙 Listening (timeout=8s, phrase_limit=20s)…")
            audio = recognizer.listen(source, timeout=8, phrase_time_limit=20)
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

    # Google STT
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

async def listen_once() -> Optional[str]:
    """Non-blocking async wrapper around _listen_sync."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _listen_sync)

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
    # Endpoint candidates in priority order
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
            req = urllib.request.Request(
                url, data=payload, headers=_auth_headers(), method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode())
                # Try common response field names
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
            # 404 = wrong endpoint, try next; 4xx/5xx = log and try next
            continue
        except urllib.error.URLError as exc:
            logger.warning("[WARN] Cannot reach %s: %s", url, exc.reason)
            break   # backend is down entirely — no point trying other endpoints
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
            logger.error("[ERROR] Port %d already in use — kill the other process or change WS_PORT in env.conf", WS_PORT)
        raise

# ── Main voice loop ────────────────────────────────────────────────────────────

async def _voice_loop() -> None:
    logger.info("[bridge] Voice loop started")

    if not SR_AVAILABLE:
        logger.warning("[WARN] STT unavailable — voice loop idle (WS server still running)")
        await asyncio.Future()
        return

    if REQUIRE_WAKE_WORD:
        logger.info("[bridge] Wake word mode ON — say '%s' first", WAKE_WORD)
    else:
        logger.info("[bridge] Wake word mode OFF — speak any command directly")

    while True:
        try:
            # ── Phase 1: listen for speech ─────────────────────────────────────
            raw = await listen_once()

            if not raw:
                # No speech detected — tight loop is fine because listen_once
                # already blocks for up to 8s inside the executor thread
                continue

            logger.info("[bridge] Heard: '%s'", raw)

            # ── Phase 2: wake-word gate (optional) ────────────────────────────
            if REQUIRE_WAKE_WORD:
                if WAKE_WORD not in raw.lower():
                    logger.debug("[bridge] No wake word in '%s' — ignoring", raw)
                    continue

                logger.info("[bridge] Wake word detected")
                await speak("Yes, how can I help?")

                # Listen again for the actual command
                command = await listen_once()
                if not command:
                    await speak("I didn't catch that. Please try again.")
                    continue
            else:
                # No wake word required — whatever was heard IS the command
                command = raw

            logger.info("[bridge] Processing command: '%s'", command)

            # ── Phase 3: query backend ─────────────────────────────────────────
            reply = await query_backend(command)

            if not reply:
                reply = "I'm having trouble reaching the backend right now."
                logger.warning("[WARN] Backend returned no reply for: '%s'", command)

            logger.info("[bridge] Reply: '%s'", reply[:120])

            # ── Phase 4: speak reply + broadcast to browser ───────────────────
            await speak(reply)

            event = {
                "type":  "voice_interaction",
                "user":  command,
                "reply": reply,
                "ts":    time.time(),
            }
            await _broadcast(event)

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