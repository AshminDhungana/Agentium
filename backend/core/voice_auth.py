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

_VOICE_SECRET: Optional[str] = os.getenv("VOICE_JWT_SECRET")
_DURATION_MINUTES: int = int(os.getenv("VOICE_TOKEN_DURATION_MINUTES", "30"))
_ALGORITHM = "HS256"
_TOKEN_TYPE = "voice"


# ── Public helpers ──────────────────────────────────────────────────────────────

def create_voice_token(username: str, user_id: Optional[str] = None) -> str:
    """
    Create a short-lived voice-scoped JWT.

    Raises:
        RuntimeError: if VOICE_JWT_SECRET is not configured.
    """
    if not _VOICE_SECRET:
        raise RuntimeError(
            "VOICE_JWT_SECRET is not set. "
            "Add it to backend/.env before using the voice bridge."
        )

    now = datetime.utcnow()
    payload = {
        "sub": username,
        "user_id": user_id,
        "type": _TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=_DURATION_MINUTES),
    }

    token = jwt.encode(payload, _VOICE_SECRET, algorithm=_ALGORITHM)
    logger.info("[voice_auth] Issued voice token for user '%s' (expires in %dm)", username, _DURATION_MINUTES)
    return token


def verify_voice_token(token: str) -> Optional[dict]:
    """
    Decode and validate a voice-scoped JWT.

    Returns the payload dict on success, or None on any failure (expired,
    wrong secret, wrong type, etc.).  Never raises — the caller decides
    what to do with a None result.
    """
    if not _VOICE_SECRET:
        logger.warning("[voice_auth] VOICE_JWT_SECRET not set — token verification skipped")
        return None

    try:
        payload = jwt.decode(token, _VOICE_SECRET, algorithms=[_ALGORITHM])
        if payload.get("type") != _TOKEN_TYPE:
            logger.warning("[voice_auth] Token type mismatch: expected '%s', got '%s'", _TOKEN_TYPE, payload.get("type"))
            return None
        return payload
    except JWTError as exc:
        logger.warning("[voice_auth] Token validation failed: %s", exc)
        return None