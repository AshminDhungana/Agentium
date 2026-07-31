# Agentium — Verification & Improvement Backlog


## 18. Testing & CI

- **18.1 — [P2]** Confirm the integration suite hits ≥80% coverage on `backend/services` with zero skipped tests; confirm `docker-compose.test.yml` is truly ephemeral (no state leaks between runs).
- **18.2 — [P2]** Wire SDK smoke tests (`sdk/python/tests/test_sdk.py`, `sdk/typescript/tests/client.test.ts`) into a CI job and confirm they pass.
- **18.3 — [P3]** Confirm the a11y CI gate (`frontend-a11y.yml`) actually runs on every relevant PR (not just main-branch pushes).

---

## 19. SDKs (Python / TypeScript)

- **19.1 — [P2]** `sdk/python/pyproject.toml` — verify `pip install .` works locally and that the README's documented `pip install agentium-sdk` matches the real published package name; run `pytest`.
- **19.2 — [P2]** `sdk/typescript/package.json` (`build: tsc`, `test: jest`) — verify `tsc` emits a correct `dist/`, and that `generate-types` (ts-node) runs cleanly against the current `/docs` OpenAPI spec.
- **19.3 — [P2]** `sdk/typescript/scripts/generate-types.ts` — verify generated types stay in sync with all 80+ backend endpoints after schema changes; consider adding a CI check that fails on drift.

---

## 20. DevOps / Windows Compatibility

- **20.1 — [P2]** Confirm the `HF_HOME` named volume in `docker-compose.yml` (Phase 20, embedding-model cache) exists and is actually used, so Windows doesn't re-download the ~440 MB embedding model on every container recreate.
- **20.2 — [P2]** Verify all bind mounts (`./...:/...`, `${HOME}`, `${USERPROFILE}`) and named volumes use Windows-compatible path conventions under Docker Desktop.
- **20.3 — [P2]** `scripts/detect-host.sh` / `detect-host.ps1` — verify the Windows branch correctly detects Docker Desktop and mounts `${USERPROFILE}` writable.

---

## 21. Production-Readiness Checklist

Mapped from common agent production-readiness frameworks (functional correctness, safety, cost, observability, resilience); verify each against Agentium's actual surfaces rather than assuming the roadmap claims hold.

- **21.1 — [P2] Functional correctness** — agent completes representative tasks end-to-end; tool-call parameters are valid against schema; multi-step context is retained across a task's lifetime; output format/schema compliance is enforced; agent falls back gracefully when uncertain rather than hallucinating a result.
- **21.2 — [P0] Safety & constraints** — constitutional guard tuning (see 17.2); resistance to prompt injection from user-provided documents; no PII leakage across user sessions or privilege levels; tool/action scope stays within the calling agent's tier.
- **21.3 — [P2] Cost & resource controls** — token-budget enforcement (`DAILY_TOKEN_BUDGET_USD` per Phase 13.3); detection of runaway/looping tool calls; cost-per-query stays within the selected model's expected range; rate-limit backoff on provider errors.
- **21.4 — [P2] Observability** — every agent step emits structured logs (timestamp, request_id, step, duration, tokens, status); errors carry enough context to debug without reproducing; metrics and traces correlate by `request_id`.
- **21.5 — [P2] Production readiness** — graceful degradation when the LLM, DB, or search provider fails (Phase 13.2); load-tested at 2× expected peak; rollback to a prior version completes in under 5 minutes (config Git versioning per Phase 16.4, `POST /admin/rollback`); an incident-response runbook exists and is current.

---

## 22. Log & Audit Verification

- **22.1 — [P2]** Verify structured logging fields are present and consistent across all agent steps and Celery tasks — not just ad-hoc string logs in some code paths and structured logs in others.
- **22.2 — [P1]** Verify `AuditLog` entries are complete and immutable for every security-relevant action (privilege escalations, MCP tool invocations, auto-remediations) — this underpins the platform's core "auditable democracy" claim, so treat gaps here as high priority.
- **22.3 — [P2]** Verify slow-query log parsing (the Celery task that writes to `AuditLog`) actually populates `GET /admin/slow-queries` with real data, not an empty/stale response.
- **22.4 — [P2]** Verify frontend-caught errors actually reach `POST /frontend/errors` and surface in `MonitoringPage.tsx` (Phase 14.3 claim).

---

## 23. Dependency Updates

- **23.1 — [P2]** Scan `backend/requirements*.txt` for EOL, deprecated, or known-vulnerable packages (e.g. via `pip-audit` or `safety`); update with pinned versions and re-run the full test suite.
- **23.2 — [P2]** Scan `sdk/python/pyproject.toml` the same way; confirm build + `pytest` remain green after updates.
- **23.3 — [P2]** Scan `frontend/package.json` + lockfile for deprecated/abandoned dependencies (e.g. unmaintained animation/utility libs); update and re-run `npm run build` + the a11y CI gate.
- **23.4 — [P3]** Check `docker-compose.yml` base images for newer security patches; bump and re-test the full stack.
