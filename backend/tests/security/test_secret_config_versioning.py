"""Regression guard: secret config files must never be version-controlled in Git.

Verifies (and perpetually guards) the claim in
docs/documents/todo.md -> "19.0 Known Issues & Technical Debt ->
Config files not version-controlled via Git".

Intentionally-tracked, non-secret env/config files are enumerated in
ALLOWED_TRACKED_ENV_FILES. Every other file matching SECRET_CONFIG_PATTERNS
(.env, private keys, ...) must be git-ignored, never committed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]  # backend/tests/security -> repo root

# Safe, non-secret files that are intentionally committed to Git.
ALLOWED_TRACKED_ENV_FILES = {
    "backend/.env.example",    # template, no real secrets
    "frontend/.env",           # only VITE_API_BASE_URL= (public, Vite-exposed)
    ".pinned-digests.env",     # image digest pins, not secret
}

# Glob patterns whose matches must NEVER be tracked by Git.
SECRET_CONFIG_PATTERNS = [
    "*.env", "*.pem", "*.key", "*.p12", "*.pfx", "*.id_rsa",
]


def _git_ls_files() -> set[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return {line for line in result.stdout.splitlines() if line}


def _git_check_ignore(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", path],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def test_no_secret_env_files_are_tracked():
    tracked = _git_ls_files()
    violations = []
    for pattern in SECRET_CONFIG_PATTERNS:
        for tracked_file in tracked:
            if Path(tracked_file).match(pattern) and tracked_file not in ALLOWED_TRACKED_ENV_FILES:
                violations.append(tracked_file)
    assert not violations, (
        "Secret config file(s) are tracked by Git (must be git-ignored): "
        + ", ".join(violations)
    )


def test_backend_env_is_gitignored():
    # backend/.env holds real secrets; .gitignore must exclude it even when
    # the file is absent from the working tree.
    assert _git_check_ignore("backend/.env"), (
        "backend/.env is NOT covered by .gitignore — real secrets could be committed."
    )
