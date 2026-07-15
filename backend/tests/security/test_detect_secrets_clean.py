"""Guard: the committed tree contains no secrets outside .secrets.baseline.

Mirrors the CI `detect-secrets scan` step so developers get the same failure
locally instead of only in GitHub Actions.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
BASELINE = REPO_ROOT / ".secrets.baseline"


def test_detect_secrets_finds_no_new_secrets():
    assert BASELINE.exists(), (
        ".secrets.baseline missing — run `detect-secrets scan` to (re)create it."
    )
    result = subprocess.run(
        ["detect-secrets", "scan", "--baseline", str(BASELINE), "--all-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "detect-secrets reported NEW secrets not in .secrets.baseline:\n"
        + result.stdout
        + result.stderr
    )
