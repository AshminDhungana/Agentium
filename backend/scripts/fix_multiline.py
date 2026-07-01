"""Fix multi-line raise HTTPException blocks using proper paren matching."""

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
    return text.strip().rstrip('"').rstrip("'").rstrip('",')


def slugify(text):
    text = clean_detail(text)
    if text.startswith('f"') or text.startswith("f'"):
        text = text[1:]
    text = re.sub(r'\{[^}]*\}', '', text)
    result = []
    for c in text:
        if c.isalnum() or c == ' ':
            result.append(c)
    parts = ''.join(result).split()
    if len(parts) > 5:
        parts = parts[:5]
    code = '_'.join(parts).upper()[:64]
    if not code:
        code = "ERROR"
    return code


def find_matching_paren(content, start):
    depth, i = 1, start
    while i < len(content):
        c = content[i]
        # Skip string literals
        if c == '"' or c == "'":
            if i + 2 < len(content) and content[i + 1] == c == content[i + 2]:
                q = c * 3
                i += 3
                while i + 2 < len(content) and content[i:i + 3] != q:
                    i += 1
                i += 3
            else:
                q = c
                i += 1
                while i < len(content) and content[i] != q:
                    if content[i] == '\\' and i + 1 < len(content):
                        i += 1
                    i += 1
                i += 1
            continue
        elif c == '(':
            depth += 1
        elif c == ')':
            depth -= 1
        if depth == 0:
            return i
        i += 1
    return -1


def parse_args(inner):
    status_code = "500"
    detail = None
    headers = None
    sc = re.search(r'status_code=\s*(\d+)', inner)
    if sc:
        status_code = sc.group(1)
    else:
        m = re.match(r'\s*(\d+)', inner)
        if m:
            status_code = m.group(1)
    dm = re.search(r'detail=([\s\S]*?)(?:,\s*(?:headers=|status_code=))', inner)
    if not dm:
        dm = re.search(r'detail=([\s\S]*?)$', inner)
    if dm:
        detail = dm.group(1).strip()
        if detail and detail[-1] == ',':
            detail = detail[:-1].strip()
    if not detail:
        parts = inner.split(',')
        if len(parts) >= 2:
            detail = parts[1].strip()
    hm = re.search(r'headers=\{([^}]+)\}', inner)
    if hm:
        headers = '{' + hm.group(1) + '}'
    return status_code, detail, headers


def convert_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
    original = content
    if 'HTTPException' not in content:
        return False
    idx = 0
    while True:
        match = content.find('raise HTTPException(', idx)
        if match == -1:
            break
        end = find_matching_paren(content, match + len('raise HTTPException('))
        if end == -1:
            idx = match + 1
            continue
        block = content[match:end + 1]
        # Only handle multi-line blocks
        if 'raise HTTPException(' in block[len('raise HTTPException('):]:
            # This is already a replacement (nested), skip
            pass
        inner = block[len('raise HTTPException('): -1]
        status_code, detail, headers = parse_args(inner)
        exc_class = STATUS_MAP.get(status_code, 'InternalServerError')
        if detail:
            code = slugify(detail)
            if headers:
                replacement = f'raise {exc_class}(error={detail}, code="{code}", headers={headers})'
            else:
                replacement = f'raise {exc_class}(error={detail}, code="{code}")'
        else:
            replacement = f'raise {exc_class}(error="An error occurred", code="UNKNOWN_ERROR")'
        content = content[:match] + replacement + content[end + 1:]
        idx = match + len(replacement)
    if content == original:
        return False
    if 'from backend.core.exceptions import' not in content:
        lines = content.split('\n')
        import_line = "from backend.core.exceptions import BadRequestError, UnauthorizedError, ForbiddenError, NotFoundError, ConflictError, TooLargeError, RateLimitError, InternalServerError, ServiceUnavailableError"
        for i in range(len(lines)):
            if 'from fastapi import' in lines[i]:
                has_except = 'except HTTPException' in content
                if not has_except:
                    lines[i] = lines[i].replace(', HTTPException', '').replace('HTTPException, ', '')
                lines.insert(i + 1, import_line)
                break
        content = '\n'.join(lines)
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return True


if __name__ == '__main__':
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path('.')
    files = list(target.rglob('*.py')) if target.is_dir() else [target]
    converted = 0
    for fp in files:
        if '__pycache__' in str(fp):
            continue
        try:
            if convert_file(fp):
                print(f'Converted: {fp}')
                converted += 1
        except Exception as e:
            print(f'Error on {fp}: {e}')
    print(f'Converted {converted}/{len(files)} files')
