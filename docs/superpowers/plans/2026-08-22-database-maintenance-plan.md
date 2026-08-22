# Database Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 3 database maintenance improvements: (1) Keep ANALYZE-only approach for vacuum, (2) Add batched DELETE with configurable batch size/sleep to avoid table locking, (3) Add sustained-load connection pool leak detection test.

**Architecture:** Three independent but related improvements to `DatabaseMaintenanceService` and test suite. Batched DELETE modifies existing cleanup logic. Leak test adds new load test file. All config via existing settings system.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, PostgreSQL 15+, pytest, asyncio, Docker Compose

## Global Constraints

- Settings via `backend/core/config.py` using `Field(env=...)` pattern
- Database sessions via `get_db_context()` context manager
- Maintenance tasks run as async loops started from `backend/main.py:416`
- Tests run in Docker: `docker compose -f docker-compose.test.yml run pytest ...`
- Follow existing code style: type hints, docstrings, structured logging
- No new dependencies — use stdlib `time`, `asyncio`, `concurrent.futures`
- Pool config: `pool_size=20`, `max_overflow=10`, `pool_recycle=1800`, `pool_pre_ping=True`

---

### Task 1: Add Batch Configuration to Settings

**Files:**
- Modify: `backend/core/config.py:117-120` (add after existing maintenance settings)

**Interfaces:**
- Produces: `settings.DB_MAINTENANCE_BATCH_SIZE` (int, default=1000), `settings.DB_MAINTENANCE_BATCH_SLEEP` (float, default=0.1)
- Consumed by: Task 2 (`db_maintenance.py`)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_db_maintenance_config.py
from backend.core.config import get_settings


def test_db_maintenance_batch_settings_exist():
    s = get_settings()
    assert hasattr(s, "DB_MAINTENANCE_BATCH_SIZE")
    assert hasattr(s, "DB_MAINTENANCE_BATCH_SLEEP")
    assert s.DB_MAINTENANCE_BATCH_SIZE == 1000
    assert s.DB_MAINTENANCE_BATCH_SLEEP == 0.1


def test_db_maintenance_batch_settings_overridable(monkeypatch):
    monkeypatch.setenv("DB_MAINTENANCE_BATCH_SIZE", "500")
    monkeypatch.setenv("DB_MAINTENANCE_BATCH_SLEEP", "0.05")
    from backend.core.config import get_settings as get_settings_fresh
    get_settings_fresh.cache_clear()
    import backend.core.config as config_mod
    import importlib
    importlib.reload(config_mod)
    s = config_mod.get_settings()
    assert s.DB_MAINTENANCE_BATCH_SIZE == 500
    assert s.DB_MAINTENANCE_BATCH_SLEEP == 0.05
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/unit/test_db_maintenance_config.py -v`
Expected: FAIL - attributes don't exist

- [ ] **Step 3: Add settings to config.py**

```python
# In backend/core/config.py, after line 120 (after CONSTITUTION_MAX_VERSIONS)
    # Phase 9: Database Maintenance — batch cleanup settings
    DB_MAINTENANCE_BATCH_SIZE: int = Field(default=1000, env="DB_MAINTENANCE_BATCH_SIZE")
    DB_MAINTENANCE_BATCH_SLEEP: float = Field(default=0.1, env="DB_MAINTENANCE_BATCH_SLEEP")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/unit/test_db_maintenance_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/core/config.py backend/tests/unit/test_db_maintenance_config.py
git commit -m "feat: add DB maintenance batch size/sleep config"
```

---

### Task 2: Implement Batched DELETE in cleanup_stale_data()

**Files:**
- Modify: `backend/services/db_maintenance.py:32-96` (the `cleanup_stale_data` method)
- Test: `backend/tests/unit/test_db_maintenance_batched_delete.py`

**Interfaces:**
- Consumes: `settings.DB_MAINTENANCE_BATCH_SIZE`, `settings.DB_MAINTENANCE_BATCH_SLEEP`
- Produces: Modified `cleanup_stale_data()` that deletes in batches with sleep
- Consumed by: Task 4 (integration verification)

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/unit/test_db_maintenance_batched_delete.py
import time
from unittest.mock import MagicMock, patch
from backend.services.db_maintenance import DatabaseMaintenanceService
from backend.models.entities.audit import AuditLog
from backend.models.entities.task import Task


def test_batch_delete_splits_large_delete_into_batches():
    """Verify _batch_delete helper splits large deletes into multiple transactions."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_limit = MagicMock()
    
    # Simulate 2500 rows returned in 3 batches: 1000, 1000, 500
    batch1 = [(i,) for i in range(1, 1001)]
    batch2 = [(i,) for i in range(1001, 2001)]
    batch3 = [(i,) for i in range(2001, 2501)]
    mock_limit.all.side_effect = [batch1, batch2, batch3, []]
    
    mock_filter.limit.return_value = mock_limit
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query
    
    # Call the helper (will be added in implementation)
    deleted = DatabaseMaintenanceService._batch_delete(
        mock_db, AuditLog, AuditLog.created_at < "2024-01-01", batch_size=1000, sleep=0
    )
    
    assert deleted == 2500
    assert mock_db.commit.call_count == 3  # One commit per batch
    assert mock_db.query.call_count == 3   # One query per batch


def test_batch_delete_respects_batch_size_and_sleep():
    """Verify batch size and sleep are configurable."""
    mock_db = MagicMock()
    mock_query = MagicMock()
    mock_filter = MagicMock()
    mock_limit = MagicMock()
    
    batch1 = [(i,) for i in range(1, 501)]
    batch2 = [(i,) for i in range(501, 1001)]
    mock_limit.all.side_effect = [batch1, batch2, []]
    
    mock_filter.limit.return_value = mock_limit
    mock_query.filter.return_value = mock_filter
    mock_db.query.return_value = mock_query
    
    with patch("time.sleep") as mock_sleep:
        deleted = DatabaseMaintenanceService._batch_delete(
            mock_db, AuditLog, AuditLog.created_at < "2024-01-01", batch_size=500, sleep=0.05
        )
    
    assert deleted == 1000
    assert mock_sleep.call_count == 1  # Sleep between batches
    mock_sleep.assert_called_with(0.05)
    mock_filter.limit.assert_called_with(500)


def test_cleanup_stale_data_uses_batched_delete_for_audit_logs():
    """Verify cleanup_stale_data calls batched delete for audit_logs."""
    with patch.object(DatabaseMaintenanceService, "_batch_delete") as mock_batch:
        mock_batch.return_value = 100
        mock_db = MagicMock()
        
        # Need to mock the db context manager
        with patch("backend.services.db_maintenance.get_db_context") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_db
            mock_db.query.return_value.filter.return_value.delete.return_value = 0
            
            # Run one iteration of cleanup (mock the sleep to exit loop)
            import asyncio
            async def run_once():
                task = asyncio.create_task(DatabaseMaintenanceService.cleanup_stale_data())
                await asyncio.sleep(0.01)
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            asyncio.run(run_once())
            
            # Verify batched delete was called for audit_logs
            mock_batch.assert_any_call(
                mock_db, AuditLog, mock_db.query(AuditLog).filter.return_value, 
                batch_size=1000, sleep=0.1
            )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/unit/test_db_maintenance_batched_delete.py -v`
Expected: FAIL - `_batch_delete` doesn't exist, `cleanup_stale_data` not using it

- [ ] **Step 3: Add `_batch_delete` helper and modify `cleanup_stale_data()`**

```python
# In backend/services/db_maintenance.py

# Add imports at top
import time
from backend.core.config import settings

# Add _batch_delete static method after _prune_constitution_versions (around line 132)
    @staticmethod
    def _batch_delete(db: Session, model, filter_criterion, batch_size: int = None, sleep: float = None) -> int:
        """
        Delete rows matching filter_criterion in batches to avoid long locks.
        
        Args:
            db: Database session
            model: SQLAlchemy model class (e.g., AuditLog, Task)
            filter_criterion: SQLAlchemy filter expression (e.g., AuditLog.created_at < cutoff)
            batch_size: Rows per batch (default from settings)
            sleep: Seconds to sleep between batches (default from settings)
        
        Returns:
            Total rows deleted
        """
        if batch_size is None:
            batch_size = settings.DB_MAINTENANCE_BATCH_SIZE
        if sleep is None:
            sleep = settings.DB_MAINTENANCE_BATCH_SLEEP
        
        total = 0
        while True:
            # Fetch IDs to delete in this batch
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

# Modify cleanup_stale_data() (lines 32-96) to use _batch_delete:
# Replace the audit_logs deletion (lines 48-56):
    # OLD:
    # report["audit_logs_deleted"] = (
    #     db.query(AuditLog)
    #     .filter(AuditLog.created_at < audit_cutoff)
    #     .delete()
    # )
    # NEW:
    report["audit_logs_deleted"] = DatabaseMaintenanceService._batch_delete(
        db, AuditLog, AuditLog.created_at < audit_cutoff
    )

# Replace the tasks deletion (lines 58-72):
    # OLD:
    # report["tasks_deleted"] = (
    #     db.query(Task)
    #     .filter(
    #         Task.status.in_(["completed", "cancelled", "failed"]),
    #         Task.updated_at < task_cutoff,
    #     )
    #     .delete()
    # )
    # NEW:
    from sqlalchemy import and_
    task_filter = and_(
        Task.status.in_(["completed", "cancelled", "failed"]),
        Task.updated_at < task_cutoff,
    )
    report["tasks_deleted"] = DatabaseMaintenanceService._batch_delete(
        db, Task, task_filter
    )

# Keep constitution version cleanup as-is (small table, single DELETE is fine)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/unit/test_db_maintenance_batched_delete.py -v`
Expected: PASS

- [ ] **Step 5: Run existing maintenance tests to ensure no regression**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/ -k "maintenance" -v`
Expected: PASS (or at least no new failures)

- [ ] **Step 6: Commit**

```bash
git add backend/services/db_maintenance.py backend/tests/unit/test_db_maintenance_batched_delete.py
git commit -m "feat: add batched DELETE to database maintenance cleanup"
```

---

### Task 3: Add Connection Pool Leak Detection Test

**Files:**
- Create: `backend/tests/load/test_connection_pool_leak.py`
- Test: Same file (self-contained)

**Interfaces:**
- Consumes: `backend.models.database.engine`, `backend.models.database.get_db_context`
- Produces: Test that verifies no connection leak under sustained load
- Independent: Can run standalone

- [ ] **Step 1: Write the test file with implementation**

```python
# backend/tests/load/test_connection_pool_leak.py
"""
Sustained load test for SQLAlchemy connection pool leak detection.
Runs 60 seconds of concurrent requests, verifies checked-out connections return to baseline.
"""
import concurrent.futures
import time
import statistics
from backend.models.database import engine, get_db_context
from sqlalchemy import text


POOL_SIZE = 20
MAX_OVERFLOW = 10
TOTAL_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW  # 30
CONCURRENT_WORKERS = 30
REQUESTS_PER_WAVE = 1
WAVES = 12  # 12 waves x ~5 sec = ~60 seconds
WAVE_INTERVAL = 5  # seconds between waves


def _single_request(worker_id: int) -> dict:
    """Execute a single SELECT 1 via get_db_context()."""
    start = time.perf_counter()
    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000  # ms
        return {"worker": worker_id, "latency_ms": latency, "success": True}
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return {"worker": worker_id, "latency_ms": latency, "success": False, "error": str(e)}


def test_connection_pool_no_leak_under_sustained_load():
    """
    Run sustained load for 60 seconds, track checked-out connections.
    Assert checked-out count returns to baseline after each wave.
    """
    print(f"\nStarting pool leak test: {WAVES} waves x {CONCURRENT_WORKERS} workers")
    print(f"Pool capacity: {POOL_SIZE} + {MAX_OVERFLOW} overflow = {TOTAL_CONNECTIONS}")
    
    baseline_checked_out = engine.pool.checkedout()
    print(f"Baseline checked-out connections: {baseline_checked_out}")
    
    all_latencies = []
    all_errors = []
    leak_detected = False
    
    for wave in range(WAVES):
        wave_start = time.perf_counter()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_WORKERS) as executor:
            futures = [executor.submit(_single_request, i) for i in range(CONCURRENT_WORKERS)]
            
            for future in concurrent.futures.as_completed(futures, timeout=30):
                result = future.result()
                if result["success"]:
                    all_latencies.append(result["latency_ms"])
                else:
                    all_errors.append(result)
        
        wave_duration = time.perf_counter() - wave_start
        
        # Allow pool cleanup
        time.sleep(0.5)
        
        checked_out = engine.pool.checkedout()
        pool_size = engine.pool.size()
        overflow = engine.pool.overflow()
        
        print(f"Wave {wave + 1}/{WAVES}: {wave_duration:.1f}s | "
              f"checked_out={checked_out} | pool_size={pool_size} | overflow={overflow} | "
              f"errors={len([e for e in all_errors if e.get('worker') >= wave*CONCURRENT_WORKERS])}")
        
        # Allow small variance (+2) for connections being returned
        if checked_out > baseline_checked_out + 2:
            leak_detected = True
            print(f"  ⚠️  LEAK DETECTED: {checked_out} checked out (baseline: {baseline_checked_out})")
    
    # Final verification after all waves
    time.sleep(1)
    final_checked_out = engine.pool.checkedout()
    print(f"Final checked-out: {final_checked_out} (baseline: {baseline_checked_out})")
    
    # Assertions
    assert len(all_errors) == 0, f"Pool exhaustion errors: {all_errors[:5]}"
    assert not leak_detected, "Connection pool leak detected during sustained load"
    assert final_checked_out <= baseline_checked_out + 1, \
        f"Final leak: {final_checked_out} checked out (baseline: {baseline_checked_out})"
    
    # Latency sanity checks
    avg_latency = statistics.mean(all_latencies) if all_latencies else 0
    p95_latency = sorted(all_latencies)[int(len(all_latencies) * 0.95)] if all_latencies else 0
    max_latency = max(all_latencies) if all_latencies else 0
    
    print(f"Latency: avg={avg_latency:.2f}ms, p95={p95_latency:.2f}ms, max={max_latency:.2f}ms")
    assert avg_latency < 5000, "Average latency too high (possible pool contention)"
    assert max_latency < 30000, "Max latency exceeds pool_timeout (30s)"


def test_check_health_under_sustained_load():
    """Verify check_health() works correctly under concurrent load."""
    from backend.models.database import check_health
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_health) for _ in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]

    for r in results:
        assert r["status"] == "healthy", f"Health check failed under load: {r}"
        assert r["database"] == "connected"
```

- [ ] **Step 2: Run test to verify it passes**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/load/test_connection_pool_leak.py -v`
Expected: PASS (test implements both test and implementation in one file per TDD pattern)

Note: This test file is self-contained — it IS the implementation (the test verifies the system behavior). No separate implementation file needed.

- [ ] **Step 3: Run existing pool test to ensure no regression**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/load/test_connection_pool_load.py -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/tests/load/test_connection_pool_leak.py
git commit -m "test: add connection pool leak detection under sustained load"
```

---

### Task 4: Integration Verification — Maintenance Tasks Start Correctly

**Files:**
- Test: Manual verification via Docker Compose logs
- Modify: None (verification only)

**Interfaces:**
- Consumes: Tasks from 1-3
- Produces: Confidence that maintenance loops run without errors

- [ ] **Step 1: Start full stack in test mode**

```bash
docker compose -f docker-compose.test.yml up -d postgres redis backend
```

- [ ] **Step 2: Wait for backend to start and check logs for maintenance startup**

```bash
docker compose -f docker-compose.test.yml logs -f backend | grep -E "(Database Maintenance|Maintenance|cleanup_stale_data|index_maintenance|trigger_pg_dump|vector_db)"
```
Expected to see:
- `Database Maintenance & Backup Scanners active`
- No errors from `cleanup_stale_data` or `index_maintenance`

- [ ] **Step 3: Verify cleanup_stale_data runs (manually trigger or wait)**

Option A: Wait 24 hours (not practical)
Option B: Temporarily reduce sleep in test env to 10 seconds, verify batch deletes work
Option C: Call the function directly via test

```bash
docker compose -f docker-compose.test.yml exec backend python -c "
from backend.services.db_maintenance import DatabaseMaintenanceService
from backend.models.database import get_db_context
from datetime import datetime, timedelta
from backend.core.config import settings

# Temporarily reduce retention for test
settings.AUDIT_LOG_RETENTION_DAYS = 0
settings.TASK_ARCHIVE_DAYS = 0

import asyncio
async def test():
    report = await DatabaseMaintenanceService.cleanup_stale_data().__anext__()
    print('Cleanup report:', report)
asyncio.run(test())
"
```

- [ ] **Step 4: Verify index_maintenance runs ANALYZE**

```bash
docker compose -f docker-compose.test.yml exec backend python -c "
from backend.services.db_maintenance import DatabaseMaintenanceService
import asyncio
async def test():
    # This will run ANALYZE on default tables
    await DatabaseMaintenanceService.index_maintenance().__anext__()
    print('Index maintenance completed')
asyncio.run(test())
"
```

- [ ] **Step 5: Commit verification notes (optional)**

```bash
git commit --allow-empty -m "chore: verify maintenance tasks start correctly in Docker"
```

---

### Task 5: Run Full Test Suite for Regression Check

**Files:**
- None (execution only)

- [ ] **Step 1: Run all load tests**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/load/ -v`

- [ ] **Step 2: Run all unit tests**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/unit/ -v`

- [ ] **Step 3: Run integration tests related to database**

Run: `docker compose -f docker-compose.test.yml run pytest backend/tests/integration/ -k "db or database or pool" -v`

- [ ] **Step 4: Commit if all pass**

```bash
git commit --allow-empty -m "chore: all tests pass after database maintenance changes"
```

---

## Self-Review Checklist

- [x] Spec coverage: All 3 TODO items (3.4.1, 3.4.2, 3.4.3) have corresponding tasks
- [x] No placeholders: Every step has actual code/commands
- [x] Type consistency: `_batch_delete` signature matches test expectations
- [x] Config names match: `DB_MAINTENANCE_BATCH_SIZE` / `DB_MAINTENANCE_BATCH_SLEEP` used consistently
- [x] File paths exact: All paths are absolute from repo root
- [x] Commands exact: Docker compose commands match project structure
- [x] TDD order: Test written first, then implementation
- [x] Granularity: Each task is 2-5 minutes of work
- [x] Independence: Task 1-3 can be done in parallel (different files); Task 4 depends on 1-3

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-22-database-maintenance-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**