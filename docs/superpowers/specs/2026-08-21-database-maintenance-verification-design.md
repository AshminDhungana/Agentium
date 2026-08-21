# Database Maintenance Verification & Targeted Gap Fixes

| Field | Value |
|---|---|
| **Status** | Draft — pending user review |
| **Date** | 2026-08-21 |
| **TODO Refs** | `docs/documents/TODO.md` § 3.4.1, § 3.4.2, § 3.4.3 |
| **Scope** | Verify that `DatabaseMaintenanceService` runs and is lock-safe + that the connection pool does not leak; close the small real gaps uncovered by the audit |

## Context

`backend/services/db_maintenance.py` already implements a `DatabaseMaintenanceService` class with five periodic loops (`cleanup_stale_data`, `index_maintenance`, `vector_db_optimization`, `trigger_pg_dump`, `vector_db_snapshot`) plus a `get_maintenance_report()` utility. The lifespan in `main.py:416` starts these via `asyncio.create_task()`, so they live inside the FastAPI process — not in Celery beat.

Three TODO checkboxes (`3.4.1`, `3.4.2`, `3.4.3`) claim that:
1. Vacuum/cleanup tasks actually run.
2. Periodic tasks don't lock tables excessively.
3. The connection pool doesn't leak under load.

A read of the existing code shows (1) is structurally present but **untested**, (2) is unmet because `db.query(AuditLog).filter(...).delete()` is unbatched and would hold its lock for the full row count on a large table, and (3) is unmet because no test exercises pool checkout/checkin concurrency.

This spec is a verify-plus-tiny-fix pass: write the missing tests, and make one surgical change to the bulk-delete path to ensure (2) becomes testable rather than aspirational.

---

## Goals

- **G1.** Establish that `cleanup_stale_data` deletes only the entities it claims to (audit logs older than retention, completed/cancelled/failed tasks older than archive, constitution versions outside the keep window — except version 1).
- **G2.** Establish that the cleanup path doesn't take statements longer than 500ms per single DELETE under realistic seed sizes.
- **G3.** Establish that the engine's connection pool returns to `checkedout() == 0` after concurrent traffic and that an `engine.dispose()` cleans up the underlying handles.
- **G4.** Make the bulk-delete behavior chunked and time-bounded so a future regression in any single cleanup loop easily trips a test instead of silently degrading production latency.

## Non-Goals

- NG1. **Not** moving `db_maintenance` tasks onto Celery beat. They remain `asyncio.create_task` loops driven by `start_maintenance_monitors()`.
- NG2. **Not** tuning `AUDIT_LOG_RETENTION_DAYS` / `TASK_ARCHIVE_DAYS` defaults. Those are ops policy values and stay as-is.
- NG3. **Not** building new dashboards for cleanup results — the existing `get_maintenance_report()` continues to be the source of truth.
- NG4. **Not** changing vector DB or ChromaDB snapshot logic (untouched in this spec).
- NG5. **Not** adding Prometheus exporters or new monitoring surfaces; existing `monitoring_service` and `alert_manager` integrations stay.

---

## Architecture

Three independent pieces kept physically separate so each can be reasoned about alone.

```
┌─────────────────────────────────────────────────────────────────┐
│                 backend/services/db_maintenance.py              │
│              (existing; ~2 surgical code edits)                 │
├─────────────────────────────────────────────────────────────────┤
│  DatabaseMaintenanceService                                     │
│   ├─ cleanup_stale_data()    →  chunked deletes via helper      │
│   ├─ index_maintenance()     →  per-table autocommit (unchanged)│
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
│   Real Postgres via testcontainer — slow/lock claims only       │
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
- The Postgres integration file is gated with `@pytest.mark.postgres` so SQLite-only CI runs do not require a Docker daemon.
- The pure-Python pool-leak file uses no fixtures, since pool behavior is engine-level and does not depend on schema content.

---

## Production Code Edits

Both edits live in `backend/services/db_maintenance.py`. Total diff is approximately 40 lines.

### Edit 1 — Chunked delete helper

A new private coroutine becomes the only path through which `cleanup_stale_data()` drops rows. Its single responsibility: bound each single-statement lock hold to at most `batch_size` rows and yield to the event loop between batches so request paths can grab a connection.

```python
async def _chunked_delete(
    db: Session,
    model: type,
    filter_factory,
    batch_size: int = 1000,
    sleep_ms: int = 50,
) -> int:
    """Delete matching rows in chunks; sleep between chunks.
    `filter_factory` is a callable returning the filter clause; it is
    re-evaluated each chunk so newly-eligible rows are also caught.
    """
    total = 0
    while True:
        # SAVEPONT so a chunk-level error does not poison the outer txn.
        with db.begin_nested():
            q = db.query(model).filter(filter_factory()).limit(batch_size)
            count = q.delete(synchronize_session="fetch")
        if count == 0:
            break
        total += count
        db.commit()
        await asyncio.sleep(sleep_ms / 1000)
    return total
```

Body of the `while True` cleanup loop is extracted into a public single-tick method `cleanup_stale_data_once()` so tests can drive one iteration without spinning the 24-hour sleep. The existing `cleanup_stale_data()` becomes a thin wrapper that calls `cleanup_stale_data_once()` then `await asyncio.sleep(86400)`.

The three call-sites inside `cleanup_stale_data_once()` become `_chunked_delete(...)` invocations — one for audit logs, one for completed/cancelled/failed tasks, one for constitution versions (replacing the iteration-based prune in `_prune_constitution_versions` with the same helper). The outer coroutine signature of `DatabaseMaintenanceService.cleanup_stale_data` is unchanged.

### Edit 2 — `lock_timeout` and event-loop yield

Before the cleanup transaction body opens, run:

```python
db.execute(text("SET LOCAL lock_timeout = '5s'"))
```

This bound the wait time on any contended lock acquisition to 5 seconds; if a cleanup chunk collides with concurrent writes, it bails fast and the helper's retry loop continues with whatever rows it managed to drop. Concurrent writes (e.g., audit log writes during chat) keep their latency bounded; cleanup just yields rather than blocking transactions.

### What does NOT change

- `index_maintenance` is already per-table autocommit (one ANALYZE per table, each in its own connection); no change.
- `vector_db_optimization` / `vector_db_snapshot` / `trigger_pg_dump` are filesystem-bound; no change.
- `start_maintenance_monitors()` schedule is unchanged.
- `get_maintenance_report()` API and shape are unchanged.
- `database.py` engine config and pool settings are unchanged.

---

## Test Strategy

Three files, three scopes. Each test maps directly to one of `G1`–`G4`.

### A) `backend/tests/unit/test_db_maintenance.py` (Python + SQLite)

Pure logic and coroutine tests. SQLite-compatible — no testcontainers needed.

| Test | Maps to | Behavior under test |
|---|---|---|
| `test_cleanup_drops_audit_older_than_retention` | G1 | Seed 100 audit rows at varying ages; run one tick of cleanup; assert retention-window rows are deleted and inside-window rows remain. |
| `test_cleanup_drops_completed_tasks_older_than_archive` | G1 | Seed tasks with mixed statuses/dates; assert only `status IN (completed, cancelled, failed) ∧ updated_at < cutoff` are deleted. |
| `test_cleanup_keeps_constitution_v1_always` | G1 + Edit 1 | Seed N constitutions, force N > settings threshold; assert version 1 survives even after multiple delete ticks. |
| `test_constitution_prune_keeps_latest_n` | G1 | After prune, exactly `settings.CONSTITUTION_MAX_VERSIONS + (1 if version 1 among exceeded else 0)` rows remain. |
| `test_chunked_delete_respects_batch_size` | G2 | Seed 250 rows matching a filter; run `_chunked_delete(batch_size=50)`. Assert cleanup ran ≥5 chunks (proves the lock-shape, not just the outcome). |
| `test_get_maintenance_report_returns_zero_on_empty_db` | G1 | Empty SQLite DB → report shows zero for each "eligible" counter. |

### B) `backend/tests/integration/test_db_maintenance_pg.py` (Postgres via testcontainer)

Required to honestly back the **G2** lock-budget claim — only meaningful against a real Postgres backend.

| Test | Maps to | Behavior under test |
|---|---|---|
| `test_audit_log_delete_completes_under_lock_budget` | G2 | Use `pg_stat_activity` snapshotting and a 50k-row seed. Assert no single DELETE observed in `pg_stat_activity` exceeded 500 ms of `state` = `active` while it was the victim of a lock wait — or, equivalently, time each chunk from a sidecar instrumentation. |
| `test_long_running_cleanup_does_not_exhaust_pool` | G3 | Spawn a `cleanup_stale_data` coroutine in the background. While it runs, open `pool_size + max_overflow` sessions on the app engine and time them. Assert each request returns within `DATABASE_POOL_TIMEOUT` (does not starve). |
| `test_maintenance_yields_to_event_loop` | G2 | During cleanup mid-flight, an unrelated `get_db_context()` call returns within `DATABASE_POOL_TIMEOUT`, proving `await asyncio.sleep(...)` actually yields. |
| `test_get_maintenance_report_against_real_db` | G1 | Counts match raw SQL truth. |

### C) `backend/tests/unit/test_connection_pool_under_load.py` (any DB)

Pool-leak claims are engine-level; no schema needed.

| Test | Maps to | Behavior under test |
|---|---|---|
| `test_checked_out_returns_to_baseline_after_traffic` | G3 | Snapshot `engine.pool.checkedout()` before. Fire 100 concurrent `with get_db_context()` blocks. After all complete, assert `checkedout() == 0`. |
| `test_engine_dispose_closes_all_connections` | G3 | Snap-check that `engine.dispose()` correctly closes underlying handles. Defensive against handle lifecycle regressions. |

### Test infra

- A new fixture file `backend/tests/integration/conftest_pg.py` (or extension to the existing fixture set) boots a Postgres testcontainer and overrides `DATABASE_URL` for the duration of `test_db_maintenance_pg.py` only.
- Mark the file with `pytest.mark.postgres` so SQLite-only CI runs (e.g., agentium-dev's local pytest) keep working without Docker.
- Test naming follows the existing convention (`test_<thing>_<expected_behavior>`); the convention is already enforced by code style and CI.

---

## Failure Modes & Error Handling

The new code can misbehave in five distinct ways; each is caught by the test matrix.

| Mode | What it looks like in production | Caught by |
|---|---|---|
| **Lock-timeout storm** | `lock_timeout` aborts every chunk; helper loops forever deleting zero rows. | `test_chunked_delete_respects_batch_size` (asserts the helper actually _achieves_ bounds by counting chunks; a zero-progress loop times out the test). |
| **SAVEPONT leak** | `db.begin_nested()` raises (e.g., autocommit-bound session) — chunks never commit; subsequent writes see phantom rows. | `test_audit_log_delete_completes_under_lock_budget` plus the existing DBA-style assertions on row counts. |
| **Sleep too short** | Cleanup chews all CPU; concurrent requests still starved. | `test_long_running_cleanup_does_not_exhaust_pool` — concurrent traffic must keep within `DATABASE_POOL_TIMEOUT`. |
| **Sleep too long** | Cleanup never finishes; reports zero-eligible for days. | `test_audit_log_delete_completes_under_lock_budget` — counts covered within a reasonable wall-clock budget. |
| **Connection handle leak in test teardown** | `engine.pool` full of dead handles; next CI run flakes. | `test_engine_dispose_closes_all_connections` plus `test_checked_out_returns_to_baseline_after_traffic` (baseline-restoration inherently implies handle closure). |

Defensive conventions maintained from existing code:

- All exceptions inside `cleanup_stale_data` are caught by the outer `try/except` already present — adding `_chunked_delete` does not change that surface; chunks that error log and continue, since cleanup is best-effort.
- `AlertManager` integration for backup failures (in `trigger_pg_dump`) is left untouched — Phase 9.3 already routes those to a `MonitoringAlert`.

---

## Acceptance Criteria / Definition of Done

### Code
- [ ] `_chunked_delete()` helper exists in `db_maintenance.py` with `batch_size` and `sleep_ms` parameters.
- [ ] `cleanup_stale_data_once()` (new public single-tick method) exists and contains the bodies called by `cleanup_stale_data()`.
- [ ] `cleanup_stale_data_once()` calls `_chunked_delete()` for audit log cleanup, task cleanup, and constitution pruning.
- [ ] Each transaction body sets `lock_timeout = '5s'` before any chunk runs.
- [ ] Diff scope: only `backend/services/db_maintenance.py` changes; no other production file is edited.
- [ ] `get_maintenance_report()` continues to return the same shape.
- [ ] `start_maintenance_monitors()` and the 24-hour cadence are unchanged.

### Tests
- [ ] `backend/tests/unit/test_db_maintenance.py` — 6 tests, all passing on SQLite.
- [ ] `backend/tests/integration/test_db_maintenance_pg.py` — 4 tests, gated behind `pytest.mark.postgres`, all passing on the testcontainer Postgres.
- [ ] `backend/tests/unit/test_connection_pool_under_load.py` — 2 tests, all passing on the configured DB.

### CI & Integration
- [ ] `pytest backend/tests/unit/test_db_maintenance.py backend/tests/unit/test_connection_pool_under_load.py` exits 0.
- [ ] `pytest -m postgres backend/tests/integration/test_db_maintenance_pg.py` exits 0.
- [ ] Full `pytest backend/tests/` exits 0 — no regressions to existing tests.
- [ ] Lint passes (`ruff check backend/services/db_maintenance.py backend/tests/...`).

### TODO.md update
- [ ] `3.4.1`, `3.4.2`, `3.4.3` each flip from `[ ]` to `[x]` in a final commit referencing this spec.

### Out of Scope (explicit)
- Moving `db_maintenance` tasks onto Celery beat (a future separate spec).
- Tuning `AUDIT_LOG_RETENTION_DAYS` / `TASK_ARCHIVE_DAYS` defaults.
- Vector DB snapshot restore flow (Phase 9.3 is verify-only here; disaster recovery is its own scope).
- Adding dashboards/metrics exporters for cleanup results.

---

## Open Questions & Risks

### Resolved during brainstorming
- **Q: What test infrastructure?** Real Postgres via testcontainer — keeps the lock-budget claim honest while keeping corpus-level logic tests cheap. (See § Test Strategy B.)
- **Q: How to bound bulk delete lock hold?** `LIMIT N` + `await asyncio.sleep` between chunks. (See § Production Code Edits, Edit 1.)
- **Q: What is in scope vs out?** Only `db_maintenance.py` and the new test files. No Celery migration. No retention tuning. (See § Non-Goals.)

### Residual risks
- **R1 — Postgres testcontainer requires Docker.** Mitigated by gating with `pytest.mark.postgres` so SQLite-only CI does not break. Local devs without Docker can run unit tests but not the lock-budget integration test.
- **R2 — `await asyncio.sleep(50ms)` × N chunks scales linearly with eligible rows.** For very large backlogs (millions of audit rows), total wall-clock could exceed 24 hours. The mitigations are: (a) `batch_size` and `sleep_ms` are parameters and could be tuned; (b) chunks are committed each iteration so partial progress persists across restarts; (c) the helper exits when a chunk returns 0 — the size of an entangled backlog is naturally capped by `sleep_ms × chunk_count + chunk_delete_time`. Worth checking the absolute upper bound once first prod run happens.
- **R3 — `lock_timeout` interacts with `synchronize_session="fetch"`.** If a SQLite test backend is used for the chunked test, `lock_timeout` is a no-op (SQLite doesn't honor it). This is fine — the lock-budget test is the one that requires Postgres; logic tests don't care.

### What is NOT decided here
- Whether to add a Phase 17 follow-up that moves these tasks to Celery beat. Touched on but explicitly deferred (Non-Goals NG1).
- Whether to expose cleanup duration via the existing `monitoring_service`. Out of scope for this verify-only spec.

---



