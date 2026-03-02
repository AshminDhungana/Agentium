"""
File upload and download API for chat attachments.
Handles multipart file uploads, storage, and retrieval.
"""

import os
import io
import uuid
import mimetypes
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Depends, status
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session
import aiofiles

from backend.models.database import get_db
from backend.core.auth import get_current_active_user
from backend.models.entities.user import User
from backend.services.storage_service import storage_service

router = APIRouter(prefix="/files", tags=["Files"])

MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB max file size
ALLOWED_EXTENSIONS = {
    'image': ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.bmp'],
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


@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload_files(
    files: List[UploadFile] = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Upload one or more files.
    Returns metadata for each uploaded file.
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No files provided"
        )

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

        # Read file content
        try:
            content = await file.read()
        except Exception as e:
            errors.append({
                "filename": file.filename,
                "error": f"Failed to read file: {str(e)}"
            })
            continue

        # Check file size
        if len(content) > MAX_FILE_SIZE:
            errors.append({
                "filename": file.filename,
                "error": f"File exceeds {MAX_FILE_SIZE / (1024*1024):.0f}MB limit ({len(content) / (1024*1024):.1f}MB)"
            })
            continue

        # Determine MIME type
        mime_type = file.content_type or mimetypes.guess_type(file.filename)[0] or 'application/octet-stream'
        category = get_file_category(file.filename)
        safe_filename = generate_safe_filename(file.filename)

        # Build S3 Object Key
        object_name = f"files/{current_user.id}/{safe_filename}"

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

        # Build response metadata
        file_info = {
            "id": str(uuid.uuid4()),
            "original_name": file.filename,
            "stored_name": safe_filename,
            "url": f"/api/v1/files/download/{current_user.id}/{safe_filename}",
            "type": mime_type,
            "category": category,
            "size": len(content),
            "uploaded_at": datetime.now(timezone.utc).isoformat()
        }
        uploaded_files.append(file_info)

    # If all files failed, return error
    if not uploaded_files and errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"errors": errors}
        )

    return {
        "success": True,
        "files": uploaded_files,
        "total_uploaded": len(uploaded_files),
        "errors": errors if errors else None
    }


@router.get("/download/{user_id}/{filename}")
async def download_file(
    user_id: str,
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Download a specific file.
    Users can only access their own files unless they're admin.
    """
    # Security check - users can only access their own files
    if str(current_user.id) != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    object_name = f"files/{user_id}/{filename}"
    url = storage_service.generate_presigned_url(object_name, expiration=3600)
    
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or failed to generate URL"
        )

    return RedirectResponse(url=url)


@router.get("/list")
async def list_files(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    List all files for the current user from S3.
    """
    prefix = f"files/{current_user.id}/"
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
            "url": f"/api/v1/files/download/{current_user.id}/{filename}",
            "size": size,
            "category": get_file_category(filename),
            "uploaded_at": str(obj.get('LastModified', ''))
        })

    # Sort by upload time (newest first)
    files.sort(key=lambda x: x["uploaded_at"], reverse=True)

    return {
        "files": files,
        "total": len(files),
        "storage_used_bytes": total_size
    }


@router.delete("/{filename}")
async def delete_file(
    filename: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Delete a file.
    """
    object_name = f"files/{current_user.id}/{filename}"
    
    success = storage_service.delete_file(object_name)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete file"
        )
        
    return {
        "success": True,
        "message": f"File {filename} deleted successfully"
    }


@router.get("/stats")
async def get_file_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_active_user)
):
    """
    Get file statistics for the current user from S3.
    """
    prefix = f"files/{current_user.id}/"
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

    # Calculate percentage
    stats["storage_used_percent"] = round(
        (stats["total_size_bytes"] / stats["storage_limit_bytes"]) * 100, 
        2
    )

    return stats


@router.get("/preview/{user_id}/{filename}")
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
    if str(current_user.id) != user_id and not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied"
        )

    media_type = mimetypes.guess_type(filename)[0] or 'application/octet-stream'

    # Only allow preview for safe types
    if not (media_type.startswith('image/') or media_type.startswith('video/') or media_type == 'application/pdf'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File type not supported for preview"
        )

    object_name = f"files/{user_id}/{filename}"
    url = storage_service.generate_presigned_url(object_name, expiration=3600)
    
    if not url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="File not found or failed to generate URL"
        )

    # For S3, presigned GETs often force download or rely on Content-Disposition.
    # A simple redirect is usually sufficient.
    return RedirectResponse(url=url)