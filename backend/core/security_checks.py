"""
Security startup checks.

These run once at application boot (see backend/main.py) and flag insecure
configuration before the system goes live. They are intentionally lightweight
and read-only — they never mutate configuration, only observe it.

Currently guards:
  - MinIO / S3 object storage using the well-known default credentials
    (`minioadmin` / `minioadmin`). Shipping with default credentials in any
    non-trivial deployment is a critical security risk: anyone who can reach
    the MinIO console or S3 API owns your file store.
"""

import os
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# Well-known insecure MinIO default shipped by the project's old Compose config.
DEFAULT_MINIO_USER = "minioadmin"
DEFAULT_MINIO_PASSWORD = "minioadmin"


def _resolved_minio_credentials() -> Tuple[str, str]:
    """
    Resolve the MinIO/S3 credentials the backend will actually use.

    The backend's S3 client reads AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY,
    which docker-compose wires to MINIO_ROOT_USER / MINIO_ROOT_PASSWORD. We
    check both so the guard works whether callers set the MinIO-named vars or
    the AWS-named vars.
    """
    user = (
        os.getenv("MINIO_ROOT_USER")
        or os.getenv("AWS_ACCESS_KEY_ID")
        or ""
    ).strip()
    password = (
        os.getenv("MINIO_ROOT_PASSWORD")
        or os.getenv("AWS_SECRET_ACCESS_KEY")
        or ""
    ).strip()
    return user, password


def minio_uses_default_credentials() -> bool:
    """Return True if the configured MinIO/S3 creds are the insecure default."""
    user, password = _resolved_minio_credentials()
    return user == DEFAULT_MINIO_USER and password == DEFAULT_MINIO_PASSWORD


def check_minio_credentials(strict: bool = False) -> bool:
    """
    Startup guard for MinIO default credentials.

    Returns True if the insecure default pair was detected (and we warned/blocked).

    By default this only emits a loud WARNING and returns True — the storage
    layer independently refuses to use MinIO with default creds and falls back
    to local disk. Set ``strict=True`` (or ``MINIO_BLOCK_DEFAULT_CREDS=true``)
    to instead raise RuntimeError and abort startup, enforcing fail-closed
    behaviour for production deployments.
    """
    if not minio_uses_default_credentials():
        return False

    msg = (
        "SECURITY ALERT: MinIO/S3 object storage is configured with the "
        "well-known default credentials (minioadmin/minioadmin). "
        "Anyone able to reach the MinIO console or S3 API can read, write, "
        "and delete all stored files. Generate a unique MINIO_ROOT_USER and "
        "MINIO_ROOT_PASSWORD (e.g. `make setup`) and rotate them on first "
        "deploy. The backend will use LOCAL disk storage instead of MinIO "
        "until this is fixed."
    )

    if strict or os.getenv("MINIO_BLOCK_DEFAULT_CREDS", "").lower() == "true":
        logger.error("❌ %s", msg)
        raise RuntimeError(msg)

    logger.warning("⚠️  %s", msg)
    return True


def run_security_startup_checks() -> None:
    """Run all security startup guards. Safe to call once at boot."""
    check_minio_credentials(strict=False)
