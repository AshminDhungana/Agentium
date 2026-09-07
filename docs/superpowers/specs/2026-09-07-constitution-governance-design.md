# Constitution & Governance — Gap-Filling Design

**Date**: 2026-09-07
**Scope**: Section 7 of TODO.md — Constitution & Governance verification & missing pieces
**Approach**: Minimal Gap-Filling (Approach A)

---

## 1. Constitution API Routes

### Problem
Frontend `constitutionService` expects two endpoints that don't exist:
- `GET /api/v1/constitution` — returns active constitution
- `POST /api/v1/constitution/update` — updates constitution

### Design
Create `backend/api/routes/constitution.py` with:

| Endpoint | Method | Description | Auth |
|----------|--------|-------------|------|
| `/api/v1/constitution` | GET | Returns active constitution (version, preamble, articles, prohibited_actions, sovereign_preferences, effective_date, is_active) | Any authenticated |
| `/api/v1/constitution/update` | POST | Updates constitution (archives old, creates new version). Validates preamble not empty. | Admin/Sovereign only |
| `/api/v1/constitution/preferences` | POST | Updates sovereign_preferences only (communication_style, response_format, verbosity) | Admin/Sovereign only |
| `/api/v1/constitution/history` | GET | Returns amendment history (delegates to voting service) | Any authenticated |

### Implementation Details
- Use existing `Constitution` model methods: `get_articles_dict()`, `get_prohibited_actions_list()`, `get_sovereign_preferences()`
- On update: archive current (`is_active=False`, `archived_date=now`), insert new row with `version_number+1`, `replaces_version_id=old_id`
- Reuse `Constitution.to_dict()` for response serialization
- Register route in `main.py` during route registration phase

---

## 2. Ethos Injection Unification

### Problem
Two different system prompt builders create inconsistent LLM context:

| Location | What's Included |
|----------|-----------------|
| `Agent.get_system_prompt()` → `build_persona_directive()` | Full constitution persona (preamble, articles, prohibited, tier emphasis) + ethos operational context (objective, working_method, capabilities, environment) |
| `ModelService.generate_with_agent()` (line ~2080) | Only `ethos.mission_statement` + `behavioral_rules` |

### Design
Unify all LLM calls to use `Agent.get_system_prompt(db, channel)`:

1. Modify `ModelService.generate_with_agent(agent, ..., channel="text")` to call `agent.get_system_prompt(db, channel)`
2. Add `channel` parameter ("text" | "voice") to `generate_with_agent` and propagate through callers
3. Remove duplicate prompt-building logic from `model_provider.py` (lines 2080-2101)
4. Ensure `db` session is passed (already available in context)

### Impact
- All LLM calls receive full constitutional context
- Voice channel automatically gets `VOICE_ADAPTATION` (concise, spoken language)
- Sovereign preferences (`communication_style`, `response_format`, `verbosity`) flow through
- Ethos working memory (current_objective, active_plan, task_progress) included

### Files to Change
- `backend/services/model_provider.py` — `generate_with_agent` method
- Callers: `AgentOrchestrator`, `TaskExecutor`, any direct `ModelService` calls

---

## 3. Head of Council Veto — Current Behavior Accepted

### Decision
No special veto power needed. Current behavior is sufficient:
- Head of Council (00001) is one voter among council members
- Amendment passes with 60% quorum + 66% supermajority
- Head's vote counts equally with other council members
- No `VETOED` status or override mechanism added

### Rationale
- Simpler governance model
- Supermajority already provides strong consensus requirement
- Head can influence via proposal sponsorship and debate

---

## 4. Sovereign Preferences Flow

### Current State
- Stored in `Constitution.sovereign_preferences` (JSON)
- Genesis sets: `country_name`, `founded_at`, `council_size`, `degraded_mode`
- `persona.py:build_persona_directive()` reads `communication_style`
- Frontend `ConstitutionPage.tsx` has edit UI

### Design
1. **API**: Add `POST /api/v1/constitution/preferences` in new constitution routes
2. **Schema Validation**: Accept only known keys:
   - `communication_style` (string) — e.g., "formal", "concise", "technical"
   - `response_format` (enum: "summary_first", "detailed", "bullet_points")
   - `verbosity` (enum: "concise", "normal", "verbose")
   - `country_name` (string)
3. **Persona Integration**: `build_persona_directive()` already reads these; extend to use `response_format` and `verbosity` for prompt hints
4. **Frontend**: `ConstitutionPage.tsx` already has edit form; ensure it calls new endpoint

### Preference → Prompt Mapping
| Preference | Prompt Effect |
|------------|---------------|
| `communication_style` | Added to "# Communication Style" section |
| `response_format` | Adds instruction: "Start with summary", "Use bullet points", etc. |
| `verbosity` | Adds instruction: "Be concise", "Provide detail", etc. |

---

## 5. Verification Checklist (Maps to TODO.md Section 7)

| TODO Item | Status | Implementation |
|-----------|--------|----------------|
| 7.1.1 Constitution seeded on first boot | ✅ Done | `main.py` lines 250-265, `initialization_service.py` lines 780-851 |
| 7.1.2 GET /api/v1/constitution | 🔧 **This design** | New `constitution.py` route |
| 7.1.3 ConstitutionPage.tsx displays articles | ✅ Done | Frontend implemented |
| 7.1.4 Sovereign preferences stored/applied | 🔧 **This design** | API + persona integration |
| 7.2.1 POST /api/v1/voting/proposals | ✅ Done | `voting.py` line 163 |
| 7.2.2 Council agents can vote | ✅ Done | `AmendmentService` |
| 7.2.3 60% quorum rule | ✅ Done | `QUORUM_PERCENTAGE = 60` |
| 7.2.4 Head of Council veto | ✅ **Accepted as-is** | No special veto |
| 7.2.5 Approved amendments modify constitution | ✅ Done | `_ratify_amendment` |
| 7.2.6 VotingPage.tsx displays proposals | ✅ Done | Frontend implemented |
| 7.3.1 Tier 1 guard blocks prohibited | ✅ Done | `_tier1_check` |
| 7.3.2 Tier 2 guard semantic | ✅ Done | `_tier2_check` |
| 7.3.3 Blocked actions logged | ✅ Done | `_log_decision` |
| 7.3.4 VOTE_REQUIRED triggers vote | ✅ Done | Auto-propose after 3 in 24h |
| 7.4.1 ethos_tool.py reads ethos | ✅ Done | `ethos_tool.py` |
| 7.4.2 Ethos injected into LLM prompts | 🔧 **This design** | Unify to `get_system_prompt` |
| 7.4.3 Agent behavior adapts from ethos | ✅ Partial | Ethos compression exists |
| 7.4.4 Persona guides communication | ✅ Done | `build_persona_directive` |

---

## Implementation Order

1. **Create `backend/api/routes/constitution.py`** — API routes (Sections 1, 4)
2. **Register route in `main.py`** — Add to route registration
3. **Unify ethos injection in `model_provider.py`** — Section 2
4. **Update callers to pass `channel` parameter** — Section 2
5. **Extend `persona.py` for new preferences** — Section 4
6. **Run verification tests** — Confirm all TODO items pass

---

## Testing Strategy

- **Unit**: Test constitution CRUD, preferences validation
- **Integration**: Verify `GET /api/v1/constitution` returns correct shape for frontend
- **Integration**: Verify `ModelService.generate_with_agent` includes full persona
- **E2E**: ConstitutionPage loads, edits, saves, preferences apply to agent responses
- **Regression**: Existing amendment voting still works