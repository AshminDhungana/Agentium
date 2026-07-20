# Constitution-Driven Persona for All Agents (incl. Voice)

- **Date:** 2026-07-20
- **Status:** Design (approved in principle, pending spec review)
- **Task ref:** 8.2 — [P2] Constitution-driven persona for all agents (including voice)
- **Project:** Agentium

## 1. Goal & Acceptance Criteria

**Goal:** Persona and behavior for *every* agent — all tiers (Head `0xxxx`, Council `1xxxx`, Lead `2xxxx`, Task `3xxxx`, and the three Critics `7/8/9xxxx`) *and* the voice bridge — are driven **entirely** by the Constitution. Editing a constitutional behavior clause and saving it (via the UI) updates behavior consistently everywhere with **no other code change**.

**Primary acceptance criterion:** Editing a constitutional behavior clause in the UI and saving it is reflected in (a) a fresh agent's response *and* (b) the voice bridge's persona, with no code change.

**Secondary criteria:**
- Ethos holds **no** persona/constitutional ideas; it holds only operational working memory ("what to do, how to work, where is what").
- The Constitution is the single source of truth; no hardcoded persona strings remain in the prompt path.
- Changes propagate without recreating agents (live-read + cache invalidation).

## 2. Background — Current State (Audit Findings)

The Constitution exists in PostgreSQL + ChromaDB and is used for **governance checks** (hard/semantic rules in `constitutional_guard.py`) and **RAG grounding** (`query_constitution` in `vector_store.py`). It is **not** used to build the live LLM system prompt.

Persona today comes from **hardcoded Ethos templates** plus hardcoded tier/provider strings:

- `backend/models/entities/agents.py`
  - `get_system_prompt()` (338–356): returns `ethos.mission_statement` + behavioral rules — pure Ethos, no Constitution.
  - `templates` dict (1273–1438): hardcoded `mission`/`core_values`/`rules`/`restrictions` per agent type.
  - `CONSTITUTION_PREAMBLE` (1268) injected into missions.
  - Fallback base prompt (350): `"You are an AI assistant operating within the Agentium governance system."`
  - `read_and_align_constitution` (388–472): writes only a ~200-char summary into `constitutional_references`; never injected into prompts.
  - Broken fallback `docs/constitution/core.md` (442–445) — file does not exist.
- `backend/services/prompt_template_manager.py`
  - `build_system_prompt()` (708–768): Ethos-derived + hardcoded tier `role_context` (770–778). Does not read `constitutional_references`.
  - `PROVIDER_TEMPLATES` (53–456): hardcoded persona leads ("You are Claude…", "expert software engineer").
  - `DEEP_THINK_HINT` / `HOST_ACCESS_HINT` / `WORKSPACE_HINT` (573–600): hardcoded behavioral instructions.
- `backend/api/routes/chat.py`
  - Persona endpoint (445–456): `head.get_system_prompt()` → Ethos-derived.
  - `_enrich_with_persona` (65–69): prepends `[Persona: …]` to the *user* message, not the system prompt.
  - Hardcoded tone instruction (519–524): "You are speaking directly to the Sovereign…"
- `backend/services/persistent_council.py` (223–266) and `backend/services/overflow_recovery.py` (164): duplicate hardcoded Head ethos.
- `voice-bridge/main.py`
  - `_load_persona()` (403–420) → `_fetch_backend_persona()` (380–400) → `GET /api/v1/chat/persona` → `head.get_system_prompt()`. Comment at line 408 falsely claims it is constitution-driven.

**Conclusion:** Editing the Constitution does **not** change any agent's or the voice bridge's persona today.

## 3. Design Principles

1. **Constitution = persona/behavior/values.** The active `Constitution` row is the only source of identity, tone, values, and behavioral boundaries.
2. **Ethos = operational working memory only.** `current_objective`, `active_plan`, `task_progress`, `reasoning_artifacts`, `lessons_learned`, `working_method`, `capabilities`, `environment_context`. No `mission_statement`/`core_values`/`behavioral_rules`/`restrictions` used as persona.
3. **Live-read + cache invalidation** is the primary propagation mechanism (covers UI edits to existing agents and voice with no recreation). Ethos alignment at creation is secondary/consistency only.
4. **Single composition path** to prevent divergence between chat, task execution, and voice.
5. **Transparency:** agents can cite which clause drove behavior; responses carry the constitution version they were built from.

## 4. Architecture

```
UI (edit Constitution) ──POST /api/v1/constitution/update──▶ writes new is_active Constitution row
                                                         └──▶ invalidate Redis + in-memory active-constitution cache

Active Constitution (Postgres, cached Redis: constitutional_guard:active_constitution)
        │
        ├─▶ build_persona_directive(constitution, tier)  [NEW central function]
        │        = preamble + persona/conduct article + sovereign_preferences(comm style)
        │          + prohibited_actions + per-tier emphasis + clause citations + version footer
        │
        ├─▶ get_system_prompt()                (chat + voice persona)
        ├─▶ build_system_prompt()              (task execution)
        └─▶ /api/v1/chat/persona  ──▶ voice-bridge persona
```

Ethos is populated at agent creation by `read_and_align_constitution`, which records **only** `constitutional_references` (article titles + version) for traceability — never persona text. At inference, Ethos contributes operational context only.

## 5. Persona Directive Composition

`build_persona_directive(constitution, tier)` returns an ordered block:

1. **Identity** — `preamble` (system identity/mission).
2. **Persona & conduct** — the dedicated `agent_persona_and_conduct` article added to the seed.
3. **Communication style** — derived from `sovereign_preferences` (user-stated tone/style) + a spoken-style adaptation rule for the voice bridge (see §6.3).
4. **Boundaries** — `prohibited_actions`.
5. **Tier emphasis** — clauses tagged `applies_to` for the agent's tier (default: all tiers). Structural `role_context` (e.g., "You are the Head of Council…") remains, but is role/authority, not persona.
6. **Clause citations** — list of in-effect article keys + titles (transparency; improvement #6).
7. **Provenance footer** — `<!-- persona built from Constitution vX.Y.Z (C000N) -->` (improvement #7).

Provider `PROVIDER_TEMPLATES` retain **formatting/instruction-style** guidance only (e.g., output format, tool-use style); all persona leads are stripped.

## 6. Components & Change Points

### 6.1 Central persona function (improvement #1)
- Add `backend/core/persona.py` with `build_persona_directive(constitution: Dict, tier: Optional[str] = None) -> str` (sync; the guard's loader is async, prompt builders are sync — read the active row directly or from Redis cache synchronously).
- Used by `get_system_prompt()`, `build_system_prompt()`, and the `/chat/persona` endpoint.

### 6.2 `backend/models/entities/agents.py`
- `get_system_prompt()` (338): return `build_persona_directive(active_constitution, self.agent_type)` + Ethos operational context; **remove** `templates` persona strings (1273), `CONSTITUTION_PREAMBLE` (1268), fallback base prompt (350).
- `read_and_align_constitution` (388): stop copying persona into Ethos; record `constitutional_references` (titles + version) only. Fix the `docs/constitution/core.md` fallback to degrade to seeded defaults (no crash).
- `templates` dict (1273): remove persona fields; keep only functional `capabilities` if desired (operational, not persona).

### 6.3 `prompt_template_manager.py`
- `build_system_prompt()` (708): inject `build_persona_directive(...)`; keep tier `role_context` (structural) but strip hardcoded persona leads from `PROVIDER_TEMPLATES` (53–456); keep `DEEP_THINK/HOST_ACCESS/WORKSPACE` hints only if they are operational (not persona) — move any persona-flavored wording out.
- Voice spoken-style adaptation: when `tier == "voice"` (or a `channel="voice"` flag), append a concise/spoken adaptation rule derived from the Constitution's communication-style principle (no markdown, short sentences, conversational). (improvement #3)

### 6.4 `initialization_service.py` `create_default_constitution` (1098)
- Add a dedicated `agent_persona_and_conduct` article to the seed (the obvious editable clause for the acceptance test).
- Add a `communication_style` entry to `sovereign_preferences` defaults.
- (Optional) Tag a few clauses with `applies_to` tier lists to demonstrate tier emphasis (improvement #5).

### 6.5 Cache invalidation (critical for UI-edit workflow)
- `main.py:update_constitution` (819): after writing the new active row, **invalidate** Redis key `constitutional_guard:active_constitution` and the guard's in-memory cache (`_constitution_cache` / `_cache_timestamp`).
- Amendment ratification path (`amendment_service.conclude_voting` → writes active Constitution): same invalidation.
- Add a helper `invalidate_active_constitution_cache(redis)` in `constitutional_guard.py` and call it from both write paths.

### 6.6 `chat.py` + `voice-bridge/main.py`
- Persona endpoint (445): already calls `head.get_system_prompt()` → now Constitution-aware. Place persona in the **system prompt** (not prepended to user message) in `_enrich_with_persona` (65).
- Remove hardcoded tone instruction (519–524) ("You are speaking directly to the Sovereign…") — replaced by Constitution persona.
- `voice-bridge/main.py`: fix the misleading comment at 408; no structural change needed beyond endpoint being Constitution-aware.

### 6.7 Duplicate hardcoded ethos (improvement #2 purge)
- `persistent_council.py` (223–266) and `overflow_recovery.py` (164): remove redundant hardcoded ethos; route through `build_persona_directive` / Constitution-derived path.

### 6.8 UI persona preview (improvement #4)
- Add `POST /api/v1/constitution/preview-persona` (or extend the update request with a `dry_run` flag) that builds the directive from the **draft** constitution and returns the rendered system prompt, so the user sees the effect before saving. Frontend shows it on the Constitution editor.

## 7. Data Flow

1. User edits Constitution in UI → `POST /api/v1/constitution/update` writes new `is_active` row (version bumped) + invalidates cache.
2. Next agent inference: `get_system_prompt()` / `build_system_prompt()` live-read active Constitution (Redis cache miss → DB) → `build_persona_directive` → new persona in prompt.
3. Voice: `/chat/persona` → `head.get_system_prompt()` (Constitution-aware) → voice bridge speaks with new persona.
4. Fresh agent creation: `read_and_align_constitution` records references; inference still live-reads the Constitution, so persona is always current.

## 8. Error Handling

- If Constitution unavailable (DB down, or `TESTING=true` where seed is skipped): fall back to last-known Redis value, then to a minimal safe constant (`FALLBACK_PERSONA`). Never crash.
- `build_persona_directive` tolerates missing fields (empty article, null preferences).
- Cache invalidation failures are non-fatal (next TTL refresh recovers).

## 9. Testing (satisfies acceptance criteria)

Pytest (`backend/tests/`):
1. Seed Constitution with a unique persona clause (e.g., a marker phrase).
2. Assert fresh agent `get_system_prompt()` and `build_system_prompt()` contain the phrase.
3. Assert `/chat/persona` (voice path) contains the phrase.
4. Call `update_constitution` to change the clause; assert cache invalidated.
5. Assert a **new** fresh agent + voice persona now show the **new** phrase and not the old — no code change.
6. Unit-test `build_persona_directive` for tier filtering, citation list, and provenance footer.
7. Test `invalidate_active_constitution_cache` is invoked on update + ratification.

## 10. Out of Scope

- RLAIF / fine-tuning / training on the Constitution (Anthropic-style). The existing Critics already provide constitution-grounded critique; optionally the Output Critic can be tightened to check responses against persona clauses, but that is a follow-up.
- Changing the Constitution data model / Alembic migration (design is migration-free by composing from existing fields).

## 11. Open Questions (resolve at implementation)

- Exact key name for the persona article in the seed (`agent_persona_and_conduct` is a placeholder).
- Whether `sovereign_preferences` is the right home for `communication_style`, or a dedicated top-level field is cleaner (migration trade-off).
- Frontend effort for the preview UI (covered by improvement #4 but may be sized separately).
