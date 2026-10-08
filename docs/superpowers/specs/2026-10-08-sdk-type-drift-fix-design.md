# SDK Type Drift — Fix + Guard

**Date:** 2026-10-08
**Status:** Approved
**Trigger:** CI failure — "TypeScript SDK Smoke Tests (Node 22)": `Type drift detected — generated types don't match committed files`

## Root Cause

The SDK smoke-test workflow (`.github/workflows/sdk-smoke-tests.yml`) boots the real backend (docker-compose test services + uvicorn on :8000), fetches `/openapi.json`, regenerates `sdk/typescript/src/generated-types.ts` via `npm run generate-types`, and fails on `git diff --exit-code` against the committed file.

Commits `ba9e18f9` and `d49793fb` (§16.2.3 agent migration — `POST /api/v1/federation/agents/{agent_id}/migrate` and `POST /api/v1/federation/webhooks/agents/receive`, plus `AgentMigrateRequest` / `AgentMigrationSnapshotRequest` schemas) changed the backend OpenAPI surface, but the committed `generated-types.ts` was not regenerated. This is a recurring pattern: `e1546deb`, `0291d8c8`, and `73e53f89` are all after-the-fact "regenerate types" fix commits.

## Scope

1. **Fix** — regenerate and commit the types so CI passes now.
2. **Guard** — a local regen target plus a pre-commit hook so the next backend route change cannot silently skip regeneration.

## 1. The Fix (immediate)

Export the OpenAPI spec from the current code and regenerate `sdk/typescript/src/generated-types.ts`:

- Static export from `backend.main:app` (`app.openapi()`), no running server required — SQLAlchemy engines and redis-py clients connect lazily, so import alone is safe.
- Feed the exported spec to the existing `sdk/typescript/scripts/generate-types.ts`, which already prefers a local `openapi.json` over a live URL.
- Commit the regenerated file as `fix(sdk): regenerate types for 16.2.3 federation agent-migration endpoints`.
- Expected diff: purely additive — the two new paths, two new schemas, and two new operation IDs shown in the CI log.

## 2. The Regen Target (prevention tooling)

A one-command regeneration available on any OS:

- **`scripts/export-openapi.py`** — writes `sdk/typescript/openapi.json` from `backend.main:app`. Sets `TESTING=true` and dummy service URLs (`DATABASE_URL`, `REDIS_URL`, …) before importing the app, mirroring the env vars CI uses. Writes the spec with sorted/stable serialization.
- **`scripts/regen-sdk-types.sh` / `scripts/regen-sdk-types.ps1`** — export spec → `npm run generate-types` in `sdk/typescript` → remove the temp `openapi.json` (it stays untracked; add to `sdk/typescript/.gitignore` if not already ignored).
- **Makefile target `regen-sdk-types`** — calls the right wrapper for the current OS (repo already ships both `.sh` and `.ps1` variants of its scripts, e.g. `scripts/detect-host.*`).
- **Failure mode:** if the static import fails (missing env var, import-time side effect), the wrapper prints a clear message ("start the test stack via docker-compose.test.yml, then re-run") instead of failing mysteriously. CI is unaffected.

## 3. The Pre-Commit Guard

A `repo: local` hook added to `.pre-commit-config.yaml` (which currently runs only detect-secrets):

- A small script that inspects **staged files**: if any staged file matches the backend API-surface filter **and** `sdk/typescript/src/generated-types.ts` is not staged, the hook fails.
- **API-surface filter** (kept deliberately narrow to minimize false positives): staged files under `backend/api/` (routers), `backend/models/` (pydantic request/response definitions), and `backend/main.py` (router registration). `backend/services/`, `backend/core/`, `backend/tests/`, and non-backend changes do not match.
- **Failure message is actionable:** "Backend API surface changed but sdk/typescript/src/generated-types.ts didn't — run `make regen-sdk-types` and stage the result, or stage the generated-types change."
- Fast by construction: pure filename matching against the staged file list — no Python import, no server, no type generation.
- Runs only on commits that touch the filter, so ordinary commits are unaffected.

## 4. CI — Unchanged

The existing drift gate in `sdk-smoke-tests.yml` stays exactly as is. It remains the authoritative byte-exact check; the local hook is a fast-path guard, not a replacement, since only CI regenerates against the real running app.

## 5. Testing / Validation

- **Fix:** after regenerating locally, `git diff sdk/typescript/src/generated-types.ts` shows only the additive 16.2.3 changes; `npm test` in `sdk/typescript` passes.
- **Guard — positive case:** stage a change to a file matching the API-surface filter without touching generated types → the hook fails with the regen message.
- **Guard — negative case:** stage a change to an unrelated file (service, test, frontend) → the hook passes silently.
- **End-to-end:** push the fix commit and confirm the "TypeScript SDK Smoke Tests (Node 22)" job goes green.

## Out of Scope

- Any change to the CI workflow (auto-commit bots, restructured generation flow) — explicitly excluded.
- Regenerating the openapi.json spec as a committed artifact (spec is exported on demand).
- TypeScript SDK hand-written code changes beyond the regenerated file.
