"""
Security utilities for Agentium.
Handles API key encryption/decryption and authentication.
"""
from cryptography.fernet import Fernet
from backend.core.config import settings


def get_fernet():
    """Get Fernet instance for encryption."""
    key = settings.ENCRYPTION_KEY

    if key:
        if isinstance(key, str):
            key = key.encode()
    else:
        key = Fernet.generate_key()  # Returns bytes

    return Fernet(key)


def encrypt_api_key(plain_key: str) -> str:
    """Encrypt an API key for storage."""
    if not plain_key:
        return None
    f = get_fernet()
    return f.encrypt(plain_key.encode()).decode()


def decrypt_api_key(encrypted_key: str) -> str:
    """Decrypt an API key for use."""
    if not encrypted_key:
        return None
    f = get_fernet()
    return f.decrypt(encrypted_key.encode()).decode()
