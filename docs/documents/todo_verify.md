# Agentium — Verification & Improvement Backlog

**File:** `docs/documents/todo_verify.md`
**Purpose:** A surface-level backlog of *candidate* issues to verify, improve, or fix one-by-one. Items are **not confirmed bugs** — they are things to look into, in the order listed. Each entry has a priority tag:

- **[P1]** Likely real defect / user-reported / blocks correctness or a claimed feature
- **[P2]** Should verify; probable improvement or consistency gap
- **[P3]** Nice-to-have polish / preventative maintenance

---

## 0. Observation and Checks:

- [x] Voice bridge disconnected notification with the command should only show once after login but if shows quite often.

- [x] Improve scripts for voice bridge, in windows it is not working.
the step should be voice-bridge contaner runs installs scripts in the host system and then voice bridge will run. 

- [ ]  Chat message send no reply head of council is getting disconnected see logs. 

- [ ] Does the Voice Bridge communication form the desktop requires login from the frontend or not

- [ ] The communication with the voice using voice bridge appears in the chat or not . it should appear in the chat also. 

- [ ] Chat message in the chatscreen should be optimized, older chat example more then 7 days should be removed, the chat should keep last few messages even if it is old if no communication has been done in chat. 

- [ ] Users should be able to upload their profile picture.

- [ ] Actual genisis as per todo naming the country is not running after adding api key .

- [ ] Agent page : list shows 3 agents but graph shows only one. 


## 1. Roadmap Consistency & Incomplete Items

Items marked `[ ]` in `docs/documents/todo.md` while their parent phase is marked ✅ — verify each is actually done or close it out.

- [ ] **[P1]** Phase 6: "Real-time MCP tool usage stats; revoked tools unavailable < 1 second" is unchecked though 15.2 claims done — confirm sub-second revocation path is real (`backend/services/.../mcp*` + Redis `agentium:mcp:revoked`).
- [ ] **[P1]** Phase 7: "Drag-and-drop agent reassignment" unchecked though 18.2 claims `AgentTree.tsx` uses `react-dnd` — confirm it works.
- [ ] **[P1]** Phase 9 hardening items unchecked (query optimization/slow-query logging, connection-pool tuning, Git config backups, privilege-escalation audit trail, DDoS app-layer) though later phases claim them done — verify each.
- [ ] **[P2]** Phase 13 success criteria (all 8 acceptance items, `todo.md` L553–560) remain unchecked — run the staged verifications or mark them with evidence.
- [ ] **[P2]** Meta rows "Summery_todo.md Not Done" / "Final Checklist todo.md Not Done" (`todo.md` L42–43) — create or close these docs.
- [ ] **[P2]** Progress-overview table shows ✅ for phases (9, 13, …) that still contain unchecked `[ ]` sub-items — audit table-vs-checkbox consistency across the whole roadmap.

## 2. Voice Bridge

- [x] **[P1]** Voice bridge does not work well on Windows — verified cross-platform: `voice-bridge/main.py` + `audio_source.py` use only PyAudio + `logging.StreamHandler` (no `signal`/`fcntl`/`fork`/`termios`). Installer fixed: premature `voice-installed.marker` removed, single guarded Startup launcher + Desktop shortcut, marker now created only on successful host install.
- [x] **[P1]** Duplicate voice notifications — `frontend/src/services/voiceBridge.ts` (L82) re-fires a `showToast.error` on every reconnect attempt (`MAX_RETRIES=5`); add a dedup/seen-guard so the user sees it once.
- [ ] **[P1]** `frontend/src/components/VoiceIndicator.tsx` (L224–237) re-shows the install/error card on every `error↔offline` status flip with no dedupe — add a seen-guard.
- [x] **[P2]** Windows auto-install/startup (`scripts/install-voice-bridge.ps1`, `setup.ps1`, `windows-bootstrap.cmd`, Task Scheduler / `.vbs` / Startup folder) — consolidated to a single guarded Startup launcher (`agentium-voice-startup.cmd`) + one Desktop shortcut; legacy `.vbs`/HTA/`.reg`/duplicate `.cmd` triggers removed; `install-voice-bridge.ps1` cleans legacy artifacts so there is no double-start.
- [x] **[P2]** `docker-compose.yml` `voice-autoinstall` relies on `${USERPROFILE}` inside the Linux container + host path resolution via `windows-bootstrap.cmd` — verified reliable on Docker Desktop: container drops `bootstrap-voice.cmd` (with baked repo root) + Startup launcher + Desktop shortcut into the `/host_home` mount; `make uninstall-voice`/`voice-reinstall` are now Docker-Desktop/WSL aware.

## 3. Frontend Polish & Accessibility

- [ ] **[P2]** Leftover `console.log(...)` debug artifacts in `frontend/src/pages/DeveloperPortalPage.tsx` (L80–100) — remove per cleanup rule.
- [ ] **[P3]** `VoiceIndicator.tsx` (L140,166,186) copy/close buttons use `text-gray-600 hover:text-gray-600` with no visual hover change — fix copy-paste styling.
- [ ] **[P2]** Audit Phase 13–15 pages (`WorkflowDesigner`, `ScalingDashboard`, `EventTriggerManager`, `LearningImpactDashboard`) for hardcoded `bg-white` / `text-black` / hex without `dark:` variants (Phase 17.2 claimed done).
- [ ] **[P2]** Verify all toasts go through shared `useToast()` and all fetches through `services/api.ts` (Phase 17.2 / 18.3 claimed consolidated) — grep for stray inline `toast()`/`fetch`.
- [ ] **[P2]** Color-contrast a11y still needs a live-backend audit (per 17.4 note) — confirm `axe-core` gate covers all pages with a running backend.

## 4. Backend Correctness

- [ ] **[P1]** `backend/services/agent_orchestrator.py` (L500–501) `raise NotImplementedError("This tool was auto-generated...")` — verify it surfaces as a clean task failure (not a 500) and the message is actionable.
- [ ] **[P2]** `backend/core/constitutional_guard.py` (L172) `TODO(pre-cutover): re-tune against the REAL constitution articles` — confirm thresholds were actually re-tuned post-cutover.
- [ ] **[P2]** `backend/models/entities/agents.py` (L717–762) parses `TODO:` as a rule-action token — verify legitimate agent text containing "TODO:" cannot be misfired as an action.
- [ ] **[P2]** `backend/api/routes/chat.py` (L432) `FIX: A _done_sent flag prevents...` marks a previously-fixed duplicate final-message emit — verify no remaining double-emission path.
- [ ] **[P2]** `backend/api/routes/websocket.py` (L463 area) had an un-awaited `redis.asyncio .get()` coroutine bug fixed in 19.4 — grep `api/routes` and `core` for other un-awaited coroutines.

## 5. Testing & CI

- [ ] **[P2]** Confirm integration suite hits ≥80% `backend/services` coverage with zero skips; verify `docker-compose.test.yml` is truly ephemeral.
- [ ] **[P2]** Wire SDK smoke tests (`sdk/python/tests/test_sdk.py`, `sdk/typescript/tests/client.test.ts`) into a CI job and confirm they pass.
- [ ] **[P3]** Confirm the a11y CI gate (`frontend-a11y.yml`) runs on every relevant PR.

## 6. SDK (Python / TypeScript)

- [ ] **[P2]** `sdk/python/pyproject.toml` — verify `pip install` works and the README's `pip install agentium-sdk` matches the actual package name; run `pytest`.
- [ ] **[P2]** `sdk/typescript/package.json` (`build: tsc`, `test: jest`) — verify `tsc` emits `dist/` and `generate-types` (ts-node) runs against current `/docs` OpenAPI.
- [ ] **[P2]** `sdk/typescript/scripts/generate-types.ts` — verify generated types stay in sync with the 80+ backend endpoints after schema changes.

## 7. DevOps / Windows Compatibility

- [ ] **[P2]** `docker-compose.yml` HF_HOME named volume (Phase 20, embedding model cache) — verify it exists so Windows doesn't re-download the ~440MB model per container.
- [ ] **[P2]** Verify all bind mounts (`./...:/...`, `${HOME}`, `${USERPROFILE}`) and named volumes use Windows-compatible path conventions under Docker Desktop.
- [ ] **[P2]** `scripts/detect-host.sh` / `detect-host.ps1` — verify the Windows branch correctly detects Docker Desktop and mounts `${USERPROFILE}` writable.

## 8. AI-Agent Production-Readiness Verification (mapped)

Mapped from Galileo 8-point + Harness 25-point checklists; verify against Agentium's actual surfaces.

- [ ] **[P2] Functional correctness** — agent completes representative tasks; tool-call parameter validity; multi-step context retention; output-format/schema compliance; graceful fallback when unsure.
- [ ] **[P1] Safety & constraints** — constitutional guard tuning (see 4.2); prompt-injection resistance on user-provided docs; no PII leakage across user sessions / privilege levels; scope containment.
- [ ] **[P2] Cost & resource controls** — token-budget enforcement (13.3 `DAILY_TOKEN_BUDGET_USD`); loop/runaway-tool-call detection; cost-per-query within model; rate-limit backoff on provider errors.
- [ ] **[P2] Observability** — every agent step emits structured logs (timestamp, request_id, step, duration, tokens, status); errors carry enough context; metrics + trace correlation by request_id.
- [ ] **[P2] Production readiness** — graceful degradation when LLM/DB/search fails (13.2); load handling at 2× peak; rollback to prior version < 5 min (config Git versioning 16.4, `POST /admin/rollback`); documented incident-response runbook.

## 9. Log Verification

- [ ] **[P2]** Verify structured logging fields are present and consistent across all agent steps and Celery tasks (not just ad-hoc strings).
- [ ] **[P2]** Verify `AuditLog` entries are complete and immutable for security-relevant actions (privilege escalations, MCP invocations, auto-remediations).
- [ ] **[P2]** Verify slow-query log parsing (`backend` Celery task → `AuditLog`) actually populates `GET /admin/slow-queries`.
- [ ] **[P2]** Verify frontend caught errors reach `POST /frontend/errors` and show in `MonitoringPage.tsx` (Phase 14.3).
- [x] **[P3]** Verify voice-bridge emits useful logs on Windows failures (install, mic capture, STT/TTS) for diagnosability — install steps write to `%USERPROFILE%\.agentium\install.log`; `setup.ps1` verifies port 9999 and tails `voice-bridge.log` on failure; bridge logs to stdout/file via launcher redirection.

## 10. Dependency Updates (deprecated packages)

- [ ] **[P2]** Scan `backend/requirements*.txt` for EOL / deprecated / known-vulnerable packages; update with pinned versions and re-run tests.
- [ ] **[P2]** Scan `sdk/python/pyproject.toml` similarly; confirm build + `pytest` still green.
- [ ] **[P2]** Scan `frontend/package.json` + lockfile for deprecated/abandoned deps (e.g. unmaintained animation/util libs); update and re-run `npm run build` + a11y gate.
- [ ] **[P3]** Check `docker-compose.yml` base images for newer security patches; bump and re-test.

---

## Suggested Verification Order

1. **P1 roadmap gaps** (§1) — fastest way to confirm claimed features actually work.
2. **Voice Bridge** (§2) — user-reported, Windows-breaking.
3. **Backend correctness** (§4) + **Safety** (§8) — correctness & security first.
4. **Logs** (§9) + **Testing/CI** (§5) — prove you can see and verify behavior.
5. **Frontend polish** (§3), **SDK** (§6), **DevOps/Windows** (§7).
6. **Dependencies** (§10) + remaining **production-readiness** (§8) — maintenance & hardening last.

Work top-down; each item becomes its own dive (verify → reproduce → fix → re-verify).
