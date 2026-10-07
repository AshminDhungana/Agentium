"""
File Processor Service
======================
Handles content extraction from uploaded files so the AI agent can
understand what the user has attached.

Responsibilities
----------------
- PDF text extraction (digital PDFs via pypdf; graceful on failures)
- Image metadata extraction (dimensions, format via Pillow)
- Magic-byte validation (prevents extension-spoofing attacks)
- Token-budgeted AI context assembly from multiple attachments
- Corruption detection and safe error reporting

Design principles
-----------------
- Every function is pure (no side effects, no DB calls).
- All failures are caught internally; callers receive None / empty dict.
- No function raises to its caller — graceful degradation is mandatory.
- Max-chars guards protect against oversized LLM context windows.
"""

from __future__ import annotations

import io

from pathlib import Path
from typing import Optional

from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)
# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum characters extracted from any single PDF (~40K chars ≈ ~10K tokens)
DEFAULT_MAX_PDF_CHARS: int = 40_000

# Maximum total characters across all attachments sent to AI
DEFAULT_MAX_TOTAL_CHARS: int = 30_000

# Magic byte signatures → canonical MIME prefix for validation
# Format: bytes_prefix → (mime_type_prefix, friendly_name)
_MAGIC_SIGNATURES: list[tuple[bytes, str, str]] = [
    (b"\x25\x50\x44\x46",          "application/pdf",  "PDF"),
    (b"\xff\xd8\xff",              "image/jpeg",       "JPEG"),
    (b"\x89\x50\x4e\x47\x0d\x0a", "image/png",        "PNG"),
    (b"\x47\x49\x46\x38",         "image/gif",        "GIF"),
    (b"\x52\x49\x46\x46",         "image/webp",       "WEBP"),   # RIFF prefix
    (b"\x42\x4d",                 "image/bmp",        "BMP"),
    (b"\x50\x4b\x03\x04",         "application/zip",  "ZIP"),
]

# MIME prefixes that are inherently text — skip magic check for these
_TEXT_MIME_PREFIXES: tuple[str, ...] = (
    "text/", "application/json", "application/xml",
    "application/javascript", "application/x-yaml",
)

# ---------------------------------------------------------------------------
# Magic Byte Validation
# ---------------------------------------------------------------------------

def verify_magic_bytes(content: bytes, declared_mime: str) -> bool:
    """
    Verify that file content matches its declared MIME type.

    Returns True when:
    - The file is a recognised text type (no binary signature to check)
    - No signature in our map matches the content (allow unknown formats through)
    - The detected signature is compatible with the declared MIME type

    Returns False ONLY when we can positively identify a mismatch
    (e.g. bytes start with %PDF but MIME is image/png).

    Args:
        content:      Raw file bytes (at least first 16 bytes are sufficient)
        declared_mime: MIME type string as received from the upload request
    """
    if not content:
        return True  # empty file — let size validation handle it

    # Text types have no binary magic — always pass
    if any(declared_mime.startswith(p) for p in _TEXT_MIME_PREFIXES):
        return True

    probe = content[:16]

    for signature, detected_mime_prefix, _ in _MAGIC_SIGNATURES:
        if probe.startswith(signature):
            # We recognised the file format — check compatibility
            declared_lower = declared_mime.lower()
            detected_lower = detected_mime_prefix.lower()

            # Exact prefix match or declared starts with detected's major type
            if declared_lower.startswith(detected_lower):
                return True

            # Special case: WEBP bytes start with RIFF — also allow image/*
            if signature == b"\x52\x49\x46\x46" and declared_lower.startswith("image/"):
                return True

            # Mismatch detected
            logger.warning(
                "[file_processor] Magic byte mismatch: declared=%s detected=%s",
                declared_mime, detected_mime_prefix,
            )
            return False

    # No signature matched — unknown format, pass through
    return True

# ---------------------------------------------------------------------------
# PDF Extraction
# ---------------------------------------------------------------------------

def extract_pdf_text(content: bytes, max_chars: int = DEFAULT_MAX_PDF_CHARS) -> Optional[str]:
    """
    Extract plain text from a PDF byte string using pypdf.

    - Processes pages sequentially and stops once max_chars is reached.
    - Page breaks are marked with a separator for readability.
    - Returns None when extraction fails (encrypted PDF, corrupt file, import error).

    Args:
        content:   Raw PDF bytes
        max_chars: Hard character cap on extracted text (default 40 000)

    Returns:
        Extracted text string, or None on any failure.
    """
    try:
        import pypdf  # installed: pypdf==6.9.1
    except ImportError:
        logger.error("[file_processor] pypdf not installed — PDF extraction unavailable")
        return None

    try:
        reader = pypdf.PdfReader(io.BytesIO(content))

        if reader.is_encrypted:
            logger.info("[file_processor] Skipping encrypted PDF")
            return None

        pages: list[str] = []
        total_chars = 0

        for page_num, page in enumerate(reader.pages, start=1):
            try:
                text = page.extract_text() or ""
            except Exception as page_err:
                logger.debug(
                    "[file_processor] Page %d extraction error: %s", page_num, page_err
                )
                text = ""

            if text:
                remaining = max_chars - total_chars
                if remaining <= 0:
                    break
                pages.append(text[:remaining])
                total_chars += min(len(text), remaining)

        if not pages:
            return None

        separator = "\n\n--- Page Break ---\n\n"
        result = separator.join(pages)

        # Final safety truncation
        if len(result) > max_chars:
            result = result[:max_chars] + f"\n\n[... truncated at {max_chars} characters]"

        return result.strip() or None

    except Exception as exc:
        logger.warning("[file_processor] PDF extraction failed: %s", exc)
        return None

# ---------------------------------------------------------------------------
# Image Metadata Extraction
# ---------------------------------------------------------------------------

def extract_image_metadata(content: bytes, filename: str) -> dict:
    """
    Extract safe metadata from image bytes using Pillow.

    Returns a dict with keys: format, size, mode, width, height.
    Returns an empty dict on any failure (missing Pillow, corrupt file, etc.).

    Args:
        content:  Raw image bytes
        filename: Original filename (used for format hint)
    """
    try:
        from PIL import Image  # installed: pillow==12.1.1
    except ImportError:
        logger.warning("[file_processor] Pillow not installed — image metadata unavailable")
        return {}

    try:
        img = Image.open(io.BytesIO(content))
        return {
            "format":  img.format or Path(filename).suffix.lstrip(".").upper() or "unknown",
            "width":   img.width,
            "height":  img.height,
            "size":    f"{img.width}×{img.height}",
            "mode":    img.mode,
        }
    except Exception as exc:
        logger.debug("[file_processor] Image metadata extraction failed: %s", exc)
        return {}

# ---------------------------------------------------------------------------
# AI Context Builder
# ---------------------------------------------------------------------------

def build_file_context_for_ai(
    attachments: list[dict],
    max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
) -> str:
    """
    Build a single, token-budgeted context string from attachment metadata.

    Each attachment dict is expected to have at minimum:
      - name (str): original filename
      - type (str): MIME type
      - size (int): file size in bytes
      - extracted_text (str | None): server-extracted text content

    Files with no extracted text get a compact one-line descriptor so the
    AI still knows the attachment exists and what type it is.

    Budget is shared fairly across all files — each file gets an equal
    portion. Files with more text than their portion will be truncated with
    a clear note.

    Args:
        attachments:     List of attachment metadata dicts from the frontend.
        max_total_chars: Maximum combined characters to inject (default 30 000).

    Returns:
        Formatted context string ready to append to the user message.
    """
    if not attachments:
        return ""

    num_files = len(attachments)
    budget_per_file = max(max_total_chars // num_files, 500)  # at least 500 chars each

    parts: list[str] = []

    for att in attachments:
        name = att.get("name") or att.get("original_name") or "unknown"
        mime = att.get("type") or "application/octet-stream"
        size = att.get("size") or 0
        text = att.get("extracted_text") or ""

        size_str = _format_size(size)
        header = f"📎 Attached File: {name} ({mime}, {size_str})"

        if text:
            if len(text) > budget_per_file:
                truncated_text = text[:budget_per_file]
                omitted = len(text) - budget_per_file
                content_block = (
                    f"{header}\n"
                    f"--- Content ---\n"
                    f"{truncated_text}\n"
                    f"[... {omitted} additional characters omitted due to context limit]\n"
                    f"--- End of {name} ---"
                )
            else:
                content_block = (
                    f"{header}\n"
                    f"--- Content ---\n"
                    f"{text}\n"
                    f"--- End of {name} ---"
                )
        else:
            # No extractable text — at minimum describe the file
            content_block = (
                f"{header}\n"
                f"[Binary file — no text content extractable. "
                f"The AI acknowledges this file was attached but cannot read its contents.]"
            )

        parts.append(content_block)

    return "\n\n".join(parts)

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _format_size(bytes_count: int) -> str:
    """Return a human-readable file size string."""
    if bytes_count < 1024:
        return f"{bytes_count} B"
    if bytes_count < 1024 * 1024:
        return f"{bytes_count / 1024:.1f} KB"
    return f"{bytes_count / (1024 * 1024):.1f} MB"