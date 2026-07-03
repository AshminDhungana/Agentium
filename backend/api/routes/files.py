"""
File upload and download API for chat attachments.
Handles multipart file uploads, storage, and retrieval.

Changes vs original:
  - FIX: Stream-read in chunks to avoid loading entire file into RAM before size check
  - FIX: Magic-byte validation to prevent extension-spoofing attacks
  - FIX: SVG removed from image allowlist (XSS risk via embedded <script>)
  - NEW: PDF text extraction and image metadata extraction at upload time
  - NEW: extracted_text field added to upload response for AI consumption
"""

import os
import io
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.models.entities.user import User
from backend.services.storage_service import storage_service

from backend.api.schemas.examples import ErrorResponseExample, SuccessResponseExample, build_responses

router = APIRouter(prefix="/files", tags=["Files"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
ALLOWED_EXTENSIONS = {
    # SVG removed — SVG files can contain embedded <script> tags (XSS risk)
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'],
    'video': ['.mp4', '.webm', '.mov', '.avi', '.mkv'],
    'audio': ['.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.webm'],
    'document': ['.pdf', '.doc', '.docx', '.txt', '.rtf', '.odt'],
    'code': ['.py', '.js', '.ts', '.jsx', '.tsx', '.html', '.css', '.json', '.xml', '.yaml', '.yml', '.sql', '.md'],
    'archive': ['.zip', '.rar', '.7z', '.tar', '.gz', '.bz2'],
    'spreadsheet': ['.xls', '.xlsx', '.csv', '.ods'],
    'presentation': ['.ppt', '.pptx', '.odp']
}

# Flatten allowed extensions for validation
ALL_ALLOWED_EXTENSIONS = set()
for ext_list in ALLOWED_EXTENSIONS.values():
    ALL_ALLOWED_EXTENSIONS.update(ext_list)


def get_file_category(filename: str) -> str:
    """Determine file category based on extension."""
    ext = Path(filename).suffix.lower()
    for category, extensions in ALLOWED_EXTENSIONS.items():
        if ext in extensions:
            return category
    return 'other'


def get_file_icon(category: str) -> str:
    """Get emoji icon for file category."""
    icons = {
        'image': '🖼️',
        'video': '🎬',
        'audio': '🎵',
        'document': '📄',
        'code': '💻',
        'archive': '📦',
        'spreadsheet': '📊',
        'presentation': '📽️',
        'other': '📎'
    }
    return icons.get(category, '📎')


def format_file_size(bytes_size: int) -> str:
    """Format file size for human reading."""
    if bytes_size < 1024:
        return f"{bytes_size} B"
    elif bytes_size < 1024 * 1024:
        return f"{bytes_size / 1024:.1f} KB"
    elif bytes_size < 1024 * 1024 * 1024:
        return f"{bytes_size / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes_size / (1024 * 1024 * 1024):.1f} GB"


def is_allowed_file(filename: str) -> bool:
    """Check if file extension is allowed."""
    ext = Path(filename).suffix.lower()
    return ext in ALL_ALLOWED_EXTENSIONS


def generate_safe_filename(original_filename: str) -> str:
    """Generate a safe, unique filename for storage."""
    ext = Path(original_filename).suffix.lower()
    unique_id = str(uuid.uuid4())[:8]
    timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    return f"{timestamp}_{unique_id}{ext}"


async def _read_file_chunked(file: UploadFile, max_size: int) -> bytes:
    """
    Read an uploaded file in chunks, aborting early if max_size is exceeded.

    This prevents loading the entire file into RAM before the size check fires,
    which was a memory bomb vulnerability in the original implementation.

    Raises HTTPException 413 if the file exceeds max_size.
    """
    chunks: list[bytes] = []
    total = 0

    while True:
        chunk = await file.read(65536)  # 64KB chunks
        if not chunk:
            break
        total += len(chunk)
        if total > max_size:
            raise TooLargeError(error=(
                    f"File '{file.filename}' exceeds the "
                    f"{max_size // (1024 * 1024)}MB size limit"
                ), code="FFILE_EXCEEDS_THE_FMB_SIZE")
        chunks.append(chunk)

    return b"".join(chunks)


@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload Files",
    description="Upload one or more files. Returns metadata for each uploaded file, including extracted_text for PDFs and image metadata that the AI can consume directly.",
    responses=build_responses(None),
)
async def upload_files(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload one or more files.
    Returns metadata for each uploaded file, including extracted_text
    for PDFs and image metadata that the AI can consume directly.
    """
    from backend.services.file_processor import (
        verify_magic_bytes,
        extract_pdf_text,
        extract_image_metadata,
    )

    if not files:
        raise BadRequestError(error="No files provided", code="NO_FILES_PROVIDED")

    uploaded_files = []
    errors = []

    for file in files:
        # Validate filename
        if not file.filename:
            errors.append({"error": "File has no filename"})
            continue

        # Check file extension
        if not is_allowed_file(file.filename):
            errors.append({
                "filename": file.filename,
                "error": f"File type not allowed. Allowed: {', '.join(sorted(ALL_ALLOWED_EXTENSIONS))}"
            })
            continue

        # Read file content in chunks — aborts early if file is too large
        # This replaces the old: content = await file.read() + size check after
        try:
            content = await _read_file_chunked(file, MAX_FILE_SIZE)
        except HTTPException:
            errors.append({
                "filename": file.filename,
                "error": f"File exceeds {MAX_FILE_SIZE // (1024 * 1024)}MB limit"
            })
            continue
        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": f"Failed to read file: {str(e)}"
            })
            continue

        # Determine MIME type
        mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
        category = get_file_category(file.filename)

        # Magic byte validation — detect extension spoofing
        if not verify_magic_bytes(content, mime_type):
            errors.append({
                "filename": file.filename,
                "error": (
                    f"File content does not match declared type '{mime_type}'. "
                    "Upload rejected for security reasons."
                )
            })
            continue

        safe_filename = generate_safe_filename(file.filename)

        # Build S3 Object Key
        _uid = current_user.get("user_id") or current_user.get("id")
        object_name = f"files/{_uid}/{safe_filename}"

        # Upload to StorageService
        try:
            url = storage_service.upload_file(
                io.BytesIO(content),
                object_name=object_name,
                content_type=mime_type
            )
            if not url:
                raise Exception("StorageService returned None")
        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": f"Failed to upload file to storage: {str(e)}"
            })
            continue

        # ── Content extraction for AI consumption ─────────────────────────────
        # Extract text/metadata at upload time so it travels with the file
        # metadata and can be injected into the AI prompt without a second
        # round-trip to storage.
        extracted_text: Optional[str] = None

        if mime_type == "application/pdf":
            extracted_text = extract_pdf_text(content, max_chars=40_000)
            if extracted_text:
                # Log how much we extracted (useful for debugging large PDFs)
                import logging
                logging.getLogger(__name__).info(
                    "[files.py] Extracted %d chars from PDF: %s",
                    len(extracted_text), file.filename
                )

        elif mime_type.startswith("image/") and not mime_type == "image/svg+xml":
            meta = extract_image_metadata(content, file.filename)
            if meta:
                extracted_text = (
                    f"[Image file: {file.filename} | "
                    f"Format: {meta.get('format', 'unknown')} | "
                    f"Dimensions: {meta.get('size', 'unknown')} | "
                    f"Color mode: {meta.get('mode', 'unknown')}]"
                )

        elif category == "code" or mime_type.startswith("text/"):
            # Text-based files: decode and include directly (already safe as text)
            try:
                text_content = content.decode("utf-8", errors="replace")
                if text_content.strip():
                    # Cap at 20K chars for code files
                    cap = 20_000
                    if len(text_content) > cap:
                        extracted_text = text_content[:cap] + f"\n[... truncated at {cap} chars]"
                    else:
                        extracted_text = text_content
            except Exception:
                pass  # silently skip — not critical
        # ── End content extraction ─────────────────────────────────────────────

        # Build response metadata
        file_info = {
            "id": str(uuid.uuid4()),
            "original_name": file.filename,
            "stored_name": safe_filename,
            "url": f"/api/v1/files/download/{_uid}/{safe_filename}",
            "type": mime_type,
            "category": category,
            "size": len(content),
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            # NEW: populated when extraction succeeded, None otherwise
            # The frontend forwards this in the WebSocket message so the AI
            # receives file content without a second storage round-trip.
            "extracted_text": extracted_text,
        }
        uploaded_files.append(file_info)

    # If all files failed, return error
    if not uploaded_files and errors:
        raise BadRequestError(error={"errors": errors}, code="ERROR")

    return {
        "success": True,
        "files": uploaded_files,
        "total_uploaded": len(uploaded_files),
        "errors": errors if errors else None
    }


@router.get(
    "/list",
    summary="List Files",
    description="List all files for the current user from S3.",
    responses=build_responses(None),
)
async def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all files for the current user from S3.
    """
    user_id = current_user.get("user_id") or current_user.get("id")
    prefix  = f"files/{user_id}/"
    objects = storage_service.list_files(prefix)

    files = []
    total_size = 0

    for obj in objects:
        size = obj.get('Size', 0)
        total_size += size

        filename = obj['Key'].split("/")[-1]

        files.append({
            "filename": filename,
            "stored_name": filename,
            "url": f"/api/v1/files/download/{user_id}/{filename}",
            "size": size,
            "category": get_file_category(filename),
            "uploaded_at": str(obj.get('LastModified', ''))
        })

    files.sort(key=lambda x: x["uploaded_at"], reverse=True)

    return {
        "files": files,
        "total": len(files),
        "storage_used_bytes": total_size
    }


@router.get(
    "/stats",
    summary="Get File Stats",
    description="Get file statistics for the current user from S3. Must be defined before /{filename} and /download/{user_id}/{filename} to prevent FastAPI matching 'stats' as a path parameter.",
    responses=build_responses(None),
)
async def get_file_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get file statistics for the current user from S3.
    Must be defined before /{filename} and /download/{user_id}/{filename}
    to prevent FastAPI matching 'stats' as a path parameter.
    """
    user_id = current_user.get("user_id") or current_user.get("id")
    prefix  = f"files/{user_id}/"
    objects = storage_service.list_files(prefix)

    stats = {
        "total_files": 0,
        "total_size_bytes": 0,
        "by_category": {},
        "storage_limit_bytes": 500 * 1024 * 1024,  # 500MB limit per user
        "storage_used_percent": 0
    }

    for obj in objects:
        size = obj.get('Size', 0)
        filename = obj['Key'].split("/")[-1]
        category = get_file_category(filename)

        stats["total_files"] += 1
        stats["total_size_bytes"] += size

        if category not in stats["by_category"]:
            stats["by_category"][category] = 0
        stats["by_category"][category] += size

    stats["storage_used_percent"] = round(
        (stats["total_size_bytes"] / stats["storage_limit_bytes"]) * 100,
        2
    )

    return stats


@router.get(
    "/download/{user_id}/{filename}",
    summary="Download File",
    description="Download a specific file. Users can only access their own files unless they're admin. Behaviour differs by active storage backend: - S3/MinIO: redirects to a presigned URL. - Local:    streams the file directly from disk.",
    responses=build_responses(None),
)
async def download_file(
    user_id: str,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Download a specific file.
    Users can only access their own files unless they're admin.

    Behaviour differs by active storage backend:
      - S3/MinIO: redirects to a presigned URL.
      - Local:    streams the file directly from disk.
    """
    # Security check - users can only access their own files
    _cur_uid = current_user.get("user_id") or current_user.get("id")
    _cur_admin = current_user.get("is_admin", False)
    if str(_cur_uid) != user_id and not _cur_admin:
        raise ForbiddenError(error="Access denied", code="ACCESS_DENIED")

    object_name = f"files/{user_id}/{filename}"

    # ── Local filesystem backend: serve the file directly ────────────────────
    if storage_service.backend_name == "local":
        import os as _os
        local_root = _os.getenv("STORAGE_LOCAL_PATH", "./data/uploads")
        local_path = Path(local_root).resolve() / object_name
        if not local_path.exists():
            raise NotFoundError(error="File not found", code="FILE_NOT_FOUND")
        media_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        return FileResponse(
            path=str(local_path),
            media_type=media_type,
            filename=filename,
        )

    # ── S3/MinIO backend: redirect to presigned URL ───────────────────────────
    url = storage_service.generate_presigned_url(object_name, expiration=3600)
    if not url:
        raise NotFoundError(error="File not found or failed to generate URL", code="FILE_NOT_FOUND_OR_FAILED")
    return RedirectResponse(url=url)


@router.delete(
    "/{filename}",
    summary="Delete File",
    description="Delete a file.",
    responses=build_responses(None),
)
async def delete_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a file.
    """
    _uid        = current_user.get("user_id") or current_user.get("id")
    object_name = f"files/{_uid}/{filename}"
    
    success = storage_service.delete_file(object_name)

    if not success:
        raise InternalServerError(error=f"Failed to delete file", code="FAILED_TO_DELETE_FILE")
        
    return {
        "success": True,
        "message": f"File {filename} deleted successfully"
    }


@router.get(
    "/preview/{user_id}/{filename}",
    summary="Preview File",
    description="Preview a file (for images/videos that can be displayed inline). Same security as download but with inline disposition.",
    responses=build_responses(None),
)
async def preview_file(
    user_id: str,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Preview a file (for images/videos that can be displayed inline).
    Same security as download but with inline disposition.
    """
    # Security check
    _cur_uid = current_user.get("user_id") or current_user.get("id")
    _cur_admin = current_user.get("is_admin", False)
    if str(_cur_uid) != user_id and not _cur_admin:
        raise ForbiddenError(error="Access denied", code="ACCESS_DENIED")

    media_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # Only allow preview for safe types
    if not (media_type.startswith('image/') or media_type.startswith('video/') or media_type == 'application/pdf'):
        raise BadRequestError(error="File type not supported for preview", code="FILE_TYPE_NOT_SUPPORTED_FOR")

    object_name = f"files/{user_id}/{filename}"

    # ── Local filesystem backend: serve inline directly ───────────────────────
    if storage_service.backend_name == "local":
        import os as _os
        local_root = _os.getenv("STORAGE_LOCAL_PATH", "./data/uploads")
        local_path = Path(local_root).resolve() / object_name
        if not local_path.exists():
            raise NotFoundError(error="File not found", code="FILE_NOT_FOUND")
        return FileResponse(
            path=str(local_path),
            media_type=media_type,
            filename=filename,
        )

    # ── S3/MinIO backend: redirect to presigned URL ───────────────────────────
    url = storage_service.generate_presigned_url(object_name, expiration=3600)
    
    if not url:
        raise NotFoundError(error="File not found or failed to generate URL", code="FILE_NOT_FOUND_OR_FAILED")

    return RedirectResponse(url=url)