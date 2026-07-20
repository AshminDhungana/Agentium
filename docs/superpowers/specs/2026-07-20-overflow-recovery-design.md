# Design: Head-of-Council Overflow Handling (Task 7.1)

**Date:** 2026-07-20
**Status:** Approved (design), implementation in progress

## Problem
Only one Head (`00001`) is active at a time. If all agent-ID slots for a tier
(notably Task Agents `3-6xxxx`) are exhausted, `_generate_next_id`
(`backend/services/reincarnation_service.py`) raises `ValueError` with no
recovery path. New agents cannot be spawned.

Key finding: `_generate_next_id` counts **every** row sharing a prefix,
including terminated agents (`is_active == False`). Normal
`ReincarnationService.liquidate_agent` only *archives* (sets `is_active=False`),
so it does **not** free ID slots. The overflow recovery must therefore
hard-reclaim freed rows after a safe liquidation, scoped only to this flow.

## Decisions (approved)
- **Temporary Head form:** In-DB `0xxxx` agent (e.g. `00002`) using the
  otherwise-empty Head prefix range. Runs the idle review, then self-terminates.
- **Trigger:** Reactive (catch ID-pool exhaustion `ValueError` in spawn wrappers)
  + proactive (free task slots ≤ threshold) via
  `OverflowRecoveryService.maybe_trigger_overflow_review`.
- **Pause scope:** Gate new Task-Agent spawns **and** `dispatch_task` behind a
  Redis flag `overflow_review:in_progress`. Lead/Council spawns remain allowed
  so the review act can proceed.

## Components
### New module `backend/services/overflow_recovery.py`
- `class OverflowRecoveryService` (static methods):
  - `capacity_free_slots(db) -> Dict[str, int]` — free slots per tier from
    `ID_RANGES` minus distinct used IDs.
  - `is_review_in_progress() / set_review_in_progress() / clear_review_in_progress()`
    — Redis-backed flag with TTL + lock for idempotency.
  - `maybe_trigger_overflow_review(db, reason)` — if not already in progress,
    spawn temp head, run review, then clear flag.
  - `_spawn_overflow_review_head(db)` — create `HeadOfCouncil` `0xxxx` row with
    `is_temporary_overflow_head=True` + minimal `Ethos`.
  - `_sync_detect_idle(db)` — sync mirror of idle detection (non-persistent,
    idle > threshold, excludes temp head).
  - `run_review(db, temp_head)` — liquidate idle agents with no active tasks via
    `reincarnate...liquidate_agent`, then **hard-reclaim** each row to free the
    slot, build a report, store report (Redis + AuditLog), self-liquidate +
    delete the temp head, clear flag.
- `class CapacityRecoveryInProgress(Exception)` — raised by gated spawn paths.

### Model change
- `Agent.is_temporary_overflow_head = Column(Boolean, default=False, index=True)`
  (`backend/models/entities/agents.py`). Used to exclude the temp head from
  idle/governance loops and to scope reclamation.

### Wiring
- `ReincarnationService.spawn_task_agent` / `spawn_lead_agent`: at entry, raise
  `CapacityRecoveryInProgress` if review in progress; wrap
  `generate_id_with_retry` to catch `ValueError`, call
  `maybe_trigger_overflow_review`, then re-raise. Proactive check via
  `capacity_free_slots` inside `maybe_trigger_overflow_review`.
- `governance_tool.dispatch_task` (async): return
  `_result(False, error="capacity recovery in progress")` when flag set.
- New endpoint `GET /api/v1/governance/overflow/status` (lifecycle_routes) returns
  flag + last report.

### Alembic
- New revision adding `agents.is_temporary_overflow_head`.

## Error handling & safety
- Idempotent: Redis lock + TTL ensures a single review; if temp head dies, TTL
  clears the flag and a later spawn failure retries.
- Never liquidates `00001`, persistent agents, agents with active tasks, or the
  temp head itself until the end. Temp head excluded from normal idle/governance
  loops via the flag.
- Hard-reclaim only deletes rows already safely liquidated (children reassigned,
  tasks cancelled/reassigned by `liquidate_agent`).

## Testing (acceptance)
- `tests/unit/test_overflow_recovery.py`:
  - `fill_task_slots(db, n)` helper; simulated full-capacity (mock
    `_generate_next_id` to raise `ValueError`) triggers review flow.
  - Idle agents correctly identified; safe ones reclaimed, slots freed;
    `generate_id_with_retry("task", db)` succeeds afterward.
  - Temp head confirmed terminated (row absent) and flag cleared.
