"""User profile endpoints: avatar upload and removal."""
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, Depends, status
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.models.entities.user import User
from backend.api.middleware.auth import get_current_active_user
from backend.services.storage_service import storage_service
from backend.services.file_processor import verify_magic_bytes
from backend.core.exceptions import (
    BadRequestError,
    TooLargeError,
    ServiceUnavailableError,
)

router = APIRouter(prefix="/users", tags=["Users"])

AVATAR_MAX_SIZE = 5 * 1024 * 1024  # 5 MB
AVATAR_ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
AVATAR_CONTENT_TYPES = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
}


async def _read_chunked(file: UploadFile, max_size: int) -> bytes:
    """Stream-read the upload in 64KB chunks, raising 413 past max_size."""
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(65536)
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise TooLargeError(
                error="Profile picture exceeds the 5MB size limit",
                code="AVATAR_TOO_LARGE",
            )
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/me/avatar", status_code=status.HTTP_201_CREATED)
async def upload_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Upload (or replace) the current user's profile picture."""
    ext = Path(file.filename).suffix.lower() if file.filename else ""
    if ext not in AVATAR_ALLOWED_EXT:
        raise BadRequestError(
            error="Unsupported image type. Use jpg, png, webp or gif.",
            code="AVATAR_BAD_TYPE",
        )

    content = await _read_chunked(file, AVATAR_MAX_SIZE)
    declared = file.content_type or AVATAR_CONTENT_TYPES.get(ext, "application/octet-stream")
    if not verify_magic_bytes(content, declared):
        raise BadRequestError(
            error="File content does not match its declared type.",
            code="AVATAR_MAGIC_MISMATCH",
        )

    # Best-effort cleanup of the previous object.
    if current_user.avatar_object_name:
        storage_service.delete_file(current_user.avatar_object_name)

    object_name = f"avatars/{current_user.id}/{uuid.uuid4().hex}{ext}"
    url = storage_service.upload_file(BytesIO(content), object_name, declared)
    if not url:
        raise ServiceUnavailableError(
            error="Avatar storage is unavailable.",
            code="AVATAR_STORAGE_FAILED",
        )

    current_user.avatar_url = url
    current_user.avatar_object_name = object_name
    db.commit()
    db.refresh(current_user)
    return {"avatar_url": url}


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def remove_avatar(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user),
):
    """Remove the current user's profile picture and delete the stored object."""
    if current_user.avatar_object_name:
        storage_service.delete_file(current_user.avatar_object_name)
    current_user.avatar_url = None
    current_user.avatar_object_name = None
    db.commit()
