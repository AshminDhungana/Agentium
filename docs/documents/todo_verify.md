# Agentium — Verification & Improvement Backlog

**File:** `docs/documents/todo_verify.md`
**Purpose:** A backlog of candidate issues and improvements to verify, fix, or build, one item at a time. Each item is written to be **self-contained**: copy a single item into an AI coding agent (or a human dev) and it should have enough context — problem, relevant files, concrete task, and a definition of done — to start work without reading the rest of this document.

Items are **not confirmed bugs unless marked "Confirmed."** Anything else is a lead to verify first, then fix.

**Priority key:**
- **[P0]** Breaks core functionality / data integrity / security — fix immediately
- **[P1]** Likely real defect, user-reported, or blocks a claimed feature
- **[P2]** Should verify; probable improvement or consistency gap
- **[P3]** Nice-to-have polish / preventative maintenance

**System vocabulary used below** (see `architectural_breakdown.md`, `README.md`): **Sovereign** = the human user/admin. **Head** (`0xxxx`) = executive agent. **Council** (`1xxxx`) = legislature. **Lead** (`2xxxx`) = department coordinator. **Task Agent** (`3xxxx`–`6xxxx`) = worker. **Code/Output/Plan Critics** (`7xxxx`/`8xxxx`/`9xxxx`) = independent judiciary with veto power.

---

## Table of Contents

1. [Log-Reported Defects (P0/P1)](#1-log-reported-defects)
2. [Chat Context & Cost Optimization](#2-chat-context--cost-optimization)
3. [Core Architecture — Tools & Skills](#3-core-architecture--tools--skills)
4. [Onboarding / Genesis Flow](#4-onboarding--genesis-flow)
5. [Models & Providers](#5-models--providers)
6. [Knowledge Base (ChromaDB) & Agent Ethos](#6-knowledge-base-chromadb--agent-ethos)
7. [Autoscaling & Head-of-Council Capacity](#7-autoscaling--head-of-council-capacity)
8. [Agent Behavior, Delegation & Persona](#8-agent-behavior-delegation--persona)
9. [Chat Page — Bugs](#9-chat-page--bugs)
10. [Chat Page — UX](#10-chat-page--ux)
11. [Floating Chat Widget](#11-floating-chat-widget)
12. [Agents Page — UI Bugs](#12-agents-page--ui-bugs)
13. [Miscellaneous](#13-miscellaneous)
14. [Roadmap Consistency Audit](#14-roadmap-consistency-audit)
15. [Voice Bridge](#15-voice-bridge)
16. [Frontend Polish & Accessibility](#16-frontend-polish--accessibility)
17. [Backend Correctness](#17-backend-correctness)
18. [Testing & CI](#18-testing--ci)
19. [SDKs (Python / TypeScript)](#19-sdks-python--typescript)
20. [DevOps / Windows Compatibility](#20-devops--windows-compatibility)
21. [Production-Readiness Checklist](#21-production-readiness-checklist)
22. [Log & Audit Verification](#22-log--audit-verification)
23. [Dependency Updates](#23-dependency-updates)
24. [Suggested Verification Order](#24-suggested-verification-order)

---

Here’s a **condensed checklist** of the most urgent fixes to address the issues:

---
### ✅ Critical Fixes

- [ ] **Fix Redis write in Genesis** – define `get_redis_client()` and add missing `await` so Head of Council state persists.
- [ ] **Handle missing Head gracefully** – prevent WebSocket from closing immediately; return a clear error instead.
- [ ] **Correct duplicate `tools` argument** in LLM provider call to avoid fallback errors.

---

**Order of execution:**  
Backend Redis fix → WebSocket error handling → frontend UI enhancements.

## 1. Log-Reported Defects

Confirmed from application logs. Fix in the priority order given at the end of this section.

### 1.4 — [P2] Redis AOF fsync slow (performance warning, non-blocking)
**Problem:** Redis logs warn that asynchronous AOF fsync is taking too long due to slow disk I/O. Doesn't stop the app but degrades performance under load.
**Task:** Check the disk backing the Redis volume; consider `appendfsync everysec` (default, safe tradeoff) vs `no` (faster, less durable) depending on how critical Redis durability is for this deployment; document the chosen tradeoff.
**Acceptance criteria:** Warning no longer appears under normal load, or the tradeoff is explicitly documented as accepted.

### 1.5 — [P0] MinIO using default credentials (`minioadmin:minioadmin`)
**Problem:** Security risk — default credentials in any non-trivial deployment.
**Task:** Set `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` to generated, non-default values in `docker-compose.yml` / `.env.example`, and document that they must be rotated on first deploy. Add a startup check that warns/blocks if defaults are still in use.
**Acceptance criteria:** Fresh install requires the user to set (or auto-generates) non-default MinIO credentials; a startup guard flags the default pair if detected. If mino default is used store data locally inside docker . 

### 1.6 — [P3] nginx `user` directive warning (cosmetic)
**Problem:** nginx logs an ignored `user` directive warning because the master process doesn't run as root.
**Task:** Remove the `user` directive from `nginx.conf` in non-root deployments.
**Acceptance criteria:** Warning no longer appears in nginx startup logs.

### 1.7 — [Informational, no action] PostgreSQL FATAL messages during init/teardown
**Note:** `FATAL: database "agentium" does not exist` and `terminating connection due to administrator command` are expected during first-boot DB creation and test cleanup — not runtime issues. Leave as-is; do not "fix" these into silence without confirming they don't mask a real failure elsewhere.

**Priority order for this section:** 1.1 (breaks core endpoints) → 1.2 (breaks browser feature) → 1.3 (may corrupt/incomplete genesis state) → 1.5 (security) → 1.4 → 1.6.

---

## 2. Chat Context & Cost Optimization

### 2.1 — [P1] Reduce token usage by sending only relevant chat context to the LLM
**Problem:** The full chat history is currently sent to the model on every turn. As conversations grow, so does the payload — even though most earlier turns are irrelevant to the current one. This wastes tokens, adds latency, and increases cost.
**Task — implement in layers:**

1. **Sliding window (default):**
   - Send only the last N raw messages (start N=8–10 turns; make configurable via env/setting).
   - Always pin the system prompt and the first user message (usually contains original task/intent) regardless of window position.
2. **Background summarization** (don't just drop old messages):
   - Periodically summarize messages that fall outside the window into a short structured memo (key facts, decisions, open threads) — not a generic summary.
   - Run summarization asynchronously on a cheap/fast model so it never blocks the user-facing response.
   - Store the running summary alongside the chat record (no separate memory store needed initially).
   - Include the latest summary + pinned messages + recent window in every request.
3. **On-demand full-history retrieval (agent-requested):**
   - Expose a tool (e.g. `get_full_history` / `search_chat_history`) the LLM can call when window + summary aren't enough.
   - Default to a plain chronological fetch for "what did we say earlier" — semantic/RAG search over casual chat tends to retrieve disjointed, out-of-context snippets. Only add RAG-style search once conversations are long enough in production to justify it.
   - Merge fetched content into context without duplicating what's already in the window/summary.
4. **Cost/latency efficiency:**
   - Apply prompt caching to the stable parts of the payload (system prompt, summary, older pinned content) so only the new turn is "fresh" per call.
   - Count tokens before each call to catch overflow before hitting API limits, with graceful truncation as a fallback.
   - Watch context ordering — don't bury important retrieved/summarized info in the middle of a long prompt; put critical info near the start or end (models attend better to the edges of long contexts).

**Acceptance criteria:**
- Default window size configurable without a code change.
- Summarization runs async and adds no measurable latency to the user-facing response.
- `get_full_history` tool implemented, callable by the agent, returns merged/deduped context.
- Prompt caching applied to static/stable context segments.
- Token usage before/after is measured and documented (e.g. in a short benchmark note).
- Tested on a 50+ message conversation; confirm relevant older context is still retrievable via summary or tool call.

**Open questions to resolve during implementation:** window size in messages vs. tokens; summary refresh trigger (every N messages vs. every window shift); whether to revisit chronological-vs-semantic retrieval once real production conversation lengths are observed.

---

## 3. Core Architecture — Tools & Skills

> See `tool_and_skill_creation.md` for the canonical tool/skill pattern (the `vector_db` tool + skill pair is the reference implementation). Every new tool below should follow that guide: `execute(action=...)` dispatch, dict returns with `success`, lazy-init dependencies, module-level singleton, registered in `tool_registry.py` with correct `authorized_tiers`, and a matching `SKILL.md` under `backend/.agentium/skills/<name>/` that the tool's description/`help` action points to.

### 3.1 — [P1] Isolated Task Agent tool access
**Problem:** Unclear how a Task Agent, when executing inside its isolated Remote Executor container, is actually meant to access/invoke tools — and what commands it's realistically capable of running there.
**Task:** Trace the spawn-to-execution path for a Task Agent end to end. Document: (a) what the sandboxed container can and cannot do, (b) how tool calls are proxied into/out of the sandbox given the "Brains vs. Hands" separation (raw data/PII stays in the executor, only shape/schema returns to the agent), (c) the exact spawn mechanism. Fix any gap where a tool a Task Agent is authorized for is actually unreachable from inside the sandbox.
**Acceptance criteria:** A documented, tested path exists for a Task Agent to call at least one file-system tool and one network tool from inside the sandbox, with PII/raw-data isolation intact.

### 3.2 — [P1] Tool Creation Tool
**Problem:** There's an existing tool-creation mechanism (`backend/services/tool_factory.py`, `backend/models/schemas/tool_creation.py`, `tool_creation_service`) but no tool that lets an *agent* invoke it to create new tools for itself.
**Task:** Build a `tool_creator` tool following the pattern in `tool_and_skill_creation.md` §2. It should call into the existing `tool_factory`/`tool_creation_service`, register the result in `tool_registry.py`, and grant it as a capability to Head/Council-tier agents (destructive-scope — do not expose to Task tier by default; enforce with both `authorized_tiers` and an in-tool guard per §2.4).
**Acceptance criteria:** An authorized agent can call `tool_creator` to define a new tool, have it appear in `tool_registry.tools` and `list_tools()` for the intended tiers, and successfully invoke the newly created tool in the same session. Ship unit + registration tests per §2.5.

### 3.3 — [P1] Skill Creation Tool
**Problem:** No tool lets an agent author and persist a new Skill (`SKILL.md`) at runtime.
**Task:** Build a `skill_creator` tool that writes a valid `SKILL.md` (correct YAML frontmatter enums, 50–300 char description, `## Steps` + `## Validation` sections per `tool_and_skill_creation.md` §3) to `backend/.agentium/skills/<name>/`, then triggers `seed_skills.py` (or calls the seeding function directly) so it's indexed into ChromaDB. Register in `tool_registry.py`; grant the capability to Head and Council agents.
**Acceptance criteria:** An authorized agent can call `skill_creator`, the resulting `SKILL.md` passes `parse_skill_file` validation, and a subsequent semantic search (`skill_manager.search_skills`) retrieves it. Ship a unit test per §3.5.

### 3.4 — [P2] Frontend tool creation → backend verification
**Problem:** Unconfirmed whether tools created via the frontend UI are actually persisted and registered correctly on the backend.
**Task:** Write an end-to-end test: create a tool from the frontend, confirm it appears in `tool_registry.tools`, is exported via `to_openai_tools`/`to_anthropic_tools`, and is invocable by an authorized agent.
**Acceptance criteria:** E2E test passes in CI; any gap found (e.g. registry not reloaded, cache staleness) is fixed.

### 3.5 — [P2] Upgrade read/write tools to modern coding-agent standards
**Problem:** Current file read/write tools are coarse compared to the precision modern coding agents expect.
**Task:** Add grep-style precise reads (line-numbered, with `offset`/`limit` params), sed-style precise edits (targeted replace by exact string or line range), and replace-by-line-number/offset writes — mirroring the ergonomics of `view`/`str_replace`-style tools.
**Acceptance criteria:** New read tool supports `offset`/`limit` and returns line-numbered output; new edit tool supports exact-match replace and fails loudly (not silently) on ambiguous/non-unique matches; both covered by unit tests.

### 3.6 — [P2] Full tool audit — close known gaps
**Problem:** Agents (including Critics) likely lack several tools a modern agent stack needs.
**Task:** Audit the full tool surface against agent needs. Known gaps to close: **web fetch** (retrieve a URL's content), **code execution** (sandboxed run, distinct from the Remote Executor's task execution), **tool search** (let an agent discover other tools + descriptions at runtime, e.g. by capability/tier). Register each in `tool_registry.py` with correct tiers per §2.4 of `tool_and_skill_creation.md`.
**Acceptance criteria:** All three gap tools exist, are tier-gated appropriately, have unit + registration tests, and each has a matching `SKILL.md`.

### 3.7 — [P2] Task-management tool set
**Problem:** No first-class set of tools for agents to create/query/update/close tasks programmatically.
**Task:** Design and implement a minimal task-management tool (`action=create|get|update|list|close`) wired into the existing task/DAG models, registered per the standard pattern.
**Acceptance criteria:** Tool round-trips a task through all actions in a test; registered with sane tier restrictions (e.g. Lead+ can create/close, Task tier can update status of its own assigned task).

### 3.8 — [P2] Web crawler tool + crawling-best-practices skill
**Problem:** No tool exists for deep web crawling (beyond a single fetch) — following links, understanding page structure, multi-page traversal.
**Task:** Add a `web_crawler` tool (cURL-based fetch + link traversal, depth-limited) registered for all tiers per the standard pattern. Pair it with a `.agentium/skills/web_crawling/SKILL.md` skill covering: crawling best practices (robots.txt respect, rate limiting, depth limits) and a reference list of ~100 major websites by category with short descriptions of what each contains, to help agents pick good sources. Follow the tool→skill "pointing" pattern from `tool_and_skill_creation.md` §4: name the skill path in the tool's description and `help` action; name the tool in the skill body; seed the skill into ChromaDB.
**Acceptance criteria:** Tool successfully crawls a multi-page test site respecting depth limits; skill passes `parse_skill_file` validation and is retrievable via semantic search for a query like "what site should I use to look up X."

---

## 4. Onboarding / Genesis Flow

### 4.1 — [P1] Fix Genesis setup sequence ordering
**Problem:** The nation-naming popup currently appears **before** the Head of Council is active, and no reply is sent after the name is submitted. Correct order should be: API key added → Head of Council connects → welcome message sent → nation-naming popup appears → reply is given after naming.
**Note:** This is likely the same root cause as "Genesis step doesn't run after API key is added" (see 22.x logging note) — investigate together rather than as two separate bugs.
**Task:** Trace the genesis state machine from API-key-added to name-submitted. Ensure the popup only renders once Head is confirmed active, and that submitting a name triggers a visible reply from Head.
**Acceptance criteria:** On a fresh install, the sequence happens in the documented order every time; submitting the nation name always produces a Head reply in the chat.

### 4.2 — [P2] Render the nation-naming notification as Markdown
**Problem:** The "establishing the AI Nation" notification and the one-time nation-naming popup on the chat page render raw Markdown source instead of formatted output.
**Task:** Route both notification bodies through the existing Markdown renderer used elsewhere in the chat UI.
**Acceptance criteria:** Both notifications render headings/bold/lists correctly instead of literal `**`/`#` characters.

---

## 5. Models & Providers

### 5.1 — [P2] Correct pricing display for free models
**Problem:** Free models show pricing info they shouldn't; pricing should be pulled live from each provider's API.
**Task:** Suppress pricing display when a model is free. Fetch pricing directly from provider APIs — note most providers use an OpenAI-compatible schema, but Anthropic's differs; handle both explicitly rather than assuming one shape.
**Acceptance criteria:** Free models show no price; paid models show live, provider-sourced pricing for both an OpenAI-style and an Anthropic provider.

### 5.2 — [P2] Fix uneditable Rate Limit input field
**Problem:** On the Model page, "Rate limit (requests per minute)" defaults to 60 and can't be typed over or cleared — only the up/down steppers work.
**Task:** Fix the input binding so it behaves as a normal editable numeric field (clearable, typeable, steppers still functional).
**Acceptance criteria:** User can clear the field and type an arbitrary value; steppers still increment/decrement correctly.

### 5.3 — [P2] Auto-populate rate limit & max tokens from provider API
**Problem:** These fields aren't pre-filled from the selected model's provider metadata.
**Task:** When a model is selected while adding an AI module, fetch rate limit and max tokens from the provider API if exposed, and reflect the same values on the Model Config page. Fall back to current defaults (max tokens: 4000) when unavailable.
**Acceptance criteria:** Selecting a model with published limits auto-fills both fields; selecting one without falls back to documented defaults without erroring.

### 5.4 — [P3] Model search/filter after fetch
**Problem:** After clicking "Fetch," the model list has no way to filter by substring.
**Task:** Add a search box above the fetched model list that filters by substring match (e.g. "openrouter" narrows to `openrouter/...` entries).
**Acceptance criteria:** Typing a substring live-filters the list; clearing the box restores the full list.

### 5.5 — [P2] Validate all configured model APIs actually work
**Task:** Systematically test every provider integration exposed on the Model page (auth, list-models, completion call) and fix any that silently fail.
**Acceptance criteria:** A documented pass/fail matrix across all supported providers; failures either fixed or filed as their own follow-up items.

### 5.6 — [P2] Effort/thinking controls on Model Config
**Problem:** No UI control for extended/deep-thinking effort on models that support it.
**Task:** Add an "effort" setting on the Model Config page; wire it through to the provider's extended-thinking/reasoning parameter where supported, no-op where not. When thinking mode is active, replace the animated three-dot typing indicator with a "Thinking…" label in the chat page.
**Acceptance criteria:** Setting is present only for models that support it (or is a no-op/hidden otherwise); "Thinking…" label appears during an active thinking-mode generation.

---

## 6. Knowledge Base (ChromaDB) & Agent Ethos

### 6.1 — [P1] Give every agent environment/host context in its Ethos
**Problem:** Agents lack basic situational grounding: that they run inside a Docker container, where the host is relative to the container, what "the internet" means from inside the container, what part of the host filesystem they're allowed to touch, and how to reach the host. Example failure mode: a user says "create a folder on my desktop" and the agent doesn't understand this means the *host* filesystem, not the container's.
**Task:** Add this context to both the default Ethos and ChromaDB (constitution-adjacent, read-only collection) so it's available at agent creation and via RAG.
**Acceptance criteria:** A new agent, without any task-specific context, correctly answers "where does 'my desktop' refer to" and "can you reach the internet."

### 6.2 — [P2] Seed foundational operating knowledge
**Task:** Populate the knowledge base with: which tools to use and when, general best practices, host-system access patterns, basic CMD/PowerShell usage, and common CLI utilities (`grep`, `curl`, etc.). Decide the delivery mechanism — baked into ethos/constitution, read from Chroma at startup, or seeded at agent-creation time — and implement it consistently.
**Acceptance criteria:** Decision documented; knowledge retrievable via `search_skills`/RAG query for representative prompts ("how do I fetch a URL," "what's my working directory").

### 6.3 — [P2] Update default agent Ethos with working procedures
**Task:** Give every agent's default Ethos a basic statement of its working procedure/method and a summary of its own capabilities.
**Acceptance criteria:** A fresh agent's Ethos, inspected directly, includes both sections.

### 6.4 — [P3] Seed a web-knowledge index (major sites reference)
**Task:** Add a reference list of major websites and what kind of information each contains, so agents choose better sources when searching the web. (Can be merged with the crawler skill in 3.8 rather than duplicated — check before building twice.)
**Acceptance criteria:** List seeded into ChromaDB; retrievable via a query like "where would I look up X."

### 6.5 — [P2] Search-before-acting workflow
**Task:** Before acting on unfamiliar information, an agent should query ChromaDB first; if the knowledge isn't there, perform a web search and write the result back to Chroma before proceeding. If web search is unavailable, fall back to whatever's already in Chroma rather than blocking.
**Acceptance criteria:** Implemented as a step in the agent's standard task-execution flow (ties into 6.6/6.7 and the Ethos "Read → Update → Compress" discipline described in `architectural_breakdown.md` §7); tested with a query the agent has no prior knowledge of.

### 6.6 — [P2] Standard structure for knowledge-base writes
**Problem:** No shared schema for how agents write updates to ChromaDB, risking inconsistent formats and duplicate entries.
**Task:** Define and document a standard write structure (fields, dedup key strategy, revision metadata — see README's "Revision-Aware" claim) and route all agent writes through it.
**Acceptance criteria:** All agent code paths that write to Chroma use the shared structure; a duplicate-write test confirms deduplication works.

### 6.7 — [P2] Ethos knowledge-retrieval/update steps
**Problem:** The Ethos definition currently has no explicit **knowledge retrieval** step (query ChromaDB + web search) or **knowledge update** step (write back to ChromaDB when required).
**Task:** Locate where Ethos is constructed/loaded and add both steps explicitly so every agent performs them as part of its standard loop, not as an optional behavior.
**Acceptance criteria:** Ethos text includes both steps; an agent's task trace shows a retrieval call and (when applicable) an update call.

### 6.8 — [P2] Verify system-message usage across both LLM APIs
**Problem:** Agentium talks to both OpenAI-style and Anthropic-style APIs, which handle system prompts differently. Unclear whether system messages are actually being sent/used correctly in both cases.
**Task:** Review the request-building code for both provider paths. Confirm a system message is sent in each; if not, determine what belongs in it (ethos, constitution excerpt, role) to measurably improve output quality/reliability, and implement.
**Acceptance criteria:** Both provider paths send an explicit system message; a before/after comparison (even qualitative) is documented.

---

## 7. Autoscaling & Head-of-Council Capacity

### 7.1 — [P2] Head-of-Council overflow handling when agent slots are full
**Problem:** Only one Head (`00001`) is active at a time. If all 99,999 agent ID slots are full with none free to spawn, there's no defined recovery path.
**Task:** When no slots remain, have Head spawn a *temporary* secondary Head instance into one of the remaining slots, whose sole job is to review idle agents and report which can be safely liquidated. Pause new task assignment while this review runs. Once complete, the temporary instance terminates itself.
**Acceptance criteria:** Simulated full-capacity scenario triggers the temporary-Head review flow; idle agents are correctly identified; new-task assignment resumes automatically once slots are freed; temporary instance confirmed terminated afterward.

---

## 8. Agent Behavior, Delegation & Persona

### 8.1 — [P1] Head should delegate, not execute — and stay responsive while busy
**Problem:** Two related issues reported to cause chat slowness: (a) when a user gives Head a task, Head sometimes executes it directly instead of delegating to Lead/Task agents, which blocks it from chatting/reporting; (b) Head can't answer a new question while still processing a previous one.
**Task:** Enforce that Head's role is control + delegation only — it should hand tasks to the appropriate Lead/Task agents and remain free to converse and report status. Ensure Head's request handling is non-blocking so a new incoming message gets an immediate acknowledgment/response even while a prior task is in flight.
**Acceptance criteria:** Sending Head a task never blocks the chat channel; Head's own tool/execution activity does not appear inline in normal chat latency; a concurrency test confirms Head answers message #2 while task #1 is still running.

### 8.2 — [P2] Constitution-driven persona for all agents (including voice)
**Task:** Ensure persona/behavior for every agent — including the voice bridge — is driven entirely by the Constitution, so editing the Constitution updates behavior consistently everywhere. Audit Ethos and system-instruction construction to confirm this is actually true today (not just documented).
**Acceptance criteria:** Editing a constitutional behavior clause and reseeding is reflected in a fresh agent's response *and* the voice bridge's persona without any other code change.

### 8.3 — [P2] Enable deep thinking where supported (ties to 5.6)
**Task:** For models with extended/deep-thinking support, confirm agents actually invoke that mode when configured to.
**Acceptance criteria:** A thinking-capable model shows thinking traces/latency consistent with the mode being active when enabled via 5.6's setting.

### 8.4 — [P2] Vector DB read/write checkpoints during task execution
**Task:** Query and update ChromaDB at three points: after receiving a task, after completing it, and mid-task if needed. Before writing an update, do a web search first and fold the result into the update; skip the search step gracefully if web search is unavailable.
**Acceptance criteria:** A traced task shows all three checkpoint interactions with Chroma; missing web search doesn't block the update.

---

## 9. Chat Page — Bugs

- **9.1 — [P2]** "Voice Bridge Not Running" notification should fire once per session (after login), not repeat on every reconnect attempt or status flip. *(Cross-reference: this is the same root cause as 15.2/15.3 below — fix once, verify in both places.)*
- **9.2 — [P2]** Voice input bugs: starting voice input doesn't appear in the chat transcript; opening voice settings throws a frontend console error. Reproduce both, fix root causes.
- **9.3 — [P1]** A task can get stuck showing "Deliberating" indefinitely. Reproduce via logs, identify the stall point (likely a Council micro-vote or Lead handoff that never resolves), and add a timeout/escalation so it can't hang forever.
- **9.4 — [P3]** Add a follow-up icon next to the existing hover "copy" icon on chat messages, which copies the message into the compose box for editing and resending.

---

## 10. Chat Page — UX

- [ ] Improvements in how ai message are sent to the user, currently the ai sends small messages as reply to the user, this was intended design but it is too small. think of what can be done to imporve on that, do web serch for ideas and improvement.

- [ ] Improvement in display of animation in the chatpage, right now only three dot animation is shown, for thinking that should be shown and for tools use or processing number of tools use or something else should be shown to the user so it keeps user engaging.

- **10.2 — [P2]** When a user pastes long text into the compose box, collapse it to a `[x lines pasted]` placeholder; after sending, show the same collapsed form in the message with an expand button to view the full text.
- **10.3 — [P2]** Typing indicator: animated three-dot indicator while a reply is generating (distinct from the "Thinking…" label in 5.6, which is for active extended-thinking mode specifically). for thinking the three dot will be fine, and for tool use add no of tools used +count or somthing similar, the goal is to make the chat user engaging. 
- **10.4 — [P1]** Investigate and fix cases where Head disconnects mid-chat and a sent message never receives a reply — trace via logs, likely a WebSocket/session lifecycle bug.
- **10.5 — [P2]** Auto-prune chat history older than 7 days, but always retain the last few messages regardless of age if there's been no further activity.
- **10.6 — [P3]** Addressing convention: Head addresses the admin as "Sovereign"; all other users are addressed by username, or "sir" if no username context is available.

---

## 11. Floating Chat Widget

**Current behavior:** Chat only works from the Chat page. Messages arriving while the user is elsewhere trigger a notification requiring a page switch to reply. If the browser is minimized/closed, the voice bridge is the only remaining channel.

**Desired behavior (build as one cohesive feature):**
- Chat page keeps its full chat + voice experience, unchanged.
- Navigating away from the Chat page surfaces a small floating messenger-style icon in the bottom-right corner.
- New messages: clicking the icon opens a popup window with reply + voice support.
- Minimizing the popup hands communication back to the voice bridge.
- Returning to the Chat page hides the popup — it only mirrors the chat box while the user is elsewhere.
- Closing the browser falls back to the voice bridge.
- The popup lives in the main layout above all pages, stays fixed while scrolling, and never interferes with other pages' interactions.
- Default state: small dot in the corner → expands to a chat icon on hover → opens the full popup on click.

**Acceptance criteria:** All eight behaviors above verified manually across at least two pages other than Chat; popup and voice-bridge handoff tested in both directions (popup→minimize→voice, and voice→open popup).

---

## 12. Agents Page — UI Bugs

- **12.1 — [P3]** Scrollbar renders black in light mode; should adapt to the active theme.
- **12.2 — [P3]** "Tier Groups: Expand All — Level 1, Level 2" text renders white-on-white in light mode; should use a theme-aware dark color.
- **12.3 — [P1]** Agents list shows 3 agents but the graph view renders only 1 — data/render mismatch; fix so both views reflect the same source of truth.

---

## 13. Miscellaneous

- **13.1 — [P3]** Allow users to upload a profile picture.

---

## 14. Roadmap Consistency Audit

Items marked `[ ]` (incomplete) in `docs/documents/todo.md` while their parent phase is marked ✅ — verify each is actually done, or unmark the phase.

- **14.1 — [P1]** Phase 6: "Real-time MCP tool usage stats; revoked tools unavailable < 1 second" is unchecked though Phase 15.2 claims it's done — confirm the sub-second revocation path is real (`backend/services/.../mcp*` + Redis key `agentium:mcp:revoked`).
- **14.2 — [P1]** Phase 7: "Drag-and-drop agent reassignment" unchecked though 18.2 claims `AgentTree.tsx` uses `react-dnd` — confirm it actually works end-to-end.
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

---

## 24. Suggested Verification Order

Work top-down. Each item becomes its own dive: **verify → reproduce → fix → re-verify** — don't mark anything done on inspection alone.

1. **Log-reported P0/P1 defects (§1)** — these are confirmed from logs and block core functionality; fix first.
2. **Roadmap P1 gaps (§14)** — fastest way to confirm claimed "done" features actually work.
3. **Chat context optimization (§2)** — directly affects cost and latency on every request.
4. **Voice Bridge remaining item (§15.3)** — user-facing, Windows-affecting.
5. **Backend correctness (§17) + Safety (§21.2)** — correctness and security before anything cosmetic.
6. **Core architecture — tools & skills (§3)** — unblocks agents building their own capabilities.
7. **Logs & audit (§22) + Testing/CI (§18)** — you need to be able to see and verify behavior before trusting fixes elsewhere.
8. **Agent behavior/delegation (§8), onboarding (§4), models/providers (§5), knowledge base (§6)** — core product experience.
9. **Chat page bugs/UX (§9–§11), Agents page (§12), frontend polish/a11y (§16)** — user-facing polish.
10. **SDKs (§19), DevOps/Windows (§20)** — developer-facing and deployment concerns.
11. **Dependencies (§23) + remaining production-readiness items (§21.1, 21.3–21.5)** — maintenance and hardening last.