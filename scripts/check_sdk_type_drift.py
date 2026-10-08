"""Pre-commit guard: fail when the backend API surface changes without the
SDK's generated types in the same commit.

Pure filename matching against the staged file list — no backend import, no
server, no type generation (by design; see the 2026-10-08-sdk-type-drift-fix
design doc). CI's drift gate in sdk-smoke-tests.yml remains the authoritative
byte-exact check; this hook only catches the "forgot to regenerate" pattern
before it reaches CI.
"""

import subprocess
import sys

API_SURFACE_PREFIXES = ("backend/api/", "backend/models/")
API_SURFACE_FILES = ("backend/main.py",)
GENERATED_TYPES = "sdk/typescript/src/generated-types.ts"

FAIL_MESSAGE = """\
Backend API surface changed but sdk/typescript/src/generated-types.ts didn't.

Run 'make regen-sdk-types' and stage the result, or stage the generated-types
change together with the backend change in this commit.
"""


def staged_files():
    """Names of files staged for this commit."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def is_api_surface(filename: str) -> bool:
    return filename.startswith(API_SURFACE_PREFIXES) or filename in API_SURFACE_FILES


def main() -> None:
    files = staged_files()
    if not any(is_api_surface(f) for f in files):
        sys.exit(0)
    if GENERATED_TYPES in files:
        sys.exit(0)
    print(FAIL_MESSAGE)
    sys.exit(1)


if __name__ == "__main__":
    main()
