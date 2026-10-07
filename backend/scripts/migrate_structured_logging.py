#!/usr/bin/env python3
"""
Bulk migration script: standard logging -> StructuredLogger
Usage: python migrate_structured_logging.py --dry-run
       python migrate_structured_logging.py --apply
"""
import re
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).parent.parent / "services"

PATTERN_IMPORT_LOGGING = re.compile(r"^import logging\s*$", re.MULTILINE)
PATTERN_GETLOGGER = re.compile(r"^logger\s*=\s*logging\.getLogger\(__name__\)\s*$", re.MULTILINE)

REPLACEMENT = '''from backend.services.structured_logging import get_structured_logger
logger = get_structured_logger(__name__)'''

def migrate_file(filepath: Path, dry_run: bool = True) -> bool:
    content = filepath.read_text(encoding="utf-8")

    # Check if already migrated
    if "get_structured_logger" in content:
        print(f"  SKIP (already migrated): {filepath.relative_to(SERVICE_DIR.parent)}")
        return False

    # Check for standard pattern
    if not (PATTERN_IMPORT_LOGGING.search(content) and PATTERN_GETLOGGER.search(content)):
        print(f"  SKIP (non-standard pattern): {filepath.relative_to(SERVICE_DIR.parent)}")
        return False

    # Perform replacement
    new_content = PATTERN_IMPORT_LOGGING.sub("", content)
    new_content = PATTERN_GETLOGGER.sub(REPLACEMENT, new_content)

    # Clean up any double blank lines
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)

    if dry_run:
        print(f"  WOULD MIGRATE: {filepath.relative_to(SERVICE_DIR.parent)}")
    else:
        filepath.write_text(new_content, encoding="utf-8")
        print(f"  MIGRATED: {filepath.relative_to(SERVICE_DIR.parent)}")
    return True

def main():
    dry_run = "--dry-run" in sys.argv
    apply = "--apply" in sys.argv

    if not (dry_run or apply):
        print("Usage: python migrate_structured_logging.py --dry-run|--apply")
        sys.exit(1)

    files = list(SERVICE_DIR.rglob("*.py"))
    print(f"Scanning {len(files)} Python files in {SERVICE_DIR}...")

    migrated = 0
    for f in files:
        if f.name == "structured_logging.py":
            continue  # skip self
        if migrate_file(f, dry_run=dry_run):
            migrated += 1

    print(f"\n{'Would migrate' if dry_run else 'Migrated'} {migrated} files")

if __name__ == "__main__":
    main()