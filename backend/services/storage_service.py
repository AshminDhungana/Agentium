"""
Storage Service — S3/MinIO primary with automatic local filesystem fallback.

Selection logic (at startup):
  1. If AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY are set AND they are NOT the
     insecure default (minioadmin/minioadmin) AND the S3/MinIO endpoint is
     reachable → use S3Backend.
  2. Otherwise → use LocalBackend and log a clear warning.

Using the default MinIO credentials is treated as "not properly configured":
the backend refuses to talk to MinIO with default creds and stores files on
LOCAL disk inside the container instead. Set unique MINIO_ROOT_USER /
MINIO_ROOT_PASSWORD to enable S3/MinIO.

All callers use the same StorageService interface regardless of backend.

Environment variables
---------------------
S3_ENDPOINT            MinIO / custom endpoint URL  (e.g. http://minio:9000)
                       Omit for real AWS S3.
AWS_ACCESS_KEY_ID      S3 / MinIO access key
AWS_SECRET_ACCESS_KEY  S3 / MinIO secret key
AWS_REGION             Default: us-east-1
S3_BUCKET_NAME         Default: agentium-media
S3_FORCE_PATH_STYLE    true (default) — required for MinIO
STORAGE_LOCAL_PATH     Local fallback root dir. Default: ./data/uploads
APP_BASE_URL           Used to build download URLs in local mode.
                       Default: from settings.BASE_API_URL
"""

import io
import os
import logging
import shutil
from backend.core.config import settings
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Dict, Any, List, Optional

logger = logging.getLogger(__name__)

# Well-known insecure MinIO default shipped by the old Compose config. The
# backend refuses to use MinIO with these credentials and falls back to local
# disk (see _init_backend). Must stay in sync with
# backend/core/security_checks.py.
_DEFAULT_MINIO_USER = "minioadmin"
_DEFAULT_MINIO_PASSWORD = "minioadmin"


# ── Read environment ──────────────────────────────────────────────────────────

_ACCESS_KEY       = os.getenv("AWS_ACCESS_KEY_ID", "").strip()
_SECRET_KEY       = os.getenv("AWS_SECRET_ACCESS_KEY", "").strip()
_S3_ENDPOINT      = os.getenv("S3_ENDPOINT", "").strip()          # blank → real AWS
_BUCKET           = os.getenv("S3_BUCKET_NAME", "agentium-media")
_REGION           = os.getenv("AWS_REGION", "us-east-1")
_FORCE_PATH_STYLE = os.getenv("S3_FORCE_PATH_STYLE", "true").lower() == "true"
_LOCAL_ROOT       = Path(os.getenv("STORAGE_LOCAL_PATH", "./data/uploads")).resolve()
_APP_BASE_URL     = os.getenv("APP_BASE_URL", settings.BASE_API_URL).rstrip("/")


# ─────────────────────────────────────────────────────────────────────────────
# S3 / MinIO backend
# ─────────────────────────────────────────────────────────────────────────────

class _S3Backend:
    """Wraps boto3 for S3 / MinIO."""

    name = "s3"

    def __init__(self):
        """Initialize the S3 client and ensure the bucket exists."""
        import boto3
        from botocore.config import Config

        self._bucket = _BUCKET
        self._endpoint = _S3_ENDPOINT or None          # None → real AWS

        self._client = boto3.client(
            "s3",
            endpoint_url=self._endpoint,
            aws_access_key_id=_ACCESS_KEY,
            aws_secret_access_key=_SECRET_KEY,
            region_name=_REGION,
            config=Config(
                signature_version="s3v4",
                s3={"addressing_style": "path" if _FORCE_PATH_STYLE else "auto"},
            ),
        )
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Create the bucket if it does not already exist."""
        from botocore.exceptions import ClientError
        try:
            self._client.head_bucket(Bucket=self._bucket)
            logger.info("✅ [Storage/S3] Bucket '%s' confirmed.", self._bucket)
        except ClientError as exc:
            code = exc.response["Error"]["Code"]
            if code in ("404", "NoSuchBucket"):
                if _REGION == "us-east-1":
                    self._client.create_bucket(Bucket=self._bucket)
                else:
                    self._client.create_bucket(
                        Bucket=self._bucket,
                        CreateBucketConfiguration={"LocationConstraint": _REGION},
                    )
                logger.info("✅ [Storage/S3] Bucket '%s' created.", self._bucket)
            else:
                raise   # permission errors or network issues bubble up

    # ── Interface ─────────────────────────────────────────────────────────────

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> Optional[str]:
        """Upload a file object to S3 and return its public URL."""
        from botocore.exceptions import ClientError
        try:
            self._client.upload_fileobj(
                file_obj,
                self._bucket,
                object_name,
                ExtraArgs={"ContentType": content_type},
            )
            return self._public_url(object_name)
        except ClientError as exc:
            logger.error("[Storage/S3] Upload failed for '%s': %s", object_name, exc)
            return None

    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        """Generate a temporary presigned URL for the given object."""
        from botocore.exceptions import ClientError
        try:
            return self._client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self._bucket, "Key": object_name},
                ExpiresIn=expiration,
            )
        except ClientError as exc:
            logger.error("[Storage/S3] Presigned URL failed for '%s': %s", object_name, exc)
            return None

    def delete_file(self, object_name: str) -> bool:
        """Delete an object from S3 and return whether it succeeded."""
        try:
            self._client.delete_object(Bucket=self._bucket, Key=object_name)
            return True
        except ClientError as exc:
            logger.error("[Storage/S3] Delete failed for '%s': %s", object_name, exc)
            return False

    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """List S3 objects under the given prefix."""
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            result = []
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix):
                result.extend(page.get("Contents", []))
            return result
        except ClientError as exc:
            logger.error("[Storage/S3] List failed for prefix '%s': %s", prefix, exc)
            return []

    def _public_url(self, object_name: str) -> str:
        """Return the public HTTP(S) URL for an S3 object."""
        if self._endpoint:
            base = self._endpoint.rstrip("/")
            return f"{base}/{self._bucket}/{object_name}"
        return f"https://{self._bucket}.s3.{_REGION}.amazonaws.com/{object_name}"


# ─────────────────────────────────────────────────────────────────────────────
# Local filesystem fallback backend
# ─────────────────────────────────────────────────────────────────────────────

class _LocalBackend:
    """
    Stores files under STORAGE_LOCAL_PATH.

    Directory layout mirrors the S3 object key:
        <_LOCAL_ROOT> / files / <user_id> / <filename>

    list_files() returns dicts shaped like S3 Contents entries so callers
    need no changes.
    """

    name = "local"

    def __init__(self):
        """Initialize the local storage root directory."""
        _LOCAL_ROOT.mkdir(parents=True, exist_ok=True)
        logger.warning(
            "⚠️  [Storage] S3/MinIO credentials missing or unreachable. "
            "Falling back to LOCAL storage at: %s  "
            "Set AWS_ACCESS_KEY_ID + AWS_SECRET_ACCESS_KEY "
            "(and S3_ENDPOINT for MinIO) to enable S3.",
            _LOCAL_ROOT,
        )

    # ── Interface ─────────────────────────────────────────────────────────────

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> Optional[str]:
        """Copy a file object to local disk and return its URL."""
        dest = _LOCAL_ROOT / object_name
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            with open(dest, "wb") as fh:
                shutil.copyfileobj(file_obj, fh)
            logger.debug("[Storage/Local] Saved '%s'", dest)
            return self._public_url(object_name)
        except OSError as exc:
            logger.error("[Storage/Local] Upload failed for '%s': %s", object_name, exc)
            return None

    def generate_presigned_url(self, object_name: str, expiration: int = 3600) -> Optional[str]:
        """
        Local mode has no real presigned URLs — return a plain API download URL.
        The `expiration` parameter is accepted but ignored.
        """
        dest = _LOCAL_ROOT / object_name
        if not dest.exists():
            logger.warning("[Storage/Local] File not found: '%s'", dest)
            return None
        return self._public_url(object_name)

    def delete_file(self, object_name: str) -> bool:
        """Delete a local file by its object name."""
        dest = _LOCAL_ROOT / object_name
        try:
            if dest.exists():
                dest.unlink()
            return True
        except OSError as exc:
            logger.error("[Storage/Local] Delete failed for '%s': %s", object_name, exc)
            return False

    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """
        Returns dicts shaped like S3 Contents entries:
          { 'Key': str, 'Size': int, 'LastModified': datetime }
        """
        search_root = _LOCAL_ROOT / prefix
        if not search_root.exists():
            return []
        entries = []
        for path in search_root.rglob("*"):
            if path.is_file():
                stat = path.stat()
                rel_key = str(path.relative_to(_LOCAL_ROOT))
                entries.append(
                    {
                        "Key": rel_key,
                        "Size": stat.st_size,
                        "LastModified": datetime.fromtimestamp(
                            stat.st_mtime, tz=timezone.utc
                        ),
                    }
                )
        return entries

    def _public_url(self, object_name: str) -> str:
        """Return the API download URL for a locally stored object."""
        # object_name: "files/<user_id>/<filename>"
        parts = Path(object_name).parts
        if len(parts) >= 3:
            user_id, filename = parts[1], parts[2]
            return f"{_APP_BASE_URL}/api/v1/files/download/{user_id}/{filename}"
        return f"{_APP_BASE_URL}/api/v1/files/local/{object_name}"


# ─────────────────────────────────────────────────────────────────────────────
# StorageService — public façade
# ─────────────────────────────────────────────────────────────────────────────

class StorageService:
    """
    Public interface used by the rest of the application.

    Delegates every call to either _S3Backend or _LocalBackend depending on
    what is available at startup.  The backend is chosen once and never changes
    during a process lifetime.
    """

    def __init__(self):
        """Select and initialize the active storage backend."""
        self._backend = self._init_backend()
        logger.info(
            "✅ [Storage] Active backend: %s",
            self._backend.name.upper(),
        )

    # ── Backend selection ─────────────────────────────────────────────────────

    @staticmethod
    def _init_backend():
        """Try S3; fall back to local on any failure or insecure defaults."""
        # No credentials at all → skip S3 attempt immediately
        if not _ACCESS_KEY or not _SECRET_KEY:
            logger.warning(
                "[Storage] AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY not set. "
                "Skipping S3 init."
            )
            return _LocalBackend()

        # Insecure default credentials (minioadmin/minioadmin) → refuse S3.
        # Storing data in MinIO with the well-known default is a critical risk,
        # so we fall back to local disk inside the container instead.
        if _ACCESS_KEY == _DEFAULT_MINIO_USER and _SECRET_KEY == _DEFAULT_MINIO_PASSWORD:
            logger.warning(
                "[Storage] MinIO/S3 is configured with the insecure default "
                "credentials (minioadmin/minioadmin). Refusing S3 backend — "
                "falling back to LOCAL storage at: %s. "
                "Set unique MINIO_ROOT_USER / MINIO_ROOT_PASSWORD to enable MinIO.",
                _LOCAL_ROOT,
            )
            return _LocalBackend()

        try:
            backend = _S3Backend()
            return backend
        except Exception as exc:
            logger.warning(
                "[Storage] S3/MinIO init failed (%s). Activating local fallback.", exc
            )
            return _LocalBackend()

    # ── Public interface (mirrors both backends) ──────────────────────────────

    def upload_file(
        self,
        file_obj: BinaryIO,
        object_name: str,
        content_type: str = "application/octet-stream",
    ) -> Optional[str]:
        """Upload a file and return its URL, or None on failure."""
        return self._backend.upload_file(file_obj, object_name, content_type)

    def generate_presigned_url(
        self, object_name: str, expiration: int = 3600
    ) -> Optional[str]:
        """Return a URL to access the object (presigned for S3, API URL for local)."""
        return self._backend.generate_presigned_url(object_name, expiration)

    def delete_file(self, object_name: str) -> bool:
        """Delete an object. Returns True on success."""
        return self._backend.delete_file(object_name)

    def list_files(self, prefix: str = "") -> List[Dict[str, Any]]:
        """
        List objects under prefix.
        Returns list of dicts with at least: Key, Size, LastModified.
        """
        return self._backend.list_files(prefix)

    @property
    def backend_name(self) -> str:
        """'s3' or 'local' — useful for health-check endpoints."""
        return self._backend.name


# ── Module-level singleton ────────────────────────────────────────────────────
# Instantiated once at import time. Any startup error is caught internally
# and the local fallback is activated, so the import never raises.

storage_service = StorageService()