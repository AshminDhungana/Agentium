# Agentium — Verification & Improvement Backlog

**File:** `docs/documents/todo_verify.md`
**Purpose:** A surface-level backlog of *candidate* issues to verify, improve, or fix one-by-one. Items are **not confirmed bugs** — they are things to look into, in the order listed. Each entry has a priority tag:

- **[P1]** Likely real defect / user-reported / blocks correctness or a claimed feature
- **[P2]** Should verify; probable improvement or consistency gap
- **[P3]** Nice-to-have polish / preventative maintenance

---

## 🔲 In Progress / Pending

### Voice Bridge
- [ ] Determine whether voice bridge communication from the desktop app requires the user to be logged in via the frontend.
- [ ] Confirm whether voice bridge communication is currently visible in the chat; if not, implement it.
- [ ] Align the voice bridge persona with the chat persona so behavior is consistent across both (e.g., addressing the admin as "sir" is acceptable for both).
- [ ] Verify that whisper.cpp is downloaded in Docker and running correctly.

- [ ] After contry name is set, the ai should sent welcome message with the info like, welcome the country name is ... or similar. Currently the country name is set , then untill the user sends a message no message appears. 

- [ ] The dark light mode switch button is not functioning correctly. 
When clicked it takes time to switch form moon logo to sun logo. 

- [ ] Voice Bridge Not Running notification should only show once after login but it is showing repeteadly. 

- [ ] Using free model should not have pricing, the pricing details can be recived from the api itself make it so the pricing is correct. different models uses different api most use open ai api structure, anthropic uses different one. 

- [ ] In chatpage, the icone for the message form the ai, imporve the style to make it look better. 

- [ ] Start voice input when voice is sent is not showing in the chat, as well as clicking voice setting is throwing error in the frontend consel. 

- [ ] - **desktop_screen_size**: ❌ Failing — threw a SQLAlchemy rollback error (likely a backend session fault, not a desktop issue).

- [ ] - Adding tools, creating tools by itself is not implemented correctly.

- [ ] - Improvement on tools 
    **CATEGORY 3 — DESKTOP FILESYSTEM (⚠️ partial)**
    - `desktop_list_directory` ✅ — listed your Desktop
    - `desktop_screen_size` ❌ — SQLAlchemy rollback fault
    - (Other desktop_* tools — create/read/save/delete/copy/move/file ops — share the same backend as screen_size and are **at risk** of the same fault; only list_directory was confirmed healthy)

    **CATEGORY 4 — PREFERENCES (❌ broken)**
    - `preference_categories` ❌ — SQLAlchemy rollback fault
    - `preference_get`, `preference_set`, `preference_list`, `preference_bulk_update` — **all share the same DB backend and are broken** by the same fault

    **CATEGORY 5 — NOT AVAILABLE (no tools provisioned)**
    - MCP server connection tools — none exist
    - Agent spawning / task-creation tools — none exposed to my tier (I can only *direct* via governance, not instantiate programmatically)
    - Custom tool creation — not permitted

[ ] - Add task management tools for ths system. 

resolve the errors and add mcp tools

### Chat Page
- [ ] Add hover icons on chat messages: a **copy** icon (copies the message text) and a **forward** icon (copies the message into the compose box so the user can send it again).


### Model Page
 - [ ] Add a search function in the model selection section, when user presses the fetch button then a list of model appears and a small search appears at the top which will help user find the model he is looking for if their are many model. the search should filter but the text, example, if the model is openrouter/nvidia/xxx then serching for openrouter should only show the text that has openrouter. 

### AI Module Configuration
- [ ] When adding an AI module, the **rate limit** and **max tokens** fields should auto-populate from the provider's API after a model is selected (if the API exposes this data), and the same values should be reflected on the model config page. If the API doesn't provide this info, fall back to the current defaults (max tokens: 4000).

### Tools & Knowledge Base
- [ ] Review all existing tools, improve them, and add new tools where needed.

- [ ] In the ethos or startup prompt for all ai agent, after reading constitution, give them basic context, like where they are located inside docker contaner, when is the hostsystem outside docker contaner, where is the internet outside the host system, where they should operate in the host system, how to access the host system. where user says " create a folder in my desktop, the expectation is to create in the host system not inside contaner" this knowledge should be given to the agent to add in the ethos and also put inside the chroma db. 
- [ ] Seed the knowledge library with foundational operating info for the agent: which tools to use and when, general best practices, how to access the host system, basic CMD/PowerShell usage, and useful utilities (grep, curl, etc.), so the system behaves correctly from the start. Decide on the best delivery method — e.g., bake basics into the ethos/constitution, have the agent read from Chroma on startup, or seed it at creation time — and implement whichever fits best.

part 2 
- [ ] to know something or before doing something agent will, search the web and the chroma db, if knowledge not in chroma db they will update it , then proceed with the work. if web search is not avilable then uses chroma db knowledge. 
- [ ] A basic structure should exist to update knowledge in chroma db so all agents will use the same and , their is less dublicate inside chroma db . all agents should use the same.  


### Model cap during autoscaling 
 - [ ] their is only one head of council at a time 00001, when all agents are used and their are no index left to spwan then head of council should use the remaning index to spawn head of council to look for ideal agents to view and report back so they can be terminated to save space. and in this condition new tasks should not be assigned . after the task is done the new created index of head of council should terminate.


### Agent Behavior
- [ ] Persona and behavior for all AI agents — including the voice bridge — should be driven by the constitution, so that editing the constitution updates persona consistently everywhere. Update the ethos as well as system instruction if necessary to achive this. 

- [ ] for models that can do deep thinking the ai should be able to do that. 

- [ ] Verctor database should be queried and updated. example: after reciving a task quary, after completing the task quary and the update if necessary. and during a task can also do the quary and update. Before updating agent should web search and then with the knowledge update. if web search not avilable then can skip web search. 


### Chat Page — UX Improvements
- [ ] Show a typing indicator (e.g., animated three dots) when a message is sent and the reply is taking time, similar to most modern chat apps.
- [ ] Support streaming message display in the chat interface when a response can be streamed, similar to most modern chat apps.
- [ ] Fix: sometimes a sent chat message gets no reply because the "Head of Council" disconnects — investigate via logs.
- [ ] Optimize chat history: automatically remove messages older than 7 days, but retain the last few messages regardless of age if there has been no further activity in that chat.
- [ ] The Head of Council should address the admin specifically as "Sovereign." All other users should be addressed by their username, or simply as "sir."

### Agents Page
- [ ] Fix scrollbar color — currently black in light mode; it should be dark/visible appropriately for the theme.
- [ ] Fix "Tier Groups: Expand All — Level 1, Level 2" text color — currently white in light mode; it should be dark for readability.
- [ ] Fix mismatch: the Agents list shows 3 agents, but the graph displays only 1.

### Other Fixes
- [ ] Users should be able to upload a profile picture.
- [ ] The "Genesis" step (per the original todo) for naming the country does not run after the API key is added — investigate and fix.

### Chat Widget Redesign
**Current behavior:**
Chat only works from the Chat page. When the user is on another page and a message arrives, a notification appears, and the user must navigate back to the Chat page to view/reply. If the browser is minimized or closed, the user can still communicate via the voice bridge.

**Desired behavior:**
- [ ] While on the Chat page, the user can chat and use voice as normal.
- [ ] When the user navigates away from the Chat page, a small floating chat icon (messenger-style) appears in the bottom-right corner of the screen.
- [ ] When a new message arrives, the user can click this icon to open a popup chat window and reply — with voice support available there too.
- [ ] Minimizing the popup chat window should switch communication over to the voice bridge.
- [ ] When the user returns to the Chat page, the popup should disappear (the popup essentially mirrors the Chat page's chat box when outside of it).
- [ ] When the browser is closed, the user can continue communicating via the voice bridge.
- [ ] The popup should live in the main layout (above all other pages) so it stays fixed in place while scrolling, and should not interfere with the use of other pages.
- [ ] Default appearance: a small dot in the corner; on hover, it expands into a circular chat icon; on click, the full chat popup window opens.


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

[ ] - Verify and improve all tools and add tools if necessary.
[ ] - Inject information to knowledge library, such as which tools to use for what, best practices and others to make the system work properly from the beginning.

## Suggested Verification Order

1. **P1 roadmap gaps** (§1) — fastest way to confirm claimed features actually work.
2. **Voice Bridge** (§2) — user-reported, Windows-breaking.
3. **Backend correctness** (§4) + **Safety** (§8) — correctness & security first.
4. **Logs** (§9) + **Testing/CI** (§5) — prove you can see and verify behavior.
5. **Frontend polish** (§3), **SDK** (§6), **DevOps/Windows** (§7).
6. **Dependencies** (§10) + remaining **production-readiness** (§8) — maintenance & hardening last.

Work top-down; each item becomes its own dive (verify → reproduce → fix → re-verify).
