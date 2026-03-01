"""
voice-bridge/main.py — Agentium SecureVoiceBridge
==================================================
Runs on the HOST (outside Docker).  Connects to the backend inside Docker
via HTTP, streams microphone input through STT, sends text to the Head of
Council, speaks the reply with TTS, and pushes the exchange to the browser
via a local WebSocket server on 127.0.0.1:9999.

Every import that can fail is guarded individually so the bridge keeps
running in a degraded state rather than crashing.

Start:  python voice-bridge/main.py
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

# ── Logging ────────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("voice-bridge")

# ── Read env.conf written by detect-host.sh ───────────────────────────────────

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

BACKEND_URL: str  = _conf.get("BACKEND_URL",  os.getenv("BACKEND_URL",  "http://127.0.0.1:8000"))
WS_PORT:     int  = int(_conf.get("WS_PORT",  os.getenv("WS_PORT",  "9999")))
WAKE_WORD:   str  = _conf.get("WAKE_WORD",   os.getenv("WAKE_WORD",   "agentium")).lower()
VOICE_TOKEN: str  = _conf.get("VOICE_TOKEN", os.getenv("VOICE_TOKEN", ""))

# ── Optional dependency guards ─────────────────────────────────────────────────

SR_AVAILABLE    = False
TTS_AVAILABLE   = False
VOSK_AVAILABLE  = False
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
    logger.warning("[WARN] pyttsx3 not installed — TTS disabled (replies will be text-only)")

try:
    import vosk  # noqa: F401
    VOSK_AVAILABLE = True
    logger.info("[bridge] Vosk offline STT available")
except ImportError:
    logger.warning("[WARN] Vosk not installed — will rely on Google STT only")

try:
    import websockets
    WS_LIB_AVAILABLE = True
    logger.info("[bridge] websockets library available")
except ImportError:
    logger.warning("[WARN] websockets not installed — browser sync disabled")

import urllib.request
import urllib.error


# ── TTS engine (lazy init so errors surface cleanly) ──────────────────────────

_tts_engine = None

def _get_tts() -> Optional[object]:
    global _tts_engine
    if not TTS_AVAILABLE:
        return None
    if _tts_engine is None:
        try:
            _tts_engine = pyttsx3.init()
            logger.info("[bridge] TTS engine initialised")
        except Exception as exc:
            logger.warning("[WARN] TTS engine init failed: %s", exc)
            return None
    return _tts_engine


def speak(text: str) -> None:
    """Speak text aloud. Silently skips if TTS is unavailable or crashes."""
    engine = _get_tts()
    if not engine:
        logger.info("[bridge][TTS-FALLBACK] %s", text)
        return
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as exc:
        logger.warning("[WARN] TTS speak failed: %s", exc)


# ── STT ────────────────────────────────────────────────────────────────────────

def listen_once() -> Optional[str]:
    """
    Capture one utterance from the microphone and return the transcript.
    Returns None on any error so the main loop can continue.
    """
    if not SR_AVAILABLE:
        return None

    recognizer = sr.Recognizer()
    try:
        with sr.Microphone() as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            logger.info("[bridge] Listening…")
            audio = recognizer.listen(source, timeout=5, phrase_time_limit=15)
    except OSError as exc:
        logger.warning("[WARN] Microphone error: %s", exc)
        return None
    except sr.WaitTimeoutError:
        return None

    # Try Google first, fall back to Vosk
    try:
        text = recognizer.recognize_google(audio)
        logger.info("[bridge] STT (Google): %s", text)
        return text
    except sr.UnknownValueError:
        return None
    except sr.RequestError as exc:
        logger.warning("[WARN] Google STT failed: %s — trying Vosk fallback", exc)

    if VOSK_AVAILABLE:
        try:
            import vosk
            import json as _json
            model_path = Path.home() / ".agentium" / "vosk-model"
            if model_path.exists():
                model = vosk.Model(str(model_path))
                rec = vosk.KaldiRecognizer(model, 16000)
                raw_data = audio.get_raw_data(convert_rate=16000, convert_width=2)
                rec.AcceptWaveform(raw_data)
                result = _json.loads(rec.Result())
                return result.get("text") or None
            else:
                logger.warning("[WARN] Vosk model not found at %s", model_path)
        except Exception as exc:
            logger.warning("[WARN] Vosk fallback failed: %s", exc)

    return None


# ── Backend HTTP helper ────────────────────────────────────────────────────────

def _auth_headers() -> dict:
    headers = {"Content-Type": "application/json"}
    if VOICE_TOKEN:
        headers["Authorization"] = f"Bearer {VOICE_TOKEN}"
    return headers


def query_backend(text: str) -> Optional[str]:
    """
    Send user text to the Head of Council and return the reply string.
    Returns None on any network / HTTP error so the loop can continue.
    """
    url = f"{BACKEND_URL}/api/v1/chat/message"
    payload = json.dumps({"content": text, "source": "voice"}).encode()

    try:
        req = urllib.request.Request(url, data=payload, headers=_auth_headers(), method="POST")
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode())
            reply = body.get("response") or body.get("content") or body.get("message", "")
            logger.info("[bridge] Backend reply: %s", reply[:120])
            return reply
    except urllib.error.HTTPError as exc:
        logger.warning("[WARN] Backend HTTP %s: %s", exc.code, exc.reason)
    except urllib.error.URLError as exc:
        logger.warning("[WARN] Backend connection error: %s — is Docker running?", exc.reason)
    except Exception as exc:
        logger.warning("[WARN] Unexpected error querying backend: %s", exc)
    return None


# ── WebSocket broadcast server ─────────────────────────────────────────────────
# Pushes voice interaction events to the browser so ChatPage can show them.

_connected_browsers: set = set()


async def _ws_handler(websocket) -> None:
    _connected_browsers.add(websocket)
    logger.info("[bridge][WS] Browser connected (%d total)", len(_connected_browsers))
    try:
        async for raw in websocket:
            try:
                msg = json.loads(raw)
                logger.info("[bridge][WS] Message from browser: %s", msg)
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("[WARN][WS] Invalid JSON from browser: %s", exc)
    except Exception:
        pass
    finally:
        _connected_browsers.discard(websocket)
        logger.info("[bridge][WS] Browser disconnected (%d remaining)", len(_connected_browsers))


async def _broadcast(event: dict) -> None:
    if not _connected_browsers:
        return
    payload = json.dumps(event)
    dead = set()
    for ws in list(_connected_browsers):
        try:
            await ws.send(payload)
        except Exception:
            dead.add(ws)
    _connected_browsers.difference_update(dead)


async def _start_ws_server() -> None:
    if not WS_LIB_AVAILABLE:
        logger.warning("[WARN] websockets not available — browser WS server skipped")
        return
    try:
        import websockets
        async with websockets.serve(_ws_handler, "127.0.0.1", WS_PORT):
            logger.info("[bridge] WS server listening on ws://127.0.0.1:%d", WS_PORT)
            await asyncio.Future()   # run until cancelled
    except OSError as exc:
        if "address already in use" in str(exc).lower():
            logger.error(
                "[ERROR] Port %d already in use — "
                "kill the other process or change WS_PORT in env.conf", WS_PORT
            )
        raise


# ── Main voice loop ────────────────────────────────────────────────────────────

async def _voice_loop() -> None:
    """
    Continuously:
      1. Listen for the wake word
      2. Capture the full utterance
      3. Query the backend
      4. Speak the reply
      5. Broadcast the exchange to connected browsers
    """
    logger.info("[bridge] Voice loop started — say '%s' to activate", WAKE_WORD)

    if not SR_AVAILABLE:
        logger.warning("[WARN] STT unavailable — voice loop running in idle/text-only mode")
        await asyncio.Future()   # keep alive so WS server stays up
        return

    while True:
        try:
            raw = listen_once()
            if not raw:
                await asyncio.sleep(0.1)
                continue

            # Wake-word check
            if WAKE_WORD not in raw.lower():
                await asyncio.sleep(0.05)
                continue

            logger.info("[bridge] Wake word detected")
            speak("Yes, how can I help?")

            # Second capture — the actual command
            command = listen_once()
            if not command:
                speak("I didn't catch that. Please try again.")
                continue

            logger.info("[bridge] Command: %s", command)

            reply = query_backend(command)
            if not reply:
                reply = "I'm having trouble reaching the backend right now."

            speak(reply)

            event = {"type": "voice_interaction", "user": command, "reply": reply, "ts": time.time()}
            await _broadcast(event)

        except asyncio.CancelledError:
            logger.info("[bridge] Voice loop cancelled")
            break
        except Exception as exc:
            logger.warning("[WARN] Unhandled error in voice loop: %s", exc)
            await asyncio.sleep(1)


# ── Entry point ────────────────────────────────────────────────────────────────

async def _main() -> None:
    logger.info("=" * 60)
    logger.info("  Agentium SecureVoiceBridge starting")
    logger.info("  Backend  : %s", BACKEND_URL)
    logger.info("  WS port  : %d", WS_PORT)
    logger.info("  Wake word: '%s'", WAKE_WORD)
    logger.info("  STT      : %s", "SpeechRecognition" if SR_AVAILABLE else "DISABLED")
    logger.info("  TTS      : %s", "pyttsx3" if TTS_AVAILABLE else "DISABLED")
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
        logger.error("[ERROR] Fatal: %s", exc)
        sys.exit(1)