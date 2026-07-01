#!/usr/bin/env python3
"""Convert HTTPException raises to typed exceptions across all route files."""

import re
import sys
from pathlib import Path

STATUS_MAP = {
    "400": "BadRequestError", "401": "UnauthorizedError", "403": "ForbiddenError",
    "404": "NotFoundError", "409": "ConflictError", "413": "TooLargeError",
    "422": "BadRequestError", "429": "RateLimitError",
    "500": "InternalServerError", "503": "ServiceUnavailableError",
}


def clean_detail(text):
    return text.strip().rstrip('"').rstrip("'").rstrip('","')


def _replace_keyword(m):
    """Replace a single-line keyword-style HTTPException, skipping nested parens."""
    detail = m.group(3).strip()
    if '(' in detail or ')' in detail:
        return m.group(0)  # Skip – can't safely determine the closing paren
    return f"{m.group(1)}raise {STATUS_MAP.get(m.group(2))}(error={detail}, code=\"{slugify(detail)}\")"


def _replace_positional(m):
    """Replace a single-line positional-style HTTPException, skipping nested parens."""
    detail = m.group(3).strip()
    if '(' in detail or ')' in detail:
        return m.group(0)  # Skip – can't safely determine the closing paren
    return f"{m.group(1)}raise {STATUS_MAP.get(m.group(2))}(error={detail}, code=\"{slugify(detail)}\")"


def slugify(text):
    text = clean_detail(text)
    # Strip f-string prefix so codes don't start with F
    if text.startswith('f"') or text.startswith("f'"):
        text = text[1:]
    # Remove f-string variable placeholders like {var}
    text = re.sub(r'\{[^}]*\}', '', text)
    result = []
    for c in text:
        if c.isalnum() or c == ' ':
            result.append(c)
    parts = ''.join(result).split()
    if len(parts) > 5:
        parts = parts[:5]
    return '_'.join(parts).upper()[:64]


def convert_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original = content

    if 'HTTPException' not in content:
        return False

    has_except = 'except HTTPException' in content

    # Replace status constants
    content = content.replace('status.HTTP_400_BAD_REQUEST', '400')
    content = content.replace('status.HTTP_401_UNAUTHORIZED', '401')
    content = content.replace('status.HTTP_403_FORBIDDEN', '403')
    content = content.replace('status.HTTP_404_NOT_FOUND', '404')
    content = content.replace('status.HTTP_409_CONFLICT', '409')
    content = content.replace('status.HTTP_413_REQUEST_ENTITY_TOO_LARGE', '413')
    content = content.replace('status.HTTP_422_UNPROCESSABLE_ENTITY', '422')
    content = content.replace('status.HTTP_429_TOO_MANY_REQUESTS', '429')
    content = content.replace('status.HTTP_500_INTERNAL_SERVER_ERROR', '500')
    content = content.replace('status.HTTP_503_SERVICE_UNAVAILABLE', '503')

    # Replace single-line keyword style: raise HTTPException(status_code=..., detail=...)
    content = re.sub(
        r'(\s+)raise HTTPException[(]\s*status_code\s*=\s*(\d+)\s*,\s*detail\s*=\s*(.+?)[)]',
        _replace_keyword,
        content
    )

    # Replace single-line positional style: raise HTTPException(404, "msg")
    content = re.sub(
        r'(\s+)raise HTTPException[(]\s*(\d+)\s*,\s*(.+?)[)]',
        _replace_positional,
        content
    )

    if content == original:
        return False

    # Add typed exceptions import
    if 'from backend.core.exceptions import' not in content:
        lines = content.split('\n')
        import_line = "from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError"
        for idx in range(len(lines)):
            if 'from fastapi import' in lines[idx]:
                if not has_except:
                    lines[idx] = lines[idx].replace(', HTTPException', '').replace('HTTPException, ', '')
                lines.insert(idx + 1, import_line)
                break
        content = '\n'.join(lines)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

    return True


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python convert_exceptions.py <file_or_directory>")
        sys.exit(1)

    target = Path(sys.argv[1])
    files = []
    if target.is_file():
        files = [target]
    elif target.is_dir():
        for f in target.rglob("*.py"):
            if '__pycache__' in str(f):
                continue
            files.append(f)

    converted = 0
    for fp in files:
        success = convert_file(fp)
        if success:
            print(f"Converted: {fp}")
            converted += 1

    print(f"Converted {converted}/{len(files)} files")
