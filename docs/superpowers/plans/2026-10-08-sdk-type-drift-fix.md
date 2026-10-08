# SDK Type-Drift Fix + Guard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the failing "TypeScript SDK Smoke Tests (Node 22)" CI job green by regenerating `sdk/typescript/src/generated-types.ts` for the §16.2.3 federation agent-migration endpoints, and prevent recurrence with a one-command regen target plus a pre-commit guard.

**Architecture:** The CI drift gate regenerates types from the live backend's `/openapi.json` and diffs against the committed file. The fix regenerates locally from a **static** export of the FastAPI app's spec (no docker stack needed — SQLAlchemy/redis-py clients connect lazily, so importing `backend.main:app` is safe). The guard is a pure filename-matching pre-commit hook that fails when `backend/api/`, `backend/models/`, or `backend/main.py` change without `sdk/typescript/src/generated-types.ts` in the same commit. CI stays unchanged as the authoritative byte-exact check.

**Tech Stack:** Python 3.12 + FastAPI (`app.openapi()`), Node 22 + `openapi-typescript` v7 via existing `npm run generate-types`, pre-commit framework (repo already uses it), Make + PowerShell/bash wrappers.

## Global Constraints

- CI workflow `.github/workflows/sdk-smoke-tests.yml` must NOT be modified (spec §4).
- The regenerated `sdk/typescript/src/generated-types.ts` must be byte-identical to what CI regenerates — only the additive §16.2.3 changes seen in the CI log may appear in the diff (spec §1).
- The pre-commit guard must be pure filename matching — no Python import of the backend, no server, no type generation (spec §3).
- API-surface filter is exactly: files under `backend/api/`, files under `backend/models/`, and `backend/main.py` (spec §3).
- Failure mode of the regen target is a clear instruction, never a mystery error (spec §2).
- `sdk/typescript/openapi.json` is already gitignored (`**/openapi.json` in `sdk/typescript/.gitignore:11`) — never commit it.

## File Structure

| File | Responsibility |
|---|---|
| Create: `scripts/export_openapi.py` | Static OpenAPI spec export from `backend.main:app` → `sdk/typescript/openapi.json` |
| Create: `scripts/regen-sdk-types.sh` | POSIX wrapper: export → `npm run generate-types` → cleanup |
| Create: `scripts/regen-sdk-types.ps1` | Windows PowerShell equivalent |
| Modify: `Makefile` | Add `regen-sdk-types` target (OS-dispatching, follows existing pattern) |
| Create: `scripts/check_sdk_type_drift.py` | Pre-commit guard: staged-filename matching |
| Create: `backend/tests/test_sdk_type_drift_guard.py` | Unit tests for the guard's matching logic |
| Modify: `.pre-commit-config.yaml` | Add `repo: local` hook running the guard |
| Modify: `sdk/typescript/src/generated-types.ts` | Regenerated (by Task 3's `make regen-sdk-types`, never hand-edited) |

---

### Task 1: Static OpenAPI Export Script

**Files:**
- Create: `scripts/export_openapi.py`

**Interfaces:**
- Produces: `sdk/typescript/openapi.json` (gitignored) — the OpenAPI spec of `backend.main:app`. Task 2's wrappers invoke this script with `python scripts/export_openapi.py` from the repo root.

- [ ] **Step 1: Write the export script**

```python
# scripts/export_openapi.py
"""Export the backend's OpenAPI spec without running a server.

Imports backend.main:app and dumps app.openapi() to sdk/typescript/openapi.json.
Safe to run without docker services: SQLAlchemy engines and redis-py clients
connect lazily, so importing the app does not touch the network.

Usage (from repo root):
    python scripts/export_openapi.py
"""

import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

# Mirror the env vars CI sets for the backend (sdk-smoke-tests.yml) so import
# never fails on a missing setting. setdefault: real values win if present.
os.environ.setdefault("TESTING", "true")
os.environ.setdefault("DATABASE_URL", "postgresql://agentium:agentium@localhost:5432/agentium_test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")


def main() -> None:
    from backend.main import app

    spec = app.openapi()
    out_path = REPO_ROOT / "sdk" / "typescript" / "openapi.json"
    out_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run it and verify the §16.2.3 routes are present**

Run: `python scripts/export_openapi.py`
Expected output: `Wrote E:\...\sdk\typescript\openapi.json` (path per repo root)

Run: `grep -c "migrate_agent_api_v1_federation_agents__agent_id__migrate_post\|receive_migrated_agent_api_v1_federation_webhooks_agents_receive_post" sdk/typescript/openapi.json`
Expected: `2` (both §16.2.3 operation IDs present in the spec)

If the import fails on a missing dependency, install backend deps first (`pip install -r backend/requirements.txt`) and re-run — the script itself has no third-party deps beyond what `backend.main` imports.

- [ ] **Step 3: Commit**

```bash
git add scripts/export_openapi.py
git commit -m "feat(scripts): static OpenAPI export from backend.main:app"
```

---

### Task 2: Regen Wrappers + Makefile Target

**Files:**
- Create: `scripts/regen-sdk-types.sh`
- Create: `scripts/regen-sdk-types.ps1`
- Modify: `Makefile` (add target after the existing `pin-digests`-style utility targets, and extend the `.PHONY` line)

**Interfaces:**
- Consumes: `python scripts/export_openapi.py` (Task 1) and `npm run generate-types` in `sdk/typescript` (existing; that script prefers the local `openapi.json` Task 1 produces).
- Produces: `make regen-sdk-types` — the single command the pre-commit hook (Task 4) tells committers to run.

- [ ] **Step 1: Write the bash wrapper**

```bash
# scripts/regen-sdk-types.sh
#!/usr/bin/env bash
# Regenerate sdk/typescript/src/generated-types.ts from the current backend
# code. No running services required. Usage (from repo root):
#   scripts/regen-sdk-types.sh   (or: make regen-sdk-types)
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python scripts/export_openapi.py; then
  echo ""
  echo "ERROR: static OpenAPI export failed."
  echo "If a backend dependency is missing, run: pip install -r backend/requirements.txt"
  echo "If an import-time env var is required, start the test stack:"
  echo "  docker compose -f docker-compose.test.yml up -d"
  echo "then re-run this command."
  exit 1
fi

cd sdk/typescript
npm run generate-types
cd ../..

rm -f sdk/typescript/openapi.json
echo "Done — sdk/typescript/src/generated-types.ts regenerated. Review and commit the diff."
```

- [ ] **Step 2: Write the PowerShell wrapper**

```powershell
# scripts/regen-sdk-types.ps1
# Regenerate sdk/typescript/src/generated-types.ts from the current backend
# code. No running services required. Usage (from repo root):
#   powershell -File scripts/regen-sdk-types.ps1   (or: make regen-sdk-types)
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location $repoRoot

try {
  python scripts/export_openapi.py
} catch {
  Write-Host ""
  Write-Host "ERROR: static OpenAPI export failed."
  Write-Host "If a backend dependency is missing, run: pip install -r backend/requirements.txt"
  Write-Host "If an import-time env var is required, start the test stack:"
  Write-Host "  docker compose -f docker-compose.test.yml up -d"
  Write-Host "then re-run this command."
  exit 1
}

Push-Location sdk/typescript
npm run generate-types
Pop-Location

Remove-Item -ErrorAction SilentlyContinue sdk/typescript/openapi.json
Write-Host "Done — sdk/typescript/src/generated-types.ts regenerated. Review and commit the diff."
```

- [ ] **Step 3: Add the Makefile target**

Replace the existing `.PHONY` line (`Makefile:3`) with:

```make
.PHONY: up down restart setup voice-reinstall voice-logs voice-status uninstall-voice test hallmark test-integration load-test benchmark perf-gate test-staging audit audit-fix pin-digests docker-scout seed-skills backfill-knowledge backfill-knowledge-collection regen-sdk-types
```

Add this target at the end of the Makefile, following the repo's existing Windows-detection pattern (as used by the `voice-reinstall` target):

```make
# -- Regenerate TypeScript SDK types from the current backend OpenAPI spec --
regen-sdk-types:
	@if [ -d /run/desktop/mnt/host ] || uname -s | grep -qiE "MINGW|MSYS|CYGWIN"; then \
	  powershell.exe -NoProfile -ExecutionPolicy Bypass -File scripts/regen-sdk-types.ps1; \
	else \
	  bash scripts/regen-sdk-types.sh; \
	fi
```

- [ ] **Step 4: Smoke-test the target end-to-end**

Run: `make regen-sdk-types`
Expected: export message, `✅ Generated ./src/generated-types.ts`, `Done — ... regenerated` message. Then `git status --short` shows `sdk/typescript/src/generated-types.ts` as modified (do NOT commit yet — Task 3 handles that) and `sdk/typescript/openapi.json` absent (removed by the wrapper).

- [ ] **Step 5: Commit**

```bash
git add scripts/regen-sdk-types.sh scripts/regen-sdk-types.ps1 Makefile
git commit -m "feat(scripts): make regen-sdk-types — one-command SDK type regeneration"
```

---

### Task 3: Regenerate Types and Commit the Fix (the actual CI fix)

**Files:**
- Modify: `sdk/typescript/src/generated-types.ts` (via `make regen-sdk-types` — never hand-edited)

**Interfaces:**
- Consumes: `make regen-sdk-types` (Task 2).
- Produces: a committed `generated-types.ts` byte-identical to what CI regenerates — this is what makes the failing job green (Task 5).

- [ ] **Step 1: Regenerate**

Run: `make regen-sdk-types`
Expected: same output as Task 2 Step 4. `git status --short` shows ` M sdk/typescript/src/generated-types.ts`.

- [ ] **Step 2: Verify the diff is purely additive §16.2.3 content**

Run: `git diff --stat sdk/typescript/src/generated-types.ts`
Expected: `1 file changed, insertions only` (roughly 350–400 insertions, 0 deletions — matches the CI log's hunks).

Run: `git diff sdk/typescript/src/generated-types.ts | grep "^-" | grep -v "^---"`
Expected: **empty output** (no removed lines anywhere in the diff).

Run: `git diff sdk/typescript/src/generated-types.ts | grep -c "^+.*migrate_agent_api_v1_federation_agents__agent_id__migrate_post\|^+.*receive_migrated_agent_api_v1_federation_webhooks_agents_receive_post\|^+.*AgentMigrateRequest\|^+.*AgentMigrationSnapshotRequest"`
Expected: at least `4` — both operation IDs and both schema names appear as additions.

If deletions appear, STOP: the local backend import is producing a different app state than CI (e.g., a feature-flag env var disabling routes). Do not commit; re-export with `TESTING=true` confirmed in the environment and compare the spec against a fresh checkout before proceeding.

- [ ] **Step 3: Run the SDK test suite**

Run (in `sdk/typescript`): `npm test`
Expected: all jest suites PASS (they passed on CI before the drift check, so no SDK test depends on the new types yet).

- [ ] **Step 4: Commit the fix**

```bash
git add sdk/typescript/src/generated-types.ts
git commit -m "fix(sdk): regenerate types for 16.2.3 federation agent-migration endpoints"
```

---

### Task 4: Pre-Commit Guard (TDD)

**Files:**
- Create: `scripts/check_sdk_type_drift.py`
- Test: `backend/tests/test_sdk_type_drift_guard.py`
- Modify: `.pre-commit-config.yaml` (add a `repo: local` entry after the detect-secrets block)

**Interfaces:**
- Consumes: staged filenames via `git diff --cached --name-only` (pre-commit runs hooks at commit time, so the index is what matters; `pass_filenames: false` keeps the script's argv empty by design).
- Produces: hook id `check-sdk-type-drift`; exit code 0 (ok) or 1 (fail with the `make regen-sdk-types` instruction). The constants `API_SURFACE_PREFIXES`, `API_SURFACE_FILES`, `GENERATED_TYPES` and function `main()` are imported by the test.

- [ ] **Step 1: Write the failing tests**

```python
# backend/tests/test_sdk_type_drift_guard.py
"""Unit tests for the pre-commit SDK type-drift guard (scripts/check_sdk_type_drift.py)."""

import importlib.util
import pathlib
import sys

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "scripts" / "check_sdk_type_drift.py"


def _load_guard(monkeypatch, staged):
    spec = importlib.util.spec_from_file_location("check_sdk_type_drift", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "staged_files", lambda: staged)
    return module


@pytest.mark.parametrize(
    "staged, expected_exit",
    [
        # API-surface change without generated types -> fail
        (["backend/api/federation_routes.py"], 1),
        (["backend/api/federation_routes.py", "backend/services/foo.py"], 1),
        (["backend/models/requests.py"], 1),
        (["backend/main.py"], 1),
        # API-surface change WITH generated types staged -> pass
        (["backend/api/federation_routes.py", "sdk/typescript/src/generated-types.ts"], 0),
        # Non-API-surface changes -> pass
        (["backend/services/foo.py"], 0),
        (["backend/tests/test_foo.py"], 0),
        (["frontend/src/App.tsx"], 0),
        ([], 0),
    ],
)
def test_guard_verdicts(capsys, monkeypatch, staged, expected_exit):
    module = _load_guard(monkeypatch, staged)
    with pytest.raises(SystemExit) as excinfo:
        module.main()
    assert excinfo.value.code == expected_exit
    if expected_exit == 1:
        assert "make regen-sdk-types" in capsys.readouterr().out


def test_staged_files_uses_git_index(monkeypatch):
    """The real staged_files() shells out to git, not pre-commit's argv."""
    module = _load_guard(monkeypatch, [])
    assert callable(module.staged_files)
    with monkeypatch.context() as m:
        m.setattr(module.subprocess, "run", lambda *a, **k: type("R", (), {"stdout": "a\nb\n"})())
        assert module.staged_files() == ["a", "b"]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest backend/tests/test_sdk_type_drift_guard.py -v` (from repo root)
Expected: FAIL/ERROR — `scripts/check_sdk_type_drift.py` does not exist yet (import/`spec_from_file_location` error).

- [ ] **Step 3: Write the guard script**

```python
# scripts/check_sdk_type_drift.py
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
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest backend/tests/test_sdk_type_drift_guard.py -v`
Expected: all 9 parametrized cases + the smoke test PASS.

- [ ] **Step 5: Register the hook in pre-commit**

Append to `.pre-commit-config.yaml` (after the detect-secrets `hooks:` block):

```yaml
  - repo: local
    hooks:
      - id: check-sdk-type-drift
        name: check SDK type drift
        entry: python scripts/check_sdk_type_drift.py
        language: system
        pass_filenames: false
        stages: [pre-commit]
```

- [ ] **Step 6: Verify the hook fires on the positive case**

```bash
echo "" >> backend/main.py && git add backend/main.py
pre-commit run check-sdk-type-drift
```
Expected: the hook FAILS with the "Run 'make regen-sdk-types'" message.

Then undo and verify the negative case:

```bash
git restore --staged backend/main.py && git checkout -- backend/main.py
pre-commit run check-sdk-type-drift
```
Expected: `check SDK type drift ......................................... Passed`

- [ ] **Step 7: Commit**

```bash
git add scripts/check_sdk_type_drift.py backend/tests/test_sdk_type_drift_guard.py .pre-commit-config.yaml
git commit -m "feat(guard): pre-commit hook failing on backend API changes without SDK type regeneration"
```

---

### Task 5: Push and Verify CI

**Files:** none (verification only)

**Interfaces:**
- Consumes: the Task 3 fix commit on `main`.

- [ ] **Step 1: Push**

```bash
git push origin main
```

Expected: push succeeds; the new commits are on origin/main.

- [ ] **Step 2: Watch the SDK smoke-test job**

Run: `gh run watch --workflow sdk-smoke-tests.yml` (or watch the Actions tab for the run triggered by the push)
Expected: the **TypeScript SDK Smoke Tests (Node 22)** workflow completes successfully — including the "Check for Type Drift" step that previously failed.

- [ ] **Step 3: Record completion**

If green, mark the spec `docs/superpowers/specs/2026-10-08-sdk-type-drift-fix-design.md` as implemented (change `**Status:** Approved` to `**Status:** Implemented`) and commit:

```bash
git add docs/superpowers/specs/2026-10-08-sdk-type-drift-fix-design.md
git commit -m "docs: mark SDK type-drift fix spec implemented"
git push origin main
```

---

## Self-Review Checklist (for the executing agent)

- Spec §1 (fix) → Task 3. Spec §2 (regen target) → Tasks 1–2. Spec §3 (guard) → Task 4. Spec §4 (CI unchanged) → Global Constraints. Spec §5 (validation) → Tasks 3 Steps 2–3, Task 4 Step 6, Task 5.
- The guard's failure mode must never import `backend.*` — keep it pure filename matching.
- Never hand-edit `sdk/typescript/src/generated-types.ts`; always regenerate via `make regen-sdk-types`.

