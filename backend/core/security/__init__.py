"""Security modules for Agentium."""

import logging
from typing import Optional

from backend.core.security.execution_guard import ExecutionGuard, execution_guard, SecurityCheckResult
from cryptography.fernet import Fernet, InvalidToken
from backend.core.config import settings

logger = logging.getLogger(__name__)


# Cache a single Fernet instance per process so encrypt/decrypt are always
# consistent within a running service (the key is read from settings once).
_fernet_instance: Optional[Fernet] = None


def get_fernet():
    """Get (and cache) the Fernet instance for encryption.

    A missing ``ENCRYPTION_KEY`` generates a process-local random key. This is
    only safe within a single process; across restarts or between services a
    stable ``ENCRYPTION_KEY`` must be shared, otherwise previously encrypted
    keys raise ``InvalidToken`` and decrypt to ``None``.
    """
    global _fernet_instance
    if _fernet_instance is not None:
        return _fernet_instance
    key = settings.ENCRYPTION_KEY
    if not key:
        logger.warning(
            "[security] ENCRYPTION_KEY is not set — generating an ephemeral key. "
            "API keys encrypted now will NOT be decryptable after a restart or in "
            "other services. Set ENCRYPTION_KEY (e.g. via `python scripts/gen_secrets.py`)."
        )
        key = Fernet.generate_key()
    elif isinstance(key, str):
        key = key.encode()
    _fernet_instance = Fernet(key)
    return _fernet_instance


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt an API key for storage."""
    if not plain_key:
        return None
    f = get_fernet()
    return f.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> Optional[str]:
    """Decrypt an API key for use.

    Returns ``None`` when the value is empty or cannot be decrypted (e.g. it
    was encrypted with a different/unavailable ``ENCRYPTION_KEY``, or the blob
    is corrupt). Call sites that rely on the key (model calls, voice, fetch
    models) then fail with a clear auth error instead of a 500.
    """
    if not encrypted_key:
        return None
    try:
        f = get_fernet()
        return f.decrypt(encrypted_key.encode()).decode()
    except Exception as exc:
        logger.warning("[security] Failed to decrypt API key: %s", exc)
        return None


__all__ = [
    "ExecutionGuard", "execution_guard", "SecurityCheckResult",
    "get_fernet", "encrypt_api_key", "decrypt_api_key",
]