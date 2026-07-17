# Design: `ethos` Tool — Agent-Callable Working-Memory Tool

**Date:** 2026-07-17
**Status:** Approved (design)
**Approach:** A — Thin MCP-style tool wrappers over the existing `Ethos` ORM API

## Problem

Today an agent's Ethos (working memory) is managed entirely by the framework:

- **Read** — injected into the system prompt by `ModelService.generate_with_agent` and
  `KnowledgeService.get_agent_context`. The agent never explicitly reads it.
- **Write** — only at framework checkpoints: `update_ethos_with_plan` (planning),
  `post_task_ritual` (outcome/lessons), `chat_service`.
- **Compress** — only triggered by the orchestrator (after sub-steps, on stall) and
  `idle_governance`.

The underlying `Ethos` model already exposes a clean, audit-ready API
(`get_*`/`add_lesson_learned`/`set_task_progress`/`compress`/`apply_llm_compression`,
plus `increment_version()` which sets `last_updated_by_agent`), and the `agents` table
already has `ethos_action_pending` + `ethos_last_read_at` columns. The missing piece is an
**agent-invokable path**: the agent cannot drive its own working memory mid-reasoning.

Goal: give every agent (including critics) autonomy over its working memory while keeping
the constitutional guard intact.

## Approach

Expose the existing `Ethos` API as a governed tool in the same `tool_registry` the
constitution already tiers. Reuses the ORM methods verbatim — minimal new logic, full
audit trail, uniform with how other capabilities are governed.

## Architecture & Components

- New `backend/tools/ethos_tool.py` with an `EthosTool` class mirroring the existing
  `EmbeddingTool` / `DeepThinkTool` pattern: `TOOL_NAME`, `TOOL_DESCRIPTION`,
  `AUTHORIZED_TIERS`, `async execute(...)`.
- Registered in `tool_registry` so the agent calls it via
  `tool_registry.execute_tool_async("ethos", action=..., **kwargs)` — the same path as
  `read_file`, `deep_think`, etc.
- `execute` receives `agent_id` / `agent_tier` (like `user_preference_tool`) to resolve the
  agent's `ethos_id`, loads the `Ethos` ORM row, and delegates to the existing methods.
  No new persistence logic is introduced.

## Tool Surface

A single tool, `ethos`, with four actions:

| action          | maps to existing method(s)                                                  | tier          |
|-----------------|-----------------------------------------------------------------------------|---------------|
| `read`          | `get_active_plan`, `get_lessons_learned`, `get_reasoning_artifacts`, `get_constitutional_references`, `get_task_progress`, `outcome_summary`, `current_objective` | all (0–9xxxx) |
| `append`        | `add_lesson_learned`, append reasoning_artifacts, `set_task_progress`       | all (0–9xxxx) |
| `compress`      | `Agent.compress_ethos` (LLM) → fallback `Ethos.prune_obsolete_content`      | all (0–9xxxx) |
| `edit_identity` | setters for `mission_statement` / `behavioral_rules` / `restrictions` / `capabilities` | **restricted** |

`AUTHORIZED_TIERS` for `read` / `append` / `compress`:
`["0xxxx","1xxxx","2xxxx","3xxxx","4xxxx","5xxxx","6xxxx","7xxxx","8xxxx","9xxxx"]`
— i.e. **all agent tiers, including the critics** (`7xxxx` Code Critic, `8xxxx` Output
Critic, `9xxxx` Plan Critic).

## Governance for `edit_identity`

- `edit_identity` does **not** apply immediately. It stages the proposed change, sets
  `agents.ethos_action_pending = True`, and requires a Lead/Head `Ethos.verify()` before
  `is_verified` flips.
- Until verified, the agent's live `restrictions` / `behavioral_rules` are unchanged, so the
  constitutional guard cannot be silently evaded.
- This proposal-and-verify gate applies uniformly to **every** tier, including critics.
- The `agents` table already carries `ethos_action_pending` + `ethos_last_read_at`; this
  design reuses them rather than adding new columns.

## Data Flow

Agent reasoning turn → tool call → `EthosTool.execute(action=...)` →
load `Ethos` by `agent.ethos_id` → mutate via existing ORM method → `db.flush()` →
return result. Identity edits additionally set `ethos_action_pending` and write an audit
entry, pending Lead/Head verification.

## Error Handling & Audit

- Invalid `action` or missing required args → `{"success": False, "error": ...}` (matches
  `EmbeddingTool`'s contract).
- DB failure → rollback, no partial write.
- Every mutation bumps `version` and sets `last_updated_by_agent = True` (existing hooks).
- `edit_identity` writes to the audit trail and forces a constitutional-guard recheck once
  verified.

## Testing

- **Unit:** `EthosTool` maps each action to the correct ORM method; `edit_identity` sets
  `ethos_action_pending` and does **not** change live `restrictions` until verified.
- **Integration:** an agent appends a lesson mid-task, calls `compress`, and an identity
  edit remains unverified until a Lead verifies it; critics (7/8/9xxxx) can call `read` /
  `append` / `compress`.

## Out of Scope (YAGNI)

- No new storage engine; Ethos stays in Postgres.
- No prompt-only self-reporting parsing.
- No separate SDK method path bypassing `tool_registry`.
