# Design — Section 10.4 Scheduled Tasks (Full Build + Verify)

**Date:** 2026-09-17
**Status:** Approved for spec (pending user review)
**Scope:** `docs/documents/TODO.md` §10.4 — Scheduled Tasks
**Decision:** Full build + verify, then mark 10.4.1–10.4.3 complete

## Background / Problem

TODO §10.4 presumes the Scheduled Tasks feature works and needs only verification, but the source audit established the `ScheduledTask` model is **designed but dormant**:

- No CRUD API route — the model is unreachable via HTTP.
- No dispatcher/firing loop reads `scheduled_tasks` rows; the `idx_scheduled_next_run` index is defined but never queried.
- One-time tasks unimplemented — no one-time representation; `COMPLETED` status never set by `mark_completed()`.
- `TriggerType.SCHEDULE` event triggers are defined but never evaluated by `event_processor.py`.
- `create_reminder` (`workflow_tools.py`) writes kwargs (`task_type`/`payload`/`scheduled_for`/string `status`) that do not exist on the model → always throws → degrades to log-only; reminders never persist.
- `timezone` column stored but ignored in `calculate_next_run()` (uses naive `utcnow()`).

What *does* work today (outside scheduled-task scope): the hardcoded Celery beat schedule of ~40 system jobs in `celery_app.py`, and `event_processor.py` webhook / threshold / api_poll / dependency-graph triggers.

**Consequence:** 10.4 cannot be marked "verified working" without building the missing machinery. This spec designs the full build, then the verification that proves the three checklist claims.

## Locked decisions

1. **Fire target:** When a scheduled task is due, it creates and dispatches a regular `Task` (from `task_payload`) through the hardened 10.1–10.3 pipeline (`TaskStateMachine` transitions → `TaskExecutor.execute_task_async`), reusing lifecycle/status/escalation/audit.
2. **One-time + cleanup:** Add `run_once` (Boolean) + `run_at` (DateTime) columns; on successful one-time fire mark status `COMPLETED` (retained done-record); the dispatcher never re-dispatches `COMPLETED` rows.
3. **SCHEDULE event trigger:** Implement schedule evaluation inside `event_processor.py`, keeping trigger lifecycle (circuit-breaker, cooldown, dead-letters, EventLog) intact, and factor a **shared cron-due helper** so the ScheduledTask dispatcher and the SCHEDULE evaluator use identical cron math.
4. **Dispatcher cadence:** Celery beat entry fires every 15s (matches existing repo pattern; no APScheduler).

## 1. Data model changes — `backend/models/entities/scheduled_task.py`

- **Add `run_once`**: `Boolean`, default `False`.
- **Add `run_at`**: `DateTime`, nullable — the fire time for one-time tasks.
- **Relax `cron_expression` to nullable** with validation:
  - A task is exactly one of: cron (valid `cron_expression`, `run_once=False`) or one-time (`run_at` set, `run_once=True`).
  - Reject absent/mismatched combinations.
- **Fix `calculate_next_run()`**:
  - Apply the stored `timezone` via `zoneinfo` to the croniter base (no naive `utcnow()`).
  - For one-time rows, next run = `run_at`.
- **Fix `mark_completed(success=True)`**:
  - If `run_once` → set status `COMPLETED` (retained done-record), not `ACTIVE`.
  - Else recompute `next_execution_at` from cron; set `COMPLETED` if croniter returns `None` (expression exhausted).

## 2. Dispatcher — new module `backend/services/tasks/scheduled_task_dispatcher.py`

Beat entry `scheduled-task-dispatcher`, every 15s. Per due row (`status==ACTIVE` and `next_execution_at <= now` for cron / `run_at <= now` for one-time):

1. **Claim** the row via optimistic `UPDATE … WHERE status=ACTIVE → RUNNING` (CAS guard) — prevents double-fire under multiple workers (the "fires at correct interval, exactly once" guarantee).
2. **Create a Task** from `task_payload` (`action_type`/`params` → `TaskType`/request) and dispatch through the 10.2-fixed path: `set_status(APPROVED)` → `set_status(IN_PROGRESS)` → `TaskExecutor.execute_task_async` (reuse 10.3).
3. **On success**: `mark_completed(True)` → advance cron or set `COMPLETED`.
4. **On failure**: `mark_completed(False)` → `failure_count++`; honor `max_retries`; else `COMPLETED` / `ERROR`.
5. **AuditLog** entries (`SCHEDULED_TASK` category) on dispatch and completion.

Safety: each row's dispatch runs in its own try/except; one bad payload never aborts the sweep. Failures record to `ScheduledTaskExecution` + AuditLog. Provider-exhaustion propagates as the existing distinguishable `RuntimeError` and fails cleanly (consistent with the 10.3 decision — no infinite re-queue).

## 3. Event-trigger SCHEDULE — `backend/services/event_processor.py`

- New `evaluate_schedule_triggers(db)`: iterate `EventTrigger` where `trigger_type==SCHEDULE` and `is_active`; when due → honor `fire_count`/circuit-breaker (`max_fires_per_minute`, `cooldown_seconds`), persist an `EventLog`, then `_dispatch_action` (dispatch a Task when no `target_workflow_id`; fire workflow when set).
- Beat entry `schedule-trigger-check` (registered in `celery_app.py` beat_schedule).
- Threshold / api_poll / webhook / dependency-graph paths verified working and left intact.

## 4. Shared cron helper — new module `backend/services/scheduling/cron_due.py`

Single croniter "is this expression due at time t?" implementation used by both the ScheduledTask dispatcher (§2) and the SCHEDULE trigger evaluator (§3), so the two systems cannot drift.

## 5. CRUD route — new `backend/api/routes/scheduled_tasks.py`

- Registered `/api/v1/scheduled-tasks` in `backend/main.py`, mirroring the `tasks` router + dependency-injection patterns.
- Endpoints:
  - `POST` — create cron or one-time task (validates mutual exclusion + cron syntax).
  - `GET` — list with pagination + status/owner/active filters.
  - `GET /{id}` — details.
  - `PATCH /{id}` — pause/resume/update.
  - `DELETE /{id}` — remove.
- RBAC: sovereign/admin manage any schedule; agents may create/read their own (reuse `current_user` patterns from `tasks.py`).
- This is the backend the future 10.5 TasksPage scheduled section will consume (10.5 is a separate TODO item).

## 6. Fix `create_reminder` — `backend/services/workflow_tools.py`

- Rewrite to build a **valid** `ScheduledTask` using the new columns:
  - one-off reminder → `run_once=True` + `run_at`;
  - recurring → cron + `run_once=False`.
- Remove the invalid kwargs and the always-throw → degrade-to-log fallback for valid inputs.

## 7. Error handling

- Crash-safe sweep (per-row isolation).
- Double-fire prevention via the CAS status guard.
- Timezone consistency: default UTC; apply stored tz via `zoneinfo` in all cron computation.
- Provider-exhaustion fails cleanly (distinguishable `RuntimeError` → `SCHEDULED_TASK` failure recorded).

## 8. Testing

- **Unit**:
  - Model: `run_once`/`run_at` validation, `mark_completed` → `COMPLETED` path, timezone-aware cron, cron-exhaustion → `COMPLETED`.
  - cron-due helper.
  - CAS claim guard (no double-fire).
  - Dispatcher sweep under time-freeze.
  - Circuit-breaker on SCHEDULE trigger.
- **Integration**:
  - Cron fire → `ScheduledTaskExecution` row + dispatched Task completed + `next_execution_at` advanced (freezegun).
  - One-time → dispatched + status `COMPLETED` + **not** re-dispatched.
  - SCHEDULE trigger → Task dispatched.
- **API**: POST/GET/PATCH/DELETE CRUD round-trip.
- **Regression**: `create_reminder` now yields valid persisted rows.

## Checklist mapping

| TODO item | Delivered by |
|-----------|--------------|
| 10.4.1 — Cron-style scheduled tasks fire at correct intervals | Dispatcher + cron path (§1 cap, §2) |
| 10.4.2 — One-time scheduled tasks execute and are cleaned up | `run_once` + retain `COMPLETED` (§1, §2) |
| 10.4.3 — Event-triggered tasks fire on condition match | SCHEDULE evaluator (§3) + existing threshold/api_poll/webhook paths |

## Out of scope

- Task Frontend (TODO §10.5) — separate item; this spec only builds the backend the future page will consume.
- The hardcoded ~40 Celery beat system jobs (unchanged; they already fire).
- Rewriting the event-trigger webhook/threshold/api_poll paths (already verified working).