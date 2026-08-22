# Database Maintenance — Design Spec

**Date**: 2026-08-22  
**Scope**: TODO items 3.4.1, 3.4.2, 3.4.3  
**Status**: Approved for implementation

---

## 3.4.1 — VACUUM and Cleanup Tasks Run

### Current State
`DatabaseMaintenanceService.index_maintenance()` runs `ANALYZE` weekly on tables configured in `db_maintenance_config`. No explicit `VACUUM` is executed.

### Decision
**Keep ANALYZE-only approach.** Rely on PostgreSQL's built-in **autovacuum daemon** (enabled by default) for space reclamation from dead tuples. Autovacuum runs automatically when dead tuple thresholds are crossed.

### Rationale
- `VACUUM (ANALYZE)` duplicates autovacuum work with no benefit
- `VACUUM FULL` requires exclusive locks (downtime window)
- `pg_repack` adds operational dependency
- Current `pool_recycle=1800` + `pool_pre_ping=True` prevents stale connections from blocking autovacuum

### Verification
- Ensure `autovacuum = on` in `postgresql.conf` (default in PostgreSQL)
- Slow-query logging (`pg_stat_statements`) will surface planner issues from stale stats
- Existing `index_maintenance()` continues weekly `ANALYZE` for statistics freshness

---

## 3.4.2 — Periodic Tasks Don't Lock Tables Excessively

### Problem
`cleanup_stale_data()` runs single-transaction `DELETE` on `audit_logs` and `tasks` tables. On large tables this:
- Holds locks for the entire transaction duration
- Creates bloat that autovacuum must clean later
- Can block concurrent writes

### Solution: Batched DELETE with LIMIT + Sleep

```python
BATCH_SIZE = 1000          # Configurable via DB_MAINTENANCE_BATCH_SIZE
SLEEP_SECONDS = 0.1        # Configurable via DB_MAINTENANCE_BATCH_SLEEP

def _batch_delete(db, model, filter_criterion, batch_size=BATCH_SIZE, sleep=SLEEP_SECONDS):
    total = 0
    while True:
        # Fetch IDs to delete in batches (avoids locking entire table)
        ids_to_delete = db.query(model.id).filter(filter_criterion).limit(batch_size).all()
        if not ids_to_delete:
            break
            
        id_list = [row[0] for row in ids_to_delete]
        deleted = db.query(model).filter(model.id.in_(id_list)).delete(synchronize_session=False)
        db.commit()
        total += deleted
        
        if deleted < batch_size:
            break
            
        time.sleep(sleep)  # Yield to other transactions
    return total
```

### Tables Affected
| Table | Current Approach | New Approach |
|-------|------------------|--------------|
| `audit_logs` | Single `DELETE` | Batched `DELETE` |
| `tasks` | Single `DELETE` | Batched `DELETE` |
| `constitutions` | Single `DELETE` (small) | Keep as-is |

### Configuration
Add to `backend/core/config.py`:
```python
DB_MAINTENANCE_BATCH_SIZE: int = Field(default=1000, env="DB_MAINTENANCE_BATCH_SIZE")
DB_MAINTENANCE_BATCH_SLEEP: float = Field(default=0.1, env="DB_MAINTENANCE_BATCH_SLEEP")
```

---

## 3.4.3 — Connection Pool Doesn't Leak Under Load

### Current State
Pool configured with:
- `pool_size=20`
- `max_overflow=10`
- `pool_timeout=30`
- `pool_recycle=1800`
- `pool_pre_ping=True`

Burst load test exists (`test_connection_pool_load.py`).

### Gap
No sustained-load test that verifies connections return to pool over time (leak detection).

### Solution: Dedicated Leak Detection Test

**File**: `backend/tests/load/test_connection_pool_leak.py`

```python
def test_connection_pool_no_leak_under_sustained_load():
    """
    Run sustained load for 60 seconds, track checked-out connections.
    Assert checked-out count returns to baseline after each wave.
    """
    import time
    import concurrent.futures
    from backend.models.database import engine, get_db_context
    from sqlalchemy import text
    
    baseline_checked_out = engine.pool.checkedout()
    
    for wave in range(12):  # 12 waves x 5 sec = 60 sec
        with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
            futures = [executor.submit(_single_request, i) for i in range(30)]
            for f in concurrent.futures.as_completed(futures):
                f.result()
        
        # After wave completes, all connections should be returned
        time.sleep(0.5)  # Allow pool cleanup
        checked_out = engine.pool.checkedout()
        assert checked_out <= baseline_checked_out + 2, \
            f"Wave {wave}: Pool leak detected - {checked_out} checked out (baseline: {baseline_checked_out})"
    
    # Final verification
    time.sleep(1)
    final_checked_out = engine.pool.checkedout()
    assert final_checked_out <= baseline_checked_out + 1
```

### Optional: Pool Metrics for Production Observability
Expose via monitoring endpoint:
- `engine.pool.size()` — current pool size
- `engine.pool.checkedout()` — active connections
- `engine.pool.overflow()` — overflow connections
- `engine.pool.checkedin()` — idle connections

---

## Implementation Order

| Step | Task | Files |
|------|------|-------|
| 1 | Add batch config to settings | `backend/core/config.py` |
| 2 | Implement batched DELETE in `cleanup_stale_data()` | `backend/services/db_maintenance.py` |
| 3 | Write leak detection test | `backend/tests/load/test_connection_pool_leak.py` |
| 4 | Run tests in Docker | `docker compose -f docker-compose.test.yml run pytest backend/tests/load/test_connection_pool_leak.py` |
| 5 | Verify maintenance tasks start correctly | `docker compose up backend` (check logs) |

---

## Acceptance Criteria

### 3.4.1
- [ ] `index_maintenance()` runs weekly without errors
- [ ] `ANALYZE` completes on all configured tables
- [ ] No manual `VACUUM` scheduled (autovacuum handles space)

### 3.4.2
- [ ] `cleanup_stale_data()` deletes in batches of 1000 (configurable)
- [ ] 100ms sleep between batches (configurable)
- [ ] No single transaction holds locks > 1 second on large tables
- [ ] Existing unit tests pass

### 3.4.3
- [ ] Leak detection test passes (60s sustained load, no connection leak)
- [ ] Existing burst load test still passes
- [ ] Pool metrics available via monitoring (optional)

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Batched DELETE slower than single DELETE | Acceptable — maintenance runs off-peak; correctness > speed |
| Config values need tuning per deployment | Exposed via env vars; defaults work for most cases |
| Leak test flaky in CI | Run with `docker compose -f docker-compose.test.yml` for consistent PostgreSQL |
| Autovacuum not aggressive enough | Monitor `pg_stat_user_tables.n_dead_tup`; tune `autovacuum_vacuum_scale_factor` if needed |

---

## Self-Review Checklist

- [x] No "TBD" or placeholder sections
- [x] Internal consistency: all three items addressed, no contradictions
- [x] Scope focused: only the 3 TODO items, no unrelated refactoring
- [x] No ambiguity: batch sizes, sleep intervals, test duration all specified
- [x] Follows existing patterns: settings-driven config, async maintenance loops, pytest structure
- [x] Testable in Docker as specified in requirements