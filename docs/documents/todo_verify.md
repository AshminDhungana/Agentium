# Agentium — Verification & Improvement Backlog


---

## 14. Roadmap Consistency Audit

Items marked `[ ]` (incomplete) in `docs/documents/todo.md` while their parent phase is marked ✅ — verify each is actually done, or unmark the phase.


- **14.2 — [x][P1] Done — Phase 7: "Drag-and-drop agent reassignment" verified end-to-end.** The original note incorrectly referenced "18.2" — Phase 18.2 is about SDK smoke tests, not `react-dnd`. `AgentTree.tsx` uses **native HTML5 Drag-and-Drop API** (not `react-dnd`), confirmed by reading the component's `onDragStart`, `onDragEnd`, `onDragEnter`, `onDragLeave`, `onDrop` handlers and the `DragDropContext` provider. Frontend unit tests for `AgentTree` (6 tests) and `DragDropContext` (12 tests) all pass. Backend reassignment API verified via integration tests.

- **14.3 — [P1]** Phase 9 hardening items unchecked (query optimization/slow-query logging, connection-pool tuning, Git config backups, privilege-escalation audit trail, app-layer DDoS) though later phases claim them done — verify each individually.
- **14.4 — [P2]** Phase 13 success criteria (all 8 acceptance items, `todo.md` L553–560) remain unchecked — run the staged verifications or mark them with evidence.
- **14.5 — [P2]** Meta rows "Summery_todo.md Not Done" / "Final Checklist todo.md Not Done" (`todo.md` L42–43) — create the missing docs or close the rows out.
- **14.6 — [P2]** Progress-overview table shows ✅ for phases (9, 13, …) that still contain unchecked `[ ]` sub-items — audit table-vs-checkbox consistency across the entire roadmap and reconcile.

---

## 15. Voice Bridge

> See `voice-bridge-setup.md` for the full host-side install/config reference.

- **15.1 — [x][P1] Done — Cross-platform Windows compatibility.** `voice-bridge/main.py` + `audio_source.py` verified to use only PyAudio + `logging.StreamHandler` (no `signal`/`fcntl`/`fork`/`termios` — none of which exist on Windows). Installer bug fixed: premature `voice-installed.marker` write removed; consolidated to a single guarded Startup launcher + Desktop shortcut; marker is now only written once the bridge is confirmed listening on port 9999 (see "How it works" in `voice-bridge-setup.md`).
- **15.2 — [x][P1] Done — Duplicate voice notifications.** `frontend/src/services/voiceBridge.ts` (~L82) was re-firing `showToast.error` on every reconnect attempt (`MAX_RETRIES=5`); a dedup/seen-guard was added so the user sees the error once per incident.
- **15.3 — [P1] `VoiceIndicator.tsx` still re-shows the install/error card on every status flip.** `frontend/src/components/VoiceIndicator.tsx` (~L224–237) re-renders the install/error card on every `error ↔ offline` transition with no dedupe, distinct from the toast fixed in 15.2. Add the same seen-guard pattern here.
- **15.4 — [x][P2] Done — Windows auto-install/startup consolidation.** `scripts/install-voice-bridge.ps1`, `setup.ps1`, `windows-bootstrap.cmd`, Task Scheduler / `.vbs` / Startup folder triggers consolidated into a single guarded Startup launcher (`agentium-voice-startup.cmd`) + one Desktop shortcut; legacy `.vbs`/HTA/`.reg`/duplicate `.cmd` triggers removed; `install-voice-bridge.ps1` cleans up legacy artifacts so there's no double-start.
- **15.5 — [x][P2] Done — `docker-compose.yml` `voice-autoinstall` Windows path handling.** Verified reliable on Docker Desktop: the container drops `bootstrap-voice.cmd` (with the repo root baked in) + Startup launcher + Desktop shortcut into the `${USERPROFILE}`-mounted `/host_home` path; `make uninstall-voice` / `make voice-reinstall` are now Docker-Desktop/WSL2 aware.
- **15.6 — [x][P3] Done — Diagnosable Windows failure logs.** Install steps write to `%USERPROFILE%\.agentium\install.log`; `setup.ps1` verifies port 9999 post-install and tails `voice-bridge.log` on failure; the bridge itself logs to stdout/file via launcher redirection.

---

## 16. Frontend Polish & Accessibility

- **16.1 — [P2]** Remove leftover `console.log(...)` debug statements in `frontend/src/pages/DeveloperPortalPage.tsx` (~L80–100) per the project's cleanup convention.
- **16.2 — [P3]** `VoiceIndicator.tsx` (L140, 166, 186) copy/close buttons use `text-gray-600 hover:text-gray-600` — the hover state is a no-op due to copy-paste styling. Give hover a distinct color.
- **16.3 — [P2]** Audit Phase 13–15 pages (`WorkflowDesigner`, `ScalingDashboard`, `EventTriggerManager`, `LearningImpactDashboard`) for hardcoded `bg-white` / `text-black` / raw hex colors missing `dark:` variants, even though Phase 17.2 claims this was completed project-wide.
- **16.4 — [P2]** Verify every toast goes through the shared `useToast()` hook and every network call goes through `services/api.ts` (Phase 17.2/18.3 claimed this was consolidated) — grep for stray inline `toast()` / `fetch()` calls and migrate any found.
- **16.5 — [P2]** Color-contrast accessibility still needs a live-backend audit per the Phase 17.4 note — confirm the `axe-core` CI gate actually covers every page with a running backend (not just static/mocked pages).

---

## 17. Backend Correctness

- **17.1 — [P1]** `backend/services/agent_orchestrator.py` (~L500–501): `raise NotImplementedError("This tool was auto-generated...")` — verify this surfaces to the user as a clean, actionable task-failure message rather than a raw 500.
- **17.2 — [P2]** `backend/core/constitutional_guard.py` (~L172): `TODO(pre-cutover): re-tune against the REAL constitution articles` — confirm thresholds were actually re-tuned after cutover; if not, do it now.
- **17.3 — [P2]** `backend/models/entities/agents.py` (~L717–762) parses `TODO:` as a rule-action token — verify legitimate agent-authored text that happens to contain the literal string "TODO:" cannot be misinterpreted as a rule action. Add an escaping/quoting mechanism if it can.
- **17.4 — [P2]** `backend/api/routes/chat.py` (~L432): a `_done_sent` flag was added to prevent a previously-fixed duplicate final-message emission — verify no other code path can still double-emit the final message.
- **17.5 — [P2]** `backend/api/routes/websocket.py` (~L463 area) had an un-awaited `redis.asyncio.get()` coroutine bug, fixed in Phase 19.4 — grep the rest of `api/routes/` and `core/` for other unawaited coroutines (this class of bug already occurred twice — see 1.3 above).

---

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
