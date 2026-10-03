# Learning Impact Dashboard (TODO 12.9) — Design

> **Date**: 2026-10-03
> **Scope**: Verify and fix the Learning Impact Dashboard data flow — `LearningImpactDashboard.tsx` (12.9.1) fed by `autonomous_learning.py`-derived data (12.9.2).
> **Status**: Approved design (sections approved by user 2026-10-03)

## Problem

The dashboard renders, but its data is largely fabricated:

- `GET /api/v1/improvements/impact` reads Redis hash `agentium:learning:impact` with **hardcoded fallbacks** (`2.1` / `4` / `12`) — nothing ever writes `success_rate_delta` or `tools_generated`, so those two KPIs always show fake defaults. The `history` array is six fixed 2023 dates. Errors return HTTP 200 with `{"error": ...}`.
- `GET /api/v1/improvements/patterns` returns **two canned strings** — it never touches the ChromaDB `task_patterns` collection where `autonomous_learning.py` actually stores extracted best practices and anti-patterns.
- `POST /api/v1/improvements/consolidate` is a **no-op stub** returning `{"status": "started"}`.
- No route has an auth dependency.
- The frontend declares a `history` field but never renders it.
- No unit test suite for the page's data flow (a11y contrast test exists with mocked API).

Phase 13's own contract (`backend/tests/integration/test_phase13_success_criteria.py:392-408`) requires `success_rate_delta` to be **computed from historical task completion data** with the Redis hash as backing store — the current code violates it.

## Working data sources (verified)

| Source | What it provides |
|---|---|
| `autonomous_learning.py` `analyze_outcomes()` | Runs post-task-completion (`task_executor.py:195-202`); extracts best practices/anti-patterns from CritiqueReviews into ChromaDB `task_patterns` with metadata `{type, source_task_ids, confidence, extracted_at, decay_score, last_validated_at}` |
| `Task` model (COMPLETED/FAILED, `created_at`, `completed_at`) | Success rates per 7-day window |
| Redis `agentium:learning:impact` → `anti_patterns_warned` | Real counter, incremented on anti-pattern warning (`task_executor.py:328`) |
| `ToolStaging` rows | Count of auto-generated tools (`create_from_pattern()` stages one row per generated tool) |
| `decay_outdated_learnings()` / `share_learnings_across_agents()` | Real consolidation actions |

## Design (Approach A — route-level compute)

All truth is computed at request time in `improvements.py`. The Redis hash becomes a best-effort write-back audit cache, not a read source. Nothing in the task-execution hot path changes.

### Backend — `backend/api/routes/improvements.py` (rewritten)

- **Auth**: `current_user: dict = Depends(get_current_user)` (from `backend.core.auth`) on all three routes, matching `scaling.py`.
- **`GET /impact`**:
  - `success_rate_delta` = success rate of tasks created in the current 7-day window minus the prior 7-day window, where success rate = COMPLETED / (COMPLETED + FAILED) among active tasks. **0.0 when either window has no completed-or-failed tasks** (no basis for comparison). Rounded to 1 decimal.
  - `tools_generated` = count of `ToolStaging` rows.
  - `anti_patterns_warned` = Redis `hget` on `agentium:learning:impact`, default 0 (no fabricated fallback).
  - `history` = 7 daily points `{date, success_rate}` computed from Task outcomes; days with no completed-or-failed tasks get rate 0.
  - Best-effort write-back of all four values into the Redis hash (Redis down → skip silently; DB truth still returned).
  - Unexpected failure → raise `InternalServerError` (no `{"error": ...}` with HTTP 200).
- **`GET /patterns`**: query ChromaDB `task_patterns` collection (via `backend.core.vector_store.get_vector_store()`), map documents → `{id, type, content, confidence}` (`id` = doc id, `type` = metadata type, `content` = document text, `confidence` = metadata confidence), return the ~20 most recent. ChromaDB failure → raise `InternalServerError` (required dependency per §1.2).
- **`POST /consolidate`**: inline run of `analyze_outcomes` + `decay_outdated_learnings` + `share_learnings_across_agents` on a fresh DB session. Returns a real summary: `{status, processed, best_practices, anti_patterns, decayed, pruned, shared, ...}` (each sub-result merged; per-function errors reported in the payload rather than failing the whole request).
- Response models: replace `SuccessResponseExample`/`ErrorResponseExample` placeholders with accurate responses metadata.

### Frontend — `frontend/src/pages/LearningImpactDashboard.tsx`

- Add a Recharts trend chart (daily success rate, last 7 days) associated with the "Success Rate Delta (7d)" card. Chart code follows the dataviz skill at implementation time.
- Everything else unchanged (KPI cards, patterns list, refresh + consolidation buttons, empty states, loading spinner).

### Error handling summary

| Route | Failure mode | Behavior |
|---|---|---|
| `/impact` | Redis down | Return DB truth, skip write-back |
| `/impact` | DB/compute error | 500 `InternalServerError` |
| `/patterns` | ChromaDB down/error | 500 `InternalServerError` |
| `/consolidate` | One function fails | Report per-function error in payload, still return 200 with the rest |

## Testing & Verification

- **Backend** — `backend/tests/api/test_improvements_routes.py` (new; pattern from `test_scaling_routes.py`):
  - 401 unauthenticated on all three routes.
  - `/impact` schema: all four fields, correct types.
  - `success_rate_delta` = 0.0 when either window empty; correct delta when both windows seeded with completed/failed tasks.
  - Redis hash written back with computed values (no fabricated defaults).
  - `/patterns`: mapped ChromaDB rows; empty collection → empty list; ChromaDB failure → 500.
  - `/consolidate`: returns real summary; consolidation functions invoked (mocked).
- **Frontend** — `frontend/src/pages/__tests__/LearningImpactDashboard.test.tsx` (new; 12.8 pattern):
  - Heading render, 3 KPI cards with values from API, patterns list, trend chart render, refresh refetch, consolidation button interaction + loading state, empty state, error toast on failure.
- **a11y**: existing `LearningImpactDashboard.a11y.browser.test.tsx` stays (update mock for the chart if needed); light + dark pass.
- **Gates**: `npx tsc --noEmit` clean (0 errors); `npm run build` green.
- **TODO.md**: mark 12.9.1 and 12.9.2 `[x]` with notes documenting the phantom-data fixes.

## Decisions made with the user

1. **Trigger Consolidation** → full inline consolidation (all three functions), returns real summary.
2. **`history` field** → render a real trend chart (not drop).
3. **Verification scope** → 12.8 pattern (unit tests + API tests + tsc + build; a11y refresh), no live-stack smoke.
