# Database Maintenance Verification & Targeted Gap Fixes

| Field | Value |
|---|---|
| **Status** | Draft — pending user review |
| **Date** | 2026-08-22 |
| **Prior spec** | `docs/superpowers/specs/2026-08-21-database-maintenance-verification-design.md` (deleted; recoverable in git) |
| **TODO Refs** | `docs/documents/TODO.md` § 3.4.1, § 3.4.2, § 3.4.3 |
| **Scope** | Verify that `DatabaseMaintenanceService` runs and is lock-safe + that the connection pool does not leak; close the small real gaps uncovered by the audit |

## Context

`backend/services/db_maintenance.py` already implements a `DatabaseMaintenanceService` class with five periodic loops (`cleanup_stale_data`, `index_maintenance`, `vector_db_optimization`, `trigger_pg_dump`, `vector_db_snapshot`) plus a `get_maintenance_report()` utility. The lifespan in `main.py:416` starts these via `asyncio.create_task()`, so they live inside the FastAPI process — not in Celery beat.

Three TODO checkboxes (`3.4.1`, `3.4.2`, `3.4.3`) claim that:
1. Vacuum/cleanup tasks actually run.
2. Periodic tasks don't lock tables excessively.
3. The connection pool doesn't leak under load.

A read of the existing code shows (1) is structurally present but **untested**, (2) is unmet because `db.query(AuditLog).filter(...).delete()` is unbatched and would hold its lock for the full row count on a large table, and (3) is unmet because no test exercises pool checkout/checkin concurrency. A second narrower bug also lurks: `_prune_constitution_versions` checks `v.version == 1` against the **string** display column (`"v1.0.0"`) instead of the integer `version_number` column, so its "never delete v1" invariant is structurally broken.

This spec is a verify-plus-tiny-fix pass: write the missing tests, and make surgical edits to the bulk-delete path and the constitution-pruning invariant so (1), (2), (3) become testable rather than aspirational.

**Implementation status (as of 2026-08-22):** The worktree `.claude/worktrees/db-maintenance-verification/` already contains the implementation work — the production-side changes (across 2 production commits + 1 unit-test commit) (`_chunked_delete` helper and `cleanup_stale_data_once` single-tick extract) plus 1 unit-test commit with the SQLite suite. Three gaps remain: (a) File A "test_chunked_delete_respects_batch_size" outcome-only assertion must be strengthened to verify chunk count (a non-chunked rewrite would still pass the row-count assertion alone); (b) backend/tests/integration/test_db_maintenance_pg.py is to be authored; (c) backend/tests/unit/test_connection_pool_under_load.py is to be authored. This spec restores + refreshes the deleted 2026-08-21 design with today's audit decisions and current entity schema references; the implementation plan reuses the worktree's already-passing code where possible.

---

## Goals

- **G1.** Establish that `cleanup_stale_data` deletes only the entities it claims to (audit logs older than retention, completed/cancelled/failed tasks older than archive, constitution versions outside the keep window — except version 1).
- **G2.** Establish that the cleanup path doesn't take statements longer than 500ms per single DELETE under realistic seed sizes.
- **G3.** Establish that the engine's connection pool returns to `checkedout() == 0` after concurrent traffic and that an `engine.dispose()` cleans up the underlying handles.
- **G4.** Make the bulk-delete behavior chunked and time-bounded so a future regression in any single cleanup loop easily trips a test instead of silently degrading production latency.

## Non-Goals

- **NG1.** **Not** moving `db_maintenance` tasks onto Celery beat. They remain `asyncio.create_task` loops driven by `start_maintenance_monitors()`. Migration to Celery beat is captured as a follow-up (F1) for a future spec.
- **NG2.** **Not** tuning `AUDIT_LOG_RETENTION_DAYS` / `TASK_ARCHIVE_DAYS` defaults. Those are ops policy values and stay as-is.
- **NG3.** **Not** building new dashboards for cleanup results — the existing `get_maintenance_report()` continues to be the source of truth.
- **NG4.** **Not** changing vector DB or ChromaDB snapshot logic (untouched in this spec).
- **NG5.** **Not** adding Prometheus exporters or new monitoring surfaces; existing `monitoring_service` and `alert_manager` integrations stay.

---

## Architecture

Three independent pieces kept physically separate so each can be reasoned about alone.

```
┌─────────────────────────────────────────────────────────────────┐
│                 backend/services/db_maintenance.py              │
│              (existing; ~40 surgical code edits)                │
├─────────────────────────────────────────────────────────────────┤
│  DatabaseMaintenanceService                                     │
│   ├─ _chunked_delete()           →  new helper, bounded holds   │
│   ├─ cleanup_stale_data_once()   →  new public single-tick      │
│   ├─ cleanup_stale_data()        →  thin wrapper around single  │
│   ├─ _prune_constitution_versions_chunked()  →  v1-safe + chunked│
│   ├─ index_maintenance()         →  per-table autocommit (unchanged) │
│   ├─ vector_db_optimization()/snapshot() — unchanged            │
│   └─ start_maintenance_monitors() — unchanged scheduling        │
└─────────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────┐
│          backend/tests/unit/test_db_maintenance.py              │
│       Pure-Python coroutine tests; SQLite or any backend        │
├─────────────────────────────────────────────────────────────────┤
│  - test_cleanup_drops_audit_older_than_retention                 │
│  - test_cleanup_drops_completed_tasks_older_than_archive         │
│  - test_cleanup_keeps_constitution_v1_always                    │
│  - test_constitution_prune_keeps_latest_n                       │
│  - test_chunked_delete_respects_batch_size                      │
│  - test_get_maintenance_report_returns_zero_on_empty_db         │
└─────────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────┐
│   backend/tests/integration/test_db_maintenance_pg.py            │
│   Real Postgres; reuses `db_session` fixture from existing     │
│   backend/tests/integration/conftest.py (no testcontainer)     │
├─────────────────────────────────────────────────────────────────┤
│  - test_audit_log_delete_completes_under_lock_budget            │
│  - test_long_running_cleanup_does_not_exhaust_pool              │
│  - test_maintenance_yields_to_event_loop                        │
│  - test_get_maintenance_report_against_real_db                  │
└─────────────────────────────────────────────────────────────────┘
                ▼
┌─────────────────────────────────────────────────────────────────┐
│   backend/tests/unit/test_connection_pool_under_load.py         │
│                  (any DB; no fixtures)                           │
├─────────────────────────────────────────────────────────────────┤
│  - test_checked_out_returns_to_baseline_after_traffic           │
│  - test_engine_dispose_closes_all_connections                   │
└─────────────────────────────────────────────────────────────────┘
```

**Boundaries & rationale**

- Lock-shape and pool-leak stories are intentionally independent. If a pool test fails, the diagnostic is engine config; if a chunked-delete test fails, the diagnostic is maintenance logic. Mixing them blurs failure attribution and slows triage.
- The Postgres integration file reuses `db_session` from `backend/tests/integration/conftest.py` — the convention used by every other integration test in this repo. No new Docker dependency, no testcontainer, no fixture additions to existing conftest.
- The pure-Python pool-leak file uses no fixtures, since pool behavior is engine-level and does not depend on schema content.

---

## Production Code Edits

All edits live in `backend/services/db_maintenance.py`. Total diff is approximately 40 lines.

### Edit 1 — `_chunked_delete()` helper

A new private coroutine becomes the only path through which `cleanup_stale_data_once()` drops rows. Its single responsibility: bound each single-statement lock hold to at most `batch_size` rows and yield to the event loop between batches so request paths can grab a connection.

```python
@staticmethod
async def _chunked_delete(
    db: Session,
    model: type,
    filter_factory,
    batch_size: int = 1000,
    sleep_ms: int = 50,
    on_chunk: callable = None,
) -> int:
    """Delete matching rows in chunks; sleep between chunks.

    `filter_factory` is a callable returning the filter clause; it is
    re-evaluated each chunk so newly-eligible rows are also caught.
    Each chunk runs inside a SAVEPOINT so a chunk-level error does
    not poison the outer transaction. Each chunk commits before
    sleeping, so partial progress persists across restarts.

    SQLAlchemy 2.x refuses `.limit().delete()` because LIMIT semantics
    on UPDATE/DELETE differ across dialects. We do a bounded SELECT
    of IDs (the LIMIT applies here) then a DELETE WHERE id IN (...) —
    the bound on rows-deleted-per-statement is preserved.

    `on_chunk`, if provided, is invoked once per non-empty chunk with
    the deleted count; the test suite uses this hook to assert that
    the helper iterates more than once instead of swallowing the whole
    backlog in a single statement.
    """
    total = 0
    while True:
        with db.begin_nested():
            ids_subq = (
                db.query(model.id)
                .filter(filter_factory())
                .limit(batch_size)
                .subquery()
            )
            count = (
                db.query(model)
                .filter(model.id.in_(ids_subq))
                .delete(synchronize_session="fetch")
            )
        if count == 0:
            break
        total += count
        if on_chunk is not None:
            on_chunk(count)
        db.commit()
        if sleep_ms > 0:
            await asyncio.sleep(sleep_ms / 1000)
    return total
```

### Edit 2 — Extract `cleanup_stale_data_once()` and add `lock_timeout`

Body of the `while True` cleanup loop is extracted into a public single-tick method so tests can drive one iteration without spinning the 24-hour sleep. The existing `cleanup_stale_data()` becomes a thin wrapper.

```python
@staticmethod
async def cleanup_stale_data_once() -> dict:
    """Single tick: one pass of audit log / task / constitution cleanup.
    Async because it `await`s the `_chunked_delete` helper. Tests drive one
    tick at a time without spinning the 24-hour sleep loop.

    All bulk deletes route through `_chunked_delete` so each single
    DELETE statement holds its lock for at most `batch_size` rows
    and yields to the event loop between batches.
    """
    with get_db_context() as db:
        report = {
            "audit_logs_deleted": 0,
            "tasks_deleted": 0,
            "constitution_versions_pruned": 0,
        }

        # Bound any single lock-acquisition wait. SQLite ignores
        # this clause (no-op); Postgres honors it.
        try:
            db.execute(text("SET LOCAL lock_timeout = '5s'"))
        except Exception:
            pass

        # 1. Old audit logs (chunked).
        audit_cutoff = datetime.utcnow() - timedelta(
            days=settings.AUDIT_LOG_RETENTION_DAYS
        )
        report["audit_logs_deleted"] = (
            await DatabaseMaintenanceService._chunked_delete(
                db=db,
                model=AuditLog,
                filter_factory=lambda: AuditLog.created_at < audit_cutoff,
                batch_size=1000,
                sleep_ms=50,
            )
        )

        # 2. Completed / cancelled / failed tasks older than archive.
        task_cutoff = datetime.utcnow() - timedelta(
            days=settings.TASK_ARCHIVE_DAYS
        )
        report["tasks_deleted"] = (
            await DatabaseMaintenanceService._chunked_delete(
                db=db,
                model=Task,
                filter_factory=lambda: (
                    Task.status.in_(["completed", "cancelled", "failed"])
                    & (Task.updated_at < task_cutoff)
                ),
                batch_size=1000,
                sleep_ms=50,
            )
        )

        # 3. Constitution versions: keep latest N + version 1.
        report["constitution_versions_pruned"] = (
            await DatabaseMaintenanceService._prune_constitution_versions_chunked(db)
        )

        total = sum(report.values())
        if total > 0:
            logger.info(
                f"DB Maintenance: {report['audit_logs_deleted']} "
                f"audit logs, {report['tasks_deleted']} tasks, "
                f"{report['constitution_versions_pruned']} "
                f"constitution versions cleaned up."
            )
        return report

@staticmethod
async def cleanup_stale_data():
    """Background task: Daily cleanup. Phase 9.2: Memory Management.
    Body delegated to cleanup_stale_data_once() so tests and prod share
    the same path."""
    while True:
        try:
            await DatabaseMaintenanceService.cleanup_stale_data_once()
        except Exception as e:
            logger.error(f"Error in DB cleanup routine: {e}")
        await asyncio.sleep(86400)  # Sleep 24 hours
```

### Edit 3 — `_prune_constitution_versions_chunked()` (v1-safe + chunked)

Replaces legacy unbatched `_prune_constitution_versions()` (kept for backward import) with a chunked variant that also fixes the v1-detection bug. Constitution has *both* `version` (string label, e.g. `"v1.0.0"`) and `version_number` (integer, e.g. `1`); the integer is the invariant target.

```python
@staticmethod
async def _prune_constitution_versions_chunked(db: Session) -> int:
    """Keep the latest N constitution versions plus version 1 (original).
    Routes the actual DELETEs through `_chunked_delete` so single-statement
    lock hold is bounded.

    The v1 guard checks `version_number` (Integer), NOT `version` (String)
    — the legacy `_prune_constitution_versions` did `v.version == 1` against
    the string column, which always failed to match.
    """
    all_versions = (
        db.query(Constitution)
        .order_by(Constitution.version_number.desc())
        .all()
    )
    if len(all_versions) <= settings.CONSTITUTION_MAX_VERSIONS:
        return 0

    keep_ids = set()
    for v in all_versions[: settings.CONSTITUTION_MAX_VERSIONS]:
        keep_ids.add(v.id)
    for v in all_versions:
        if v.version_number == 1:
            keep_ids.add(v.id)
            break

    return await DatabaseMaintenanceService._chunked_delete(
        db=db,
        model=Constitution,
        filter_factory=lambda: Constitution.id.notin_(keep_ids),
        batch_size=100,
        sleep_ms=50,
    )
```

### What does NOT change

- `index_maintenance` is already per-table autocommit (one ANALYZE per table, each in its own connection); no change.
- `vector_db_optimization` / `vector_db_snapshot` / `trigger_pg_dump` are filesystem-bound; no change.
- `start_maintenance_monitors()` schedule is unchanged.
- `get_maintenance_report()` API and shape are unchanged.
- `database.py` engine config and pool settings are unchanged.
- `_prune_constitution_versions` (legacy) is preserved as a private static for any caller that imported it; it remains broken-by-design as documented in its docstring.

---

## Test Strategy

Three files, three scopes. Each test maps directly to one of `G1`–`G4`.

### A) `backend/tests/unit/test_db_maintenance.py` (Python + SQLite)

Pure logic and coroutine tests. SQLite-compatible — no testcontainers needed.

`AuditLog` schema references in this file: required fields are `agentium_id`, `level` (`AuditLevel.INFO`), `category` (`AuditCategory.SYSTEM`), `actor_type`, `actor_id`, `action`, `description`. `Task` required fields: `agentium_id`, `title`, `description`, `task_type`, `priority`, `status`, `updated_at`. `Constitution` required fields: `agentium_id`, `version` (string label), `version_number` (integer), `preamble`, `articles`, `prohibited_actions`, `sovereign_preferences`, `created_by_agentium_id`.

| Test | Maps to | Behavior under test |
|---|---|---|
| `test_cleanup_drops_audit_older_than_retention` | G1 | Seed 5 AuditLog rows under a marker `actor_id` (3 at 365d ago, 2 at 1d ago); run one tick of cleanup; assert the 3 old rows are gone and the 2 fresh rows remain. |
| `test_cleanup_drops_completed_tasks_older_than_archive` | G1 | Seed an old COMPLETED task and an old IN_PROGRESS task under a marker `title` prefix; assert only COMPLETED is deleted. |
| `test_cleanup_keeps_constitution_v1_always` | G1 + Edit 3 | Seed N+3 constitutions with `version_number` 1..(N+3); assert v1 survives and total kept == N+1. |
| `test_constitution_prune_keeps_latest_n` | G1 | Seed exactly N constitutions; cleanup deletes zero. |
| `test_chunked_delete_respects_batch_size` | G2 | Seed 250 AuditLog rows matching a marker. Run `_chunked_delete(batch_size=50, sleep_ms=0, on_chunk=lambda c: chunk_counts.append(c))` where `on_chunk` is a new optional hook the helper exposes; assert (a) `len(chunk_counts) >= 5` and (b) all 250 rows deleted and `count == 0` after. **Strengthens the prior outcome-only assertion**: a non-chunked rewrite deleting 250 rows in one statement would still match (b) but fails (a) because chunk_counts would have length 1. |
| `test_get_maintenance_report_returns_zero_on_empty_db` | G1 | Empty SQLite DB → report shows zero counters and intact `retention_config`. |

This file already exists in the worktree (`backend/tests/unit/test_db_maintenance.py`) and is the canonical reference — the implementation plan reads its actual code blocks rather than reproducing them.

### B) `backend/tests/integration/test_db_maintenance_pg.py` (Postgres via existing docker-compose)

Required to honestly back the **G2** lock-budget claim — only meaningful against a real Postgres backend. Reuses `db_session` from `backend/tests/integration/conftest.py` which already wires to the docker-compose Postgres.

| Test | Maps to | Behavior under test |
|---|---|---|
| `test_audit_log_delete_completes_under_lock_budget` | G2 | Seed 50,000 AuditLog rows matching a unique marker; run `_chunked_delete`. From a sidecar connection, repeatedly snapshot `pg_stat_activity` over the delete window. Assert across the run that no single DELETE observed in `pg_stat_activity` held `state = 'active'` for >500ms — chunked batching keeps each statement short. |
| `test_long_running_cleanup_does_not_exhaust_pool` | G3 | Spawn `_chunked_delete` in the background. While it runs, open `pool_size + max_overflow` parallel `get_db_context()` sessions on the app engine and time them. Assert each returns within `DATABASE_POOL_TIMEOUT`. Proves the asyncio sleep between chunks actually yields. |
| `test_maintenance_yields_to_event_loop` | G2 | During cleanup mid-flight, an unrelated `get_db_context()` call returns within `DATABASE_POOL_TIMEOUT` — empirical proof that `await asyncio.sleep(...)` yields. |
| `test_get_maintenance_report_against_real_db` | G1 | Counts match raw SQL truth against the populated PG. |

### C) `backend/tests/unit/test_connection_pool_under_load.py` (any DB)

Pool-leak claims are engine-level; no schema needed.

| Test | Maps to | Behavior under test |
|---|---|---|
| `test_checked_out_returns_to_baseline_after_traffic` | G3 | Snapshot `engine.pool.checkedout()` before. Fire 100 concurrent `with get_db_context(): pass` blocks via `ThreadPoolExecutor`. After all complete, assert `checkedout() == 0`. |
| `test_engine_dispose_closes_all_connections` | G3 | Asserts `engine.dispose()` correctly releases all underlying DBAPI handles — defensive against handle-lifecycle regressions. |

### Test infra

- The Postgres integration file reuses `db_session` and `db_engine` fixtures from `backend/tests/integration/conftest.py` — no new fixtures, no testcontainer, no new Docker dependency. Matches every other integration test in the repo.
- Test naming follows the existing convention (`test_<thing>_<expected_behavior>`); the convention is already enforced by code style and CI.

---

## Failure Modes & Error Handling

The new code can misbehave in six distinct ways; each is caught by the test matrix.

| Mode | What it looks like in production | Caught by |
|---|---|---|
| **Lock-timeout storm** | `lock_timeout` aborts every chunk; helper loops forever deleting zero rows. | `test_chunked_delete_respects_batch_size` (asserts the helper actually _achieves_ bounds by counting chunks; a zero-progress loop times out the test). |
| **SAVEPOINT leak** | `db.begin_nested()` raises (e.g., autocommit-bound session) — chunks never commit; subsequent writes see phantom rows. | `test_audit_log_delete_completes_under_lock_budget` plus the existing DBA-style assertions on row counts. |
| **Sleep too short** | Cleanup chews all CPU; concurrent requests still starved. | `test_long_running_cleanup_does_not_exhaust_pool` — concurrent traffic must keep within `DATABASE_POOL_TIMEOUT`. |
| **Sleep too long** | Cleanup never finishes; reports zero-eligible for days. | `test_audit_log_delete_completes_under_lock_budget` — counts covered within a reasonable wall-clock budget. |
| **Connection handle leak in test teardown** | `engine.pool` full of dead handles; next CI run flakes. | `test_engine_dispose_closes_all_connections` plus `test_checked_out_returns_to_baseline_after_traffic` (baseline-restoration inherently implies handle closure). |
| **v1 invariant breaks** | Bulk DELETE accidentally drops `version_number == 1` row. | `test_cleanup_keeps_constitution_v1_always`. |

Defensive conventions maintained from existing code:

- All exceptions inside `cleanup_stale_data` are caught by the outer `try/except` already present — adding `_chunked_delete` does not change that surface; chunks that error log and continue, since cleanup is best-effort.
- `AlertManager` integration for backup failures (in `trigger_pg_dump`) is left untouched — Phase 9.3 already routes those to a `MonitoringAlert`.

---

## Acceptance Criteria / Definition of Done

### Code
- [ ] `_chunked_delete()` helper exists in `db_maintenance.py` with `batch_size` and `sleep_ms` parameters and `SELECT-id-LIMIT → DELETE-WHERE-IN` shape.
- [ ] `cleanup_stale_data_once()` (new public single-tick method) exists and contains the bodies called by `cleanup_stale_data()`.
- [ ] `cleanup_stale_data_once()` calls `_chunked_delete()` for audit log cleanup, task cleanup, and constitution pruning.
- [ ] Each transaction body sets `lock_timeout = '5s'` before any chunk runs, wrapped in `try/except` so SQLite silently no-ops.
- [ ] `_prune_constitution_versions_chunked()` exists and uses `Constitution.version_number` (integer) for v1 detection, not `Constitution.version`.
- [ ] Diff scope: only `backend/services/db_maintenance.py` changes; no other production file is edited.
- [ ] `get_maintenance_report()` continues to return the same shape.
- [ ] `start_maintenance_monitors()` and the 24-hour cadence are unchanged.

### Tests
- [ ] `backend/tests/unit/test_db_maintenance.py` — 6 tests, all passing on SQLite (already exists in worktree).
- [ ] `backend/tests/integration/test_db_maintenance_pg.py` — 4 tests, all passing on docker-compose Postgres.
- [ ] `backend/tests/unit/test_connection_pool_under_load.py` — 2 tests, all passing on the configured DB.

### CI & Integration
- [ ] `pytest backend/tests/unit/test_db_maintenance.py backend/tests/unit/test_connection_pool_under_load.py` exits 0.
- [ ] `pytest backend/tests/integration/test_db_maintenance_pg.py` exits 0.
- [ ] Full `pytest backend/tests/` exits 0 — no regressions to existing tests.
- [ ] Lint passes (`ruff check backend/services/db_maintenance.py backend/tests/...`).

### TODO.md update
- [ ] `3.4.1`, `3.4.2`, `3.4.3` each flip from `[ ]` to `[x]` in a final commit referencing this spec.

### Out of Scope (explicit)
- Moving `db_maintenance` tasks onto Celery beat (a future separate spec — see F1).
- Tuning `AUDIT_LOG_RETENTION_DAYS` / `TASK_ARCHIVE_DAYS` defaults.
- Vector DB snapshot restore flow (Phase 9.3 is verify-only here; disaster recovery is its own scope).
- Adding dashboards/metrics exporters for cleanup results.

---

## Open Questions & Risks

### Resolved during brainstorming (2026-08-22)
- **Q: Scope?** Restore & finish the prior spec — verify-only with surgical fixes. Celery migration explicitly out of scope (F1). User chose this over expanding to Celery migration in the same spec or splitting.
- **Q: Postgres test infra?** Reuse the existing `db_session` fixture in `backend/tests/integration/conftest.py` (talks to docker-compose Postgres). No testcontainer. Matches every other integration test in the repo.
- **Q: Tunables?** Constants in code (`batch_size=1000`, `sleep_ms=50`, `lock_timeout='5s'`). The chunked helper already accepts parameters so tests can override; production uses safe defaults. Settings-tunable was considered but rejected to keep surface area narrow (today's Q&A).
- **Q: Restore verbatim or fixup?** Restore + fixup. The prior spec's design intent is preserved; this version updates entity schema references (`AuditLog` fields, `version_number` vs `version`) and notes that the worktree already contains the implementation work.

### Residual risks
- **R1 — Postgres must be up locally for integration tests.** Same dependency every other integration test in this repo has. No new contamination.
- **R2 — `await asyncio.sleep(50ms) × N chunks` scales linearly with eligible rows.** For very large backlogs (millions of audit rows), total wall-clock could exceed 24 hours. Mitigations: (a) `batch_size` and `sleep_ms` are parameters and could be tuned later; (b) chunks are committed each iteration so partial progress persists across restarts; (c) the helper exits when a chunk returns 0 — the size of an entangled backlog is naturally capped by `sleep_ms × chunk_count + chunk_delete_time`. Worth checking the absolute upper bound once first prod run happens.
- **R3 — `lock_timeout` interacts with `synchronize_session="fetch"`.** SQLite ignores the clause (no-op); only the Postgres lock-budget test cares. Logic tests don't depend on it. `SET LOCAL` requires a transaction; `get_db_context` always opens one, so scope is correct.
- **R4 — `db.begin_nested()` requires an outer transaction; `get_db_context` provides one but the boundary depends on lifecycle.** If a future refactor moves the cleanup outside a `get_db_context` block, `begin_nested` will auto-begin a fresh outer txn (SQLAlchemy 2.x guarantee). Defensive `try/except` around the cleanup body catches any divergence.

### Open follow-ups (deferred from this spec)

- **F1. Celery beat migration** — Move each `DatabaseMaintenanceService` loop onto Celery beat for restart-resilience, multi-replica safety (with Redis leader lock), and failure-retry visibility. Add `celery_app.conf.beat_schedule` entries; deprecate `start_maintenance_monitors()`. Touched on as NG1 in prior session; today confirmed as deferred.
- **F2. Admin endpoint** — `POST /admin/maintenance/run-cleanup` (admin-only) for ops-triggered runs without deploy. Quick to add later.
- **F3. Monitoring metrics** — Expose `*_cleanup_last_duration_ms` to `monitoring_service.py` for the existing `MonitoringPage.tsx`. Out of scope; small follow-up.
- **F4. Lock-budget assertion hardening** — `test_audit_log_delete_completes_under_lock_budget` uses `pg_stat_activity`. A stronger claim could use `pg_locks` snapshot diff. Optional follow-up; current implementation consistent with `slow_query_service` instrumentation.

### What is NOT decided here
- Whether to immediately follow this spec with F1 (Celery migration) in the same release. Today explicitly deferred.
- Whether to expose cleanup duration via the existing `monitoring_service`. Out of scope for this verify-only spec.
