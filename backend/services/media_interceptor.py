"""
Media Interceptor — System-Generated Media Interception (Issue #11)

Parses LLM responses for media references (Markdown images, raw media URLs),
downloads them via httpx, stores permanently via StorageService, and rewrites
the response text with permanent S3/MinIO URLs.
"""

from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass
from io import BytesIO
from typing import List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from backend.services.storage_service import storage_service

logger = logging.getLogger(__name__)


@dataclass
class MediaMatch:
    """A detected media reference in text."""
    original: str          # Full matched text (markdown or raw URL)
    url: str               # Extracted URL
    alt_text: str          # Alt text for markdown, empty for raw URLs
    start: int             # Start index in source text
    end: int               # End index in source text (exclusive)
    is_markdown: bool      # True if ![alt](url), False if raw URL


class MediaInterceptor:
    """
    Detects, downloads, and stores media referenced in LLM-generated text.

    Supported formats: PNG, JPG, JPEG, GIF, WebP, SVG, MP4
    Detection: Markdown ![alt](url) and bare URLs ending in those extensions.
    """

    # Media file extensions to intercept (lowercase, with dot)
    MEDIA_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".mp4"})

    # Regex for Markdown image syntax: ![alt text](url)
    # Captures: alt text (group 1), URL (group 2)
    MARKDOWN_IMAGE_RE = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)')

    # Regex for raw URLs ending in media extensions
    # Matches http(s)://... up to whitespace or closing punctuation
    # Allows dots in URL path, excludes trailing punctuation
    RAW_URL_RE = re.compile(
        r'(https?://[^\s\)\]\}]+)',
        re.IGNORECASE
    )

    # Default httpx timeout for media downloads
    DOWNLOAD_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

    @classmethod
    def detect_media_urls(cls, text: str) -> List[MediaMatch]:
        """
        Find all media references in text.

        Returns list of MediaMatch sorted by start position (earliest first).
        Overlapping matches resolved by preferring Markdown syntax.
        """
        matches: List[MediaMatch] = []

        # 1. Find Markdown images first (higher priority)
        for m in cls.MARKDOWN_IMAGE_RE.finditer(text):
            url = m.group(2).strip()
            if cls._is_media_url(url):
                matches.append(MediaMatch(
                    original=m.group(0),
                    url=url,
                    alt_text=m.group(1),
                    start=m.start(),
                    end=m.end(),
                    is_markdown=True
                ))

        # 2. Find raw URLs (but skip those already inside markdown matches)
        markdown_ranges = [(m.start, m.end) for m in matches]

        for m in cls.RAW_URL_RE.finditer(text):
            url = m.group(1).strip()
            # Strip trailing punctuation that's not part of the URL
            url = url.rstrip('.,;:)}]')
            # Skip if this URL is inside a markdown image we already matched
            if any(start <= m.start() < end for start, end in markdown_ranges):
                continue
            if cls._is_media_url(url):
                matches.append(MediaMatch(
                    original=url,
                    url=url,
                    alt_text="",
                    start=m.start(),
                    end=m.start() + len(url),  # Adjust end to stripped length
                    is_markdown=False
                ))

        # Sort by position for stable replacement
        matches.sort(key=lambda x: x.start)
        return matches

    @classmethod
    def _is_media_url(cls, url: str) -> bool:
        """Check if URL ends with a known media extension."""
        # Strip query params and fragment for extension check
        clean_url = url.split("?")[0].split("#")[0].lower()
        return any(clean_url.endswith(ext) for ext in cls.MEDIA_EXTENSIONS)

    @classmethod
    async def download_media(
        cls,
        url: str,
        client: httpx.AsyncClient
    ) -> Optional[Tuple[bytes, str]]:
        """
        Download media from URL.

        Returns (content_bytes, content_type) on success, None on failure.
        Failures are logged but don't raise — caller decides fallback behavior.
        """
        try:
            response = await client.get(url, timeout=cls.DOWNLOAD_TIMEOUT, follow_redirects=True)
            if response.status_code != 200:
                logger.warning(f"[MediaInterceptor] Download failed {response.status_code}: {url}")
                return None

            content_type = response.headers.get("content-type", "application/octet-stream")
            return response.content, content_type

        except httpx.TimeoutException:
            logger.warning(f"[MediaInterceptor] Download timeout: {url}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"[MediaInterceptor] Download error: {url} — {e}")
            return None

    @classmethod
    async def intercept_and_store(
        cls,
        text: str,
        user_id: str,
        db: Session,
        http_client: Optional[httpx.AsyncClient] = None
    ) -> Tuple[str, List[str]]:
        """
        Full interception pipeline: detect -> download -> store -> rewrite.

        Args:
            text: LLM response text potentially containing media references
            user_id: Sovereign user ID (for storage path: files/<user_id>/)
            db: SQLAlchemy session (available for future metadata persistence)
            http_client: Reused AsyncClient (created if not provided)

        Returns:
            Tuple of (rewritten_text, list_of_new_storage_urls)
        """
        matches = cls.detect_media_urls(text)
        if not matches:
            return text, []

        # Use provided client or create temporary one
        client_provided = http_client is not None
        if http_client is None:
            http_client = httpx.AsyncClient(timeout=cls.DOWNLOAD_TIMEOUT)

        new_urls: List[str] = []
        # Build replacement map: original_text -> replacement_text
        replacements: List[Tuple[str, str]] = []  # (original_matched_text, replacement_text)

        try:
            for match in matches:
                downloaded = await cls.download_media(match.url, http_client)
                if downloaded is None:
                    # Graceful failure: keep original, log already done in download_media
                    continue

                content_bytes, content_type = downloaded
                # Generate storage object name: files/<user_id>/<uuid>.<ext>
                ext = cls._guess_extension(match.url, content_type)
                object_name = f"files/{user_id}/{uuid.uuid4().hex}{ext}"

                # Upload to StorageService (S3/MinIO or local fallback)
                file_obj = BytesIO(content_bytes)
                storage_url = storage_service.upload_file(file_obj, object_name, content_type)

                if storage_url is None:
                    logger.warning(f"[MediaInterceptor] Storage upload failed for {match.url}")
                    continue

                new_urls.append(storage_url)

                # Build replacement text
                if match.is_markdown:
                    # Preserve alt text: ![alt](new_url)
                    replacement = f"![{match.alt_text}]({storage_url})"
                else:
                    # Raw URL replacement
                    replacement = storage_url

                replacements.append((match.original, replacement))

        finally:
            if not client_provided:
                await http_client.aclose()

        # Apply replacements in reverse order (end to start) to preserve indices
        rewritten = text
        for original, replacement in reversed(replacements):
            # Find last occurrence of original in rewritten (handles duplicates)
            idx = rewritten.rfind(original)
            if idx >= 0:
                rewritten = rewritten[:idx] + replacement + rewritten[idx + len(original):]

        return rewritten, new_urls

    @staticmethod
    def _guess_extension(url: str, content_type: str) -> str:
        """Determine file extension from URL or content-type."""
        # Try URL first
        clean_url = url.split("?")[0].split("#")[0].lower()
        for ext in MediaInterceptor.MEDIA_EXTENSIONS:
            if clean_url.endswith(ext):
                return ext
        # Fallback to content-type mapping
        ct_map = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
            "video/mp4": ".mp4",
        }
        return ct_map.get(content_type.lower(), ".bin")