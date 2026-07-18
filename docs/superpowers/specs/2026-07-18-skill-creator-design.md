# Skill Creator Tool — Design

**Date:** 2026-07-18
**Status:** Approved (design)
**Topic:** `skill_creator` — a runtime agent tool that lets Head/Council agents author and persist new Skills (`SKILL.md`) that are indexed into ChromaDB.

## 1. Goal

Add a `skill_creator` agent tool (the skill-authoring counterpart to the existing
`tool_creator` tool) that lets a Head (`0xxxx`) or Council (`1xxxx`) agent
author a valid `SKILL.md` at runtime, persist it to
`backend/.agentium/skills/<name>/`, and immediately index it into the shared
ChromaDB skill collections so it is retrievable via semantic search
(`skill_manager.search_skills`).

The resulting `SKILL.md` must pass `parse_skill_file` validation (correct YAML
frontmatter enums, 50–300 char description, `## Steps` + `## Validation`
sections), and a subsequent `skill_manager.search_skills` call must retrieve it.

## 2. Scope (YAGNI)

In scope:
- A single new tool `skill_creator` with `create` + `help` actions.
- Authorized for Head + Council tiers only.
- Structured-field input contract.
- Write `SKILL.md` to disk + build `SkillSchema` + upsert into ChromaDB/Postgres.
- Auto-verify (no Council vote gate).
- One unit test module.

Out of scope:
- Council vote / democratic approval workflow for skills (the tool auto-verifies).
- Letting Task/Lead/Critic tiers author skills.
- Editing/deprecating existing skills (handled by `skill_manager` directly).
- A web UI for skill authoring.

## 3. Components

### 3.1 New module: `backend/tools/skill_creator_tool.py`
Mirrors `backend/tools/tool_creator_tool.py`:
- `ALLOWED_TIERS = {"0", "1"}`, `ALLOWED_TIER_IDS = ["0xxxx", "1xxxx"]`.
- `skill_creator_tool` singleton instance with `execute(action="help", **kwargs)` dispatch.
- `help` returns usage text (including the `SKILL.md` path reference).
- `create` runs the flow in §4.
- All exceptions are caught and returned as `{"success": False, "error": str}` so
  the agent loop never crashes.

### 3.2 Registration: `backend/core/tool_registry.py::_initialize_tools`
Add a registration block (alongside `tool_creator`) for `skill_creator`:
- `function=skill_creator_tool.execute`
- `parameters`: `action`, `skill_name`, `display_name`, `description`,
  `skill_type`, `domain`, `complexity`, `tags`, `steps`, `validation_criteria`,
  `prerequisites` (optional), `examples` (optional), `code_template` (optional),
  `authorized_tiers` (optional, clamped), `agent_id` (optional but expected for tier check).
- `authorized_tiers=["0xxxx", "1xxxx"]`.

### 3.3 Skill doc: `backend/.agentium/skills/skill_creator/SKILL.md`
New skill file describing the tool. Must contain `## Steps` and `## Validation`
sections and a 50–300 char description so `make seed-skills` / `parse_skill_file`
index it cleanly. Frontmatter `creator_tier: head`, enums valid.

## 4. Execution Flow (`create` action)

1. **Tier guard** — read `agent_id`; reject with
   `"skill_creator is restricted to Head (0xxxx) and Council (1xxxx) agents"` if
   `agent_id[:1]` not in `ALLOWED_TIERS`.
2. **Build a `SkillSchema`** from the structured params, normalizing:
   - `skill_name` → lowercased, spaces/dashes → underscores (`SkillSchema` validator forces this).
   - `description` → validated to **50–300 chars** (truncate or reject with actionable message if out of range).
   - `skill_type`, `domain`, `complexity` → must match `SkillSchema` enums
     (`code_generation|analysis|integration|automation|research|design|testing|
     deployment|debugging|optimization|documentation`;
     `frontend|backend|devops|data|ai|security|mobile|desktop|general|database|api`;
     `beginner|intermediate|advanced`).
   - `tags` → 1–10 items, lowercased/stripped.
   - `steps`, `validation_criteria` → ≥1 item each.
   - Set `chroma_collection="agent_skills"`, `constitution_compliant=True`,
     `success_rate=1.0`, `verification_status="verified"`,
     `creator_tier` derived from `agent_id[:1]` (`"0"`→`head`, else `council`),
     `creator_id=agent_id`, `version="1.0.0"`, `embedding_model="BAAI/bge-base-en-v1.5"`,
     `created_at`/`updated_at` = now (UTC).
   - Construction raises `pydantic.ValidationError` on bad enum/length → caught and
     returned as `success: False` with the message.
3. **Write `SKILL.md`** to `backend/.agentium/skills/<safe_name>/SKILL.md`:
   - YAML frontmatter with the same enums/fields (name, display_name, description,
     skill_type, domain, tags, complexity, creator_tier, plus optional fields).
   - Body with `## Steps` (rendered from `steps`) and `## Validation`
     (rendered from `validation_criteria`) so `parse_skill_file` succeeds on a
     later full re-seed.
   - Directory created if missing; safe_name derived from `skill_name`.
4. **Index** via `skill_manager.upsert_skill_from_markdown(schema, db=session)` inside
   a DB context (`backend.models.database.get_db_context`), which writes ChromaDB
   (chunked parent-doc) + Postgres `skills` row in one call.
5. Return `{"success": True, "skill_id": schema.skill_id, "skill_name": schema.skill_name, "indexed": True}`.

> Note: the SKILL.md is written first for durability; the `SkillSchema` is built
> directly from agent params (NOT by re-parsing the file) to avoid a redundant
> `parse_skill_file` round-trip. The two are kept consistent by construction.

## 5. Error Handling

- Unknown `action` → `{"success": False, "error": "Unknown action: <action>"}`.
- Unauthorized tier → explicit restriction message.
- Invalid enum / out-of-range description / empty steps → `pydantic` message surfaced.
- Filesystem or DB failure → caught, returned as `error`, logged.
- The tool never raises into the agent loop.

## 6. Security / Governance

- Hard clamp to `0xxxx`/`1xxxx` tiers — cannot grant to Task (`3xxxx`–`6xxxx`) or
  Critics (`7xxxx`–`9xxxx`).
- `authorized_tiers` param (if supplied) is clamped to the allowed set; it only
  affects future tool-level access metadata, not the skill's own retrievability.
- Auto-verified skills are repo-folder-equivalent trusted content; this matches the
  existing `upsert_skill_from_markdown` trust model for Head/Council-authored skills.

## 7. Testing

`backend/tests/unit/test_skill_creator.py` (mirrors `test_seed_skills.py` /
`test_vector_db_skill.py` style):
1. **Valid create** — authorized agent calls `create` with a valid structured
   payload; assert `success: True`, the `SKILL.md` file exists, and
   `parse_skill_file(Path(written_skill_md))` returns a schema without error.
2. **Retrievable** — after upsert, `skill_manager.search_skills(query=<skill description keywords>, agent_tier="head", db=...)` returns the new skill in the top results.
3. **Tier rejection** — a `3xxxx` agent_id returns `success: False` with the
   restriction error.
4. **Validation rejection** — a description shorter than 50 chars (or invalid
   enum) returns `success: False` with an actionable error.

Tests run with ChromaDB/Postgres available per the existing unit-test config
(`pytest.ini`). If an in-memory/standalone ChromaDB is required, follow the same
fixture pattern used by `test_vector_db_skill.py`.

## 8. Acceptance Criteria (from spec §3.3)

- An authorized agent can call `skill_creator`.
- The resulting `SKILL.md` passes `parse_skill_file` validation.
- A subsequent semantic search (`skill_manager.search_skills`) retrieves it.
- A unit test is shipped per §7.
