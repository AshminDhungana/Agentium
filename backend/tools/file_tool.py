import os
import shutil
from typing import Dict, Any

# Binary file magic byte signatures — used to detect binary files before
# attempting a UTF-8 decode which would silently corrupt or error on them.
_BINARY_SIGNATURES: tuple[bytes, ...] = (
    b"\x25\x50\x44\x46",          # %PDF
    b"\xff\xd8\xff",              # JPEG
    b"\x89\x50\x4e\x47",         # PNG
    b"\x47\x49\x46\x38",         # GIF
    b"\x52\x49\x46\x46",         # RIFF (WEBP, WAV, AVI)
    b"\x50\x4b\x03\x04",         # ZIP / DOCX / XLSX / PPTX
    b"\x7f\x45\x4c\x46",         # ELF binary
    b"\x4d\x5a",                  # Windows EXE/DLL (MZ)
    b"\xd0\xcf\x11\xe0",         # MS Compound (old .doc, .xls, .ppt)
)


def _is_binary_file(filepath: str) -> bool:
    """
    Probe the first 512 bytes of a file to detect binary content.

    Returns True if:
    - The file starts with a known binary magic signature, OR
    - The probe bytes contain a null byte (strong indicator of binary data)

    This prevents read_file() from silently corrupting binary files or
    returning garbled content when a PDF or image path is passed.
    """
    try:
        with open(filepath, 'rb') as f:
            probe = f.read(512)
        # Null byte check — reliable binary indicator for most formats
        if b'\x00' in probe:
            return True
        # Known magic signature check
        for sig in _BINARY_SIGNATURES:
            if probe.startswith(sig):
                return True
        return False
    except OSError:
        return False


class FileSystemTool:
    """Tool for agents to manage files on the local filesystem."""

    def read_file(
        self,
        filepath: str,
        offset: int = 1,
        limit: int | None = None,
        char_limit: int = 1000,
    ) -> Dict[str, Any]:
        """
        Read text file contents.

        Two modes:
        - Whole-file (default): offset=1 and limit=None. Returns raw text
          capped at char_limit*100 characters (legacy behavior).
        - Precise (line-based): offset/limit select an inclusive 1-based line
          range and the returned content is line-numbered ("%6d\\t" prefix),
          matching text_editor's view format.

        Returns an error dict (without raising) if:
        - The file is binary (PDF, image, archive, etc.)
        - The file cannot be decoded as UTF-8.
        - The path does not exist or is not accessible.
        - In precise mode, offset is out of range.

        Args:
            filepath:   Absolute or relative path to the file.
            offset:     1-based start line for precise mode (default 1).
            limit:      Number of lines to return in precise mode (None = whole file).
            char_limit: Legacy whole-file char cap = limit * 100 characters.
        """
        try:
            if _is_binary_file(filepath):
                return {
                    "status": "error",
                    "path": filepath,
                    "error": (
                        f"'{os.path.basename(filepath)}' is a binary file "
                        "(PDF, image, archive, etc.) and cannot be read as text. "
                        "Upload the file via the chat interface so the AI can "
                        "process its contents."
                    ),
                }

            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            total_lines = content.count("\n") + (0 if content.endswith("\n") or content == "" else 1)
            if content == "":
                total_lines = 0

            precise = (offset != 1) or (limit is not None)
            if not precise:
                char_cap = char_limit * 100
                truncated = len(content) > char_cap
                return {
                    "status":    "success",
                    "path":      filepath,
                    "content":   content[:char_cap],
                    "size":      len(content),
                    "total_lines": total_lines,
                    "truncated": truncated,
                }

            # Precise (line-based) mode
            lines = content.splitlines()
            total = len(lines)
            if offset < 1 or offset > total:
                return {
                    "status": "error",
                    "path":   filepath,
                    "error":  f"offset out of range (file has {total} lines)",
                }
            end = total if limit is None else min(offset + limit - 1, total)
            selected = lines[offset - 1 : end]
            numbered = "\n".join(
                f"{i + offset:>6}\t{line}" for i, line in enumerate(selected)
            )
            truncated = (limit is not None) and (offset + limit - 1 < total)
            return {
                "status":     "success",
                "path":       filepath,
                "total_lines": total,
                "content":    numbered,
                "truncated":  truncated,
            }
        except UnicodeDecodeError:
            return {
                "status": "error",
                "path":   filepath,
                "error":  (
                    f"'{os.path.basename(filepath)}' contains non-UTF-8 characters "
                    "and cannot be read as plain text."
                ),
            }
        except Exception as e:
            return {"status": "error", "path": filepath, "error": str(e)}

    def write_file(self, filepath: str, content: str, backup: bool = True) -> Dict[str, Any]:
        """
        Write text content to a file with optional backup.

        Args:
            filepath: Target file path.
            content:  Text content to write.
            backup:   If True and file already exists, saves a .bak copy first.
        """
        try:
            if backup and os.path.exists(filepath):
                shutil.copy2(filepath, f"{filepath}.bak")

            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(content)

            return {
                "status":        "success",
                "path":          filepath,
                "bytes_written": len(content.encode('utf-8')),
            }
        except Exception as e:
            return {"status": "error", "path": filepath, "error": str(e)}

    def list_directory(self, path: str) -> Dict[str, Any]:
        """
        List directory contents with file metadata.

        Args:
            path: Directory path to list.
        """
        try:
            entries = []
            for item in os.listdir(path):
                full_path = os.path.join(path, item)
                try:
                    entries.append({
                        "name":         item,
                        "is_directory": os.path.isdir(full_path),
                        "size":         os.path.getsize(full_path),
                        "modified":     os.path.getmtime(full_path),
                    })
                except OSError:
                    # Skip entries we can't stat (permission errors, broken symlinks)
                    entries.append({
                        "name":         item,
                        "is_directory": False,
                        "size":         0,
                        "modified":     0,
                    })
            return {"status": "success", "path": path, "entries": entries}
        except Exception as e:
            return {"status": "error", "path": path, "error": str(e)}