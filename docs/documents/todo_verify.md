# Agentium — Verification & Improvement Backlog

**File:** `docs/documents/todo_verify.md`
**Purpose:** A surface-level backlog of *candidate* issues to verify, improve, or fix one-by-one. Items are **not confirmed bugs** — they are things to look into, in the order listed. Each entry has a priority tag:

- **[P1]** Likely real defect / user-reported / blocks correctness or a claimed feature
- **[P2]** Should verify; probable improvement or consistency gap
- **[P3]** Nice-to-have polish / preventative maintenance

--

# Project TODO — Agentium / Voice Bridge

- [ ] find the problem fix and solve the issue, While creating a task the task got stuck at deliberating, The system still shows no Task Agent registered for dispatch, Sovereign. The spawn of Scribe (30001) succeeded at the agent level but hasn't yet bound to the execution pool the dispatcher checks. 

**Status of task T80280257:**
- ✅ Created & deliberated
- ✅ Dispatched to Lead 20001
- ⚠️ Execution blocked — no Task Agent reachable by dispatcher
- 🆕 Scribe (30001) spawned but not yet picked up, 

the newly spawned Task Agent (Scribe, 30001) registers in the agent roster but the dispatcher's execution pool is refreshed separately — so it hasn't been "bound" yet, leaving the system's live count at 0 Task Agents. The dispatch therefore has nothing to assign execution to, even though a capable agent exists. This is a sync gap between agent creation and the runtime worker pool, not a permissions or task-definition issue
**1. A database migration error (the real blocker):**
```
ERROR: constraint "fk_tasks_deliberation_id" of relation "tasks" does not exist
STATEMENT: ALTER TABLE tasks DROP CONSTRAINT fk_tasks_deliberation_id
```
This failed migration (at 05:40:23 and again 05:44:45) means the `tasks` table schema is in a partially-migrated state. The dispatch/assignment path that depends on the deliberation linkage is likely broken as a result — so tasks can't be bound to an executor even though the Task Agent (Scribe) exists. That's why the dispatcher reports "No Task Agent available."


- [ ] api keys  that supports thinking should be able to use it. configure for each api provider if avialable

- [ ] vector database should not store ethos, ethos should be stored in postgres, check what ethos is pushed in vector database and where. 

- [ ] Find where the ethos is created, and add steps for a **knowledge retrieval** step and a **knowledge update** step — query the vector database to gather information, and also perform a web search; update the vector database when required.

- [ ] Review how system messages are passed to the API. There are two different APIs — OpenAI and Anthropic. Check whether a system message is currently being sent in each case. If not, determine what can be done, per the project, to use system messages to improve performance.

- [ ] **Tool creator tool** — Check the existing tool-creation feature inside the program (there is a tool-creation mechanism via `tool_creation_service` and others). Create a tool that helps with creating new tools, add it to the tool registry, and give the relevant agent the capability to use it.

- [ ] **Skill creation tool** — A tool that helps create new skills and saves them to `.agentium/skills/`, which will be automatically seeded into ChromaDB. Add it to the tool registry, and give the head and council members the capability for their relevant agent category.

- [ ] **Browser control tool — check and improve.** The `browser_control` tool is still **non-functional** due to a code-level defect (Sync API used inside an asyncio loop). Search the web for fixes/improvements. Also verify that browser use is registered and functioning inside the Browser tab on the Tasks page. Review all related features overall.

- [ ] Head should be able to answer new questions while it is still processing/answering a previous one.

- [ ] When a user gives a task to head, head should not execute it directly — head should delegate to other agents so it stays free to chat and report. Head's main job is to control and delegate tasks, not to execute them.

- [x] Add a tool to read/update information in the vector database, usable by every agent, pointing to the skill at `.agentium/skills/` for full usage instructions. Create the tool, add it to the tool registry, and give every agent the capability to use it. For best practices on pointing a tool to a skill, research this via web search and/or document it in the tool's description or help function (stating where the skill lives and how to use it). The system also has a function to add skills to ChromaDB, so agents can access the info there too.

- [ ] Add a **web crawler tool** that crawls the web using cURL and other methods, can deep-dive a page, and can visit every URL to understand the page's content. Add it to the tool registry and give every agent the capability to use it. Also add a skill that lists crawling best practices and the top 100 websites for different purposes with descriptions — covering the most-used sites on the internet. The crawl skill should live in and point to `.agentium/skills/`. For best practices on pointing a tool to a skill, research this via web search and/or document it in the tool's description or help function (stating where the skill lives and how to use it). The system also has a function to add skills to ChromaDB, so agents can access the info there too.


---

## 1. Core Architecture — Task Agents & Tools

- [ ] **Isolated container execution** — Determine how a Task Agent, when running inside an isolated container, can still access/use tools. Check what commands it's actually capable of running, and clarify the mechanism by which a Task Agent gets spawned.
- [ ] **Tool Creation Tool** — Review `backend/models/schemas/tool_creation.py` and `backend/services/tool_factory.py`, then build a tool that lets the system create new tools and wire it into `backend/core/tool_registry.py` and also add to agent capability. 

- [ ] **Verify frontend tool creation** — Confirm that tools added from the frontend are actually created correctly on the backend (test end-to-end).
- [ ] **Upgrade read/write tools** — Bring these up to the standard of modern AI coding tools: precise reads with line numbers (grep-style), precise edits (sed-style), and replace-by-line-number/offset.
- [ ] **Skill Creation Tool** — Similar concept to Claude Skills. Store skills at `./backend/.agentium/skills` and wire the tool into `backend/core/tool_registry.py`.
- [ ] **Tool audit** — Do a full pass over the project to identify what other tools agents need (including the Critic agent), and register them properly in `backend/core/tool_registry.py`. Known gaps: web fetch, code execution, and tool search (a tool that lets agents search for/discover other tools and their descriptions).
- [ ] **Task management tools** — Add a proper set of task-management tools for the system.

---

## 2. Onboarding / Setup Flow

- [ ] **Fix setup sequence** — The correct order should be: API key added → Head of Council connects → welcome message sent → nation-name popup appears → reply is given. Currently the nation-name popup appears *before* the Head of Council is active, and no reply is sent after the name is submitted.
  - *(This looks like the same root cause as the "Genesis step doesn't run after API key is added" bug — worth investigating together.)*

---

## 3. Models & Providers

- [ ] **Correct pricing display** — Free models should not show pricing. Pricing info should be pulled directly from each provider's API (note: most providers use an OpenAI-style API structure, but Anthropic's is different — handle both).
- [ ] **Fix Rate Limit input field** — On the Model page, the "Rate limit (requests per minute)" field defaults to 60 and can't be cleared/typed over — only the up/down arrows work. Make it a normal editable input.
- [ ] **Auto-populate rate limit & max tokens** — When adding an AI module, pull rate limit and max tokens from the provider's API once a model is selected (if available), and reflect the same values on the Model Config page. Fall back to current defaults (max tokens: 4000) if the API doesn't expose this.
- [ ] **Model search** — In the model selection section, after the user hits "Fetch" and the model list loads, add a search box at the top that filters the list by substring (e.g. typing "openrouter" shows only entries containing "openrouter", such as `openrouter/nvidia/xxx`).
- [ ] **Validate all model APIs** — Check that every configured model API actually works correctly on the Model page.
- [ ] **Effort / thinking controls** — Add an "effort" setting on the Model Config page. For models that support extended/deep thinking, enable it where possible (skip if unsupported).
  - [ ] When thinking mode is active, replace the animated three-dot typing indicator with a "Thinking..." label in the chat page.

---

## 4. Knowledge Base (Chroma DB) & Agent Ethos

- [ ] **Environment context in ethos** — After reading the constitution, every agent should be given basic situational context: that it's running inside a Docker container, where the host system is relative to the container, where "the internet" is from the container's perspective, what part of the host system it's allowed to operate in, and how to access the host. Example: if a user says "create a folder on my desktop," the agent should understand this means the *host* filesystem, not inside the container. This should go into both the ethos and Chroma DB.
- [ ] **Seed foundational knowledge** — Populate the knowledge base with core operating info: which tools to use and when, general best practices, how to access the host system, basic CMD/PowerShell usage, and common utilities (grep, curl, etc.). Decide the best delivery mechanism (baked into ethos/constitution, read from Chroma on startup, or seeded at agent creation) and implement it.
- [ ] **Update default agent ethos** — Give every agent's default ethos a basic understanding of its working procedures/methods and a summary of what it's capable of doing.
- [ ] **Seed web-knowledge index** — Add a reference list of major websites and what kind of information each contains, so agents can search the web more effectively.
- [ ] **Search-before-acting workflow** — Before doing/knowing something, an agent should search the web and Chroma DB; if the knowledge isn't in Chroma, update it there first, then proceed. If web search isn't available, fall back to whatever is already in Chroma.
- [ ] **Shared knowledge-update structure** — Build a standard structure for how agents write updates to Chroma DB so all agents update it consistently and duplicate entries are minimized.

---

## 5. Autoscaling & Head of Council Cap

- [ ] **Head of Council overflow handling** — Only one Head of Council (00001) is active at a time. When all agent index slots are full and none are left to spawn, the Head of Council should use one of the remaining slots to spawn a *temporary* Head of Council instance whose job is to review idle agents and report which ones can be terminated to free up space. While this is happening, no new tasks should be assigned. Once the review is complete, the temporary instance should terminate itself.

---

## 6. Agent Behavior & Persona

- [ ] **Constitution-driven persona** — Persona/behavior for all agents (including the voice bridge) should be driven entirely by the constitution, so that editing the constitution updates behavior consistently everywhere. Update ethos and system instructions as needed to make this actually true.
- [ ] **Enable deep thinking where supported** — For models capable of extended/deep thinking, make sure the agent actually uses that capability (ties into item in Section 3).
- [ ] **Vector DB read/write during tasks** — Chroma should be queried and updated at these points: after receiving a task query, after completing it, and mid-task if needed. Before writing an update, the agent should do a web search first and incorporate that into the update; if web search is unavailable, it's fine to skip that step.

---

## 7. Chat Page — Functionality & Bugs

- [ ] **Markdown rendering** — Model replies are returned as markdown but the chat UI doesn't render them properly. Check how the backend generates/formats the markdown and improve the frontend reply box to render it well (example failing case: task-status replies with headers/bold/bullets).
- [ ] **Slash command support** — Add `/clear` (and other slash commands) to the chat page. `/clear` should clear the chat on the frontend, and from then on only show messages sent *after* the clear timestamp.
- [ ] **"Voice Bridge Not Running" notification loops** — This should show once after login, but currently repeats. Fix so it only fires once per session.
- [ ] **Voice input bugs** — Starting voice input doesn't show up in the chat, and clicking voice settings throws an error in the frontend console.
- [ ] **Task stuck "Deliberating"** — A task shows as running but is stuck in "deliberating" status. Check logs to find the root cause and fix.
- [ ] **Follow-up button on messages** — A copy icon already exists on hover over chat messages. Add a follow-up icon next to it that copies the message into the compose box so the user can edit and resend it.

---

## 8. Chat Page — UX Improvements

- [ ] **Typing indicator** — Show an animated three-dot indicator while a reply is being generated (see Section 3 for the "Thinking..." variant).
- [ ] **Streaming replies** — Support streaming message display when the backend can stream a response.
- [ ] **Head of Council disconnects mid-chat** — Sometimes a sent message gets no reply because the Head of Council disconnects. Investigate via logs and fix.
- [ ] **Chat history retention** — Automatically prune messages older than 7 days, but always keep the last few messages regardless of age if there's been no further activity in that chat.
- [ ] **Address convention** — The Head of Council should address the admin as "Sovereign." All other users should be addressed by username, or simply as "sir."

---

## 9. Chat Widget Redesign (Floating Popup)

**Current behavior:** Chat only works from the Chat page. Messages that arrive while the user is elsewhere trigger a notification, requiring a return to the Chat page to reply. If the browser is minimized/closed, the voice bridge is the only channel.

**Desired behavior:**
- [ ] Normal chat + voice on the Chat page, unchanged.
- [ ] When navigating away from the Chat page, show a small floating (messenger-style) chat icon in the bottom-right corner.
- [ ] New messages: clicking the icon opens a popup chat window with reply + voice support.
- [ ] Minimizing the popup switches communication back over to the voice bridge.
- [ ] Returning to the Chat page hides the popup (it mirrors the Chat page's chat box only while the user is elsewhere).
- [ ] Closing the browser falls back to the voice bridge.
- [ ] The popup lives in the main layout (above all pages), stays fixed while scrolling, and doesn't interfere with other pages.
- [ ] Default state: a small dot in the corner → expands into a chat icon on hover → opens full popup on click.

---

## 10. Agents Page — UI Bugs

- [ ] Scrollbar is black in light mode — should adapt to theme (dark/visible appropriately).
- [ ] "Tier Groups: Expand All — Level 1, Level 2" text is white in light mode — should be dark for readability.
- [ ] Agents list shows 3 agents, but the graph view only shows 1 — fix the mismatch.

---

## 11. Other Fixes

- [ ] Allow users to upload a profile picture.

---

### Note on merges
The original list had two entries that appear to describe the same bug: *"the popup to ask the nation name appears before the Head of Council is active and no reply is given after"* and *"the Genesis step for naming the country doesn't run after the API key is added."* These are combined under **Section 2** — worth confirming they're the same root cause before fixing.

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
