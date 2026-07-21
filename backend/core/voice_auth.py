"""
voice_auth.py — Voice-scoped JWT helper for Agentium.

Issues short-lived tokens that the voice bridge uses to authenticate
against the main backend.  Uses its own secret (VOICE_JWT_SECRET) so a
leaked voice token can never be used to impersonate a full session.
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Optional

from jose import JWTError, jwt

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

_DURATION_MINUTES: int = int(os.getenv("VOICE_TOKEN_DURATION_MINUTES", "30"))
_ALGORITHM = "HS256"
_TOKEN_TYPE = "voice"


def _get_voice_secret() -> Optional[str]:
    """Re-read VOICE_JWT_SECRET from env so startup auto-generation is visible."""
    return os.getenv("VOICE_JWT_SECRET")


# ── Public helpers ──────────────────────────────────────────────────────────────

def create_voice_token(username: str, user_id: Optional[str] = None) -> str:
    """
    Create a short-lived voice-scoped JWT.

    Raises:
        RuntimeError: if VOICE_JWT_SECRET is not configured.
    """
    return _encode_voice_token(username, user_id, _DURATION_MINUTES)


def create_host_voice_token(username: str, user_id: Optional[str] = None,
                            days: Optional[int] = None) -> str:
    """
    Create a LONG-lived voice-scoped JWT for the host-native voice bridge.

    Unlike the short session-bound voice token (issued to the browser client),
    the host bridge runs independently of any browser session and must keep
    authenticating to the backend after the browser is closed.  This token is
    delivered to the bridge locally over its trusted 127.0.0.1 WS by an
    authenticated admin, never over the network, so a long lifetime is safe.

    Raises:
        RuntimeError: if VOICE_JWT_SECRET is not configured.
    """
    if days is None:
        days = int(os.getenv("VOICE_HOST_TOKEN_DURATION_DAYS", "30"))
    return _encode_voice_token(username, user_id, days * 24 * 60)


def _encode_voice_token(username: str, user_id: Optional[str], minutes: int) -> str:
    secret = _get_voice_secret()
    if not secret:
        raise RuntimeError(
            "VOICE_JWT_SECRET is not set. "
            "Set the VOICE_JWT_SECRET environment variable before using the voice bridge."
        )

    now = datetime.utcnow()
    payload = {
        "sub": username,
        "user_id": user_id,
        "type": _TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=minutes),
    }

    token = jwt.encode(payload, secret, algorithm=_ALGORITHM)
    logger.info("[voice_auth] Issued voice token for user '%s' (expires in %dm)", username, minutes)
    return token


def verify_voice_token(token: str) -> Optional[dict]:
    """
    Decode and validate a voice-scoped JWT.

    Returns the payload dict on success, or None on any failure (expired,
    wrong secret, wrong type, etc.).  Never raises — the caller decides
    what to do with a None result.
    """
    secret = _get_voice_secret()
    if not secret:
        logger.warning("[voice_auth] VOICE_JWT_SECRET not set — token verification skipped")
        return None

    try:
        payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
        if payload.get("type") != _TOKEN_TYPE:
            logger.warning("[voice_auth] Token type mismatch: expected '%s', got '%s'", _TOKEN_TYPE, payload.get("type"))
            return None
        return payload
    except JWTError as exc:
        logger.warning("[voice_auth] Token validation failed: %s", exc)
        return None