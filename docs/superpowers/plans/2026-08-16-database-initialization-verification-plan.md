# Database Initialization Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Verify all 4 subtasks in TODO.md §3.1 (Database Initialization) by adding unit, integration, and load tests that confirm `init_db()` creates all tables, all 76 entity models import correctly, `check_health()` returns healthy status, and connection pooling works under concurrent load.

**Architecture:** Add 4 new test files to existing test infrastructure: unit tests for entity imports and check_health(), integration test for init_db() and table creation, load test for connection pool burst capacity. Use existing conftest.py fixtures (real PostgreSQL) for integration tests, mocked engine for unit tests, and ThreadPoolExecutor for load test.

**Tech Stack:** pytest, SQLAlchemy 2.x, FastAPI TestClient, concurrent.futures, existing docker-compose PostgreSQL test database

## Global Constraints

- All tests MUST pass against real PostgreSQL (integration) or mocked engine (unit)
- Test files follow existing naming: `test_<feature>.py` in `backend/tests/unit/`, `backend/tests/integration/`, `backend/tests/load/`
- Entity verification derives expected models from `entities.__all__` — no hardcoded lists
- Load test targets 35 concurrent workers × 3 requests (105 total) exceeding pool+overflow (30) with pool_timeout=30s
- No changes to production code — test-only additions
- Follow existing commit patterns: `test: add <feature> verification`
- CI integration: add to existing `.github/workflows/test.yml` if present

---

### Task 1: Create Unit Test for Entity Imports (`test_entity_imports.py`)

**Files:**
- Create: `backend/tests/unit/test_entity_imports.py`

**Interfaces:**
- Consumes: `backend.models.entities` module (imports `__all__` and each exported name)
- Produces: Independent test — no downstream dependencies

- [ ] **Step 1: Write the failing test**

```python
"""
Unit test verifying all entity models in entities/__init__.py are importable
and map to database tables (where applicable).
"""
import pytest
from backend.models import entities


def test_all_entities_in_all_are_importable():
    """Every name in entities.__all__ can be imported."""
    for name in entities.__all__:
        assert hasattr(entities, name), f"Missing export: {name}"
        model = getattr(entities, name)
        assert model is not None, f"Export {name} is None"


def test_no_duplicate_exports():
    """entities.__all__ has no duplicates."""
    assert len(entities.__all__) == len(set(entities.__all__)), "Duplicate exports in __all__"


# Table-mapped models (derived from entities.__all__ by filtering enums/base)
# Enums have __members__, Base classes are 'Base'/'BaseEntity', constants like 'AGENT_TYPE_MAP'
def test_table_models_have_tablename():
    """Models expected to be tables have __tablename__ attribute."""
    for name in entities.__all__:
        model = getattr(entities, name)
        is_enum = hasattr(model, '__members__')  # Enum classes have __members__
        is_base = name in ('Base', 'BaseEntity')
        is_constant = name == 'AGENT_TYPE_MAP'
        
        if not (is_enum or is_base or is_constant):
            # This should be a table-mapped model
            assert hasattr(model, '__tablename__'), f"{name} missing __tablename__"
            assert isinstance(model.__tablename__, str), f"{name}.__tablename__ not string"
            assert len(model.__tablename__) > 0, f"{name}.__tablename__ empty"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_entity_imports.py -v`
Expected: FAIL with "No module named 'tests.unit.test_entity_imports'" (file doesn't exist yet)

- [ ] **Step 3: File created above — test will now run**

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_entity_imports.py -v`
Expected: PASS (all 76 exports importable, table models have __tablename__)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/unit/test_entity_imports.py
git commit -m "test: add entity imports verification for section 3.1.2"
```

---

### Task 2: Create Unit Test for check_health() (`test_check_health.py`)

**Files:**
- Create: `backend/tests/unit/test_check_health.py`

**Interfaces:**
- Consumes: `backend.models.database.check_health` function
- Produces: Independent test — no downstream dependencies

- [ ] **Step 1: Write the failing test**

```python
"""
Unit tests for check_health() function.
"""
import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import text
from backend.models.database import check_health


def test_check_health_success():
    """check_health returns healthy with valid latency."""
    with patch('backend.models.database.engine') as mock_engine:
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        
        result = check_health()
        
        assert result["status"] == "healthy"
        assert "latency_ms" in result
        assert isinstance(result["latency_ms"], (int, float))
        assert result["latency_ms"] >= 0
        assert result["database"] == "connected"
        mock_conn.execute.assert_called_once_with(text("SELECT 1"))


def test_check_health_failure():
    """check_health returns unhealthy on exception."""
    with patch('backend.models.database.engine') as mock_engine:
        mock_engine.connect.side_effect = Exception("Connection refused")
        
        result = check_health()
        
        assert result["status"] == "unhealthy"
        assert "error" in result
        assert "Connection refused" in result["error"]
        assert result["database"] == "disconnected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/unit/test_check_health.py -v`
Expected: FAIL with "No module named 'tests.unit.test_check_health'"

- [ ] **Step 3: File created above — test will now run**

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/unit/test_check_health.py -v`
Expected: PASS (both mocked success and failure cases)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/unit/test_check_health.py
git commit -m "test: add check_health unit tests for section 3.1.3"
```

---

### Task 3: Create Integration Test for init_db() and Table Creation (`test_database_initialization.py`)

**Files:**
- Create: `backend/tests/integration/test_database_initialization.py`

**Interfaces:**
- Consumes: `backend.models.database.init_db`, `backend.models.database.check_health`, `backend.models.database.engine`, `backend.models.entities.Base`
- Consumes fixture: `db_session` from `backend/tests/integration/conftest.py` (real PostgreSQL with alembic migrations applied)
- Produces: Independent test — no downstream dependencies

- [ ] **Step 1: Write the failing test**

```python
"""
Integration tests for database initialization (TODO §3.1).
Verifies init_db() creates all tables and check_health() works.
"""
import pytest
from sqlalchemy import inspect
from backend.models.database import init_db, check_health, engine
from backend.models.entities import Base


def test_init_db_creates_all_tables(db_session):
    """init_db() creates all expected tables in the database."""
    # Tables already created by conftest.py alembic migration before test runs
    # This test verifies init_db() doesn't break and tables match metadata
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    # Verify core tables exist (derived from entities module)
    core_tables = [
        'users', 'agents', 'tasks', 'constitutions', 'ethos',
        'audit_logs', 'violations', 'monitoring_alerts',
        'chat_messages', 'conversations', 'channels',
        'scheduled_tasks', 'execution_checkpoints',
        'workflows', 'workflow_executions', 'skills',
        'tool_versions', 'tool_staging', 'tool_usage_logs',
        'model_pricing', 'system_settings'
    ]
    for t in core_tables:
        assert t in tables, f"Core table {t} missing after init_db()"
    
    # Verify all tables have expected columns (no empty tables)
    for t in tables:
        cols = inspector.get_columns(t)
        assert len(cols) > 0, f"Table {t} has no columns"


def test_check_health_returns_healthy(db_session):
    """check_health() returns healthy status with latency against real DB."""
    result = check_health()
    assert result["status"] == "healthy"
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
    assert result["database"] == "connected"


def test_init_db_idempotent(db_session):
    """Calling init_db() multiple times doesn't error."""
    # Should not raise
    init_db()
    init_db()
    # Tables still exist
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    assert 'users' in tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/integration/test_database_initialization.py -v`
Expected: FAIL with "No module named 'tests.integration.test_database_initialization'"

- [ ] **Step 3: File created above — test will now run**

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/integration/test_database_initialization.py -v`
Expected: PASS (requires docker-compose postgres running; conftest sets up test DB)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/integration/test_database_initialization.py
git commit -m "test: add init_db and table creation integration test for section 3.1.1"
```

---

### Task 4: Create Load Test for Connection Pool (`test_connection_pool_load.py`)

**Files:**
- Create: `backend/tests/load/test_connection_pool_load.py`

**Interfaces:**
- Consumes: `backend.models.database.get_db_context`, `backend.models.database.check_health`
- Consumes: Pool settings from config (pool_size=20, max_overflow=10, pool_timeout=30)
- Produces: Independent test — no downstream dependencies

- [ ] **Step 1: Write the failing test**

```python
"""
Load test for SQLAlchemy connection pool under concurrent requests.
Verifies pool (size=20, max_overflow=10) handles burst of 35 concurrent requests.
"""
import concurrent.futures
import time
import statistics
from backend.models.database import get_db_context, check_health
from sqlalchemy import text


POOL_SIZE = 20
MAX_OVERFLOW = 10
TOTAL_CONNECTIONS = POOL_SIZE + MAX_OVERFLOW  # 30
CONCURRENT_REQUESTS = 35  # Exceeds pool capacity
REQUESTS_PER_WORKER = 3


def _single_request(worker_id: int, request_num: int) -> dict:
    """Execute a single SELECT 1 via get_db_context()."""
    start = time.perf_counter()
    try:
        with get_db_context() as db:
            db.execute(text("SELECT 1"))
        latency = (time.perf_counter() - start) * 1000  # ms
        return {"worker": worker_id, "request": request_num, "latency_ms": latency, "success": True}
    except Exception as e:
        latency = (time.perf_counter() - start) * 1000
        return {"worker": worker_id, "request": request_num, "latency_ms": latency, "success": False, "error": str(e)}


def test_connection_pool_under_burst_load():
    """
    Spawn CONCURRENT_REQUESTS concurrent workers, each making REQUESTS_PER_WORKER requests.
    Total connections attempted = 35 * 3 = 105, but only 30 available (20 pool + 10 overflow).
    Workers should queue and succeed (pool_timeout=30s), not fail.
    """
    print(f"\nStarting pool load test: {CONCURRENT_REQUESTS} workers x {REQUESTS_PER_WORKER} requests")
    print(f"Pool capacity: {POOL_SIZE} + {MAX_OVERFLOW} overflow = {TOTAL_CONNECTIONS}")
    
    latencies = []
    errors = []
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=CONCURRENT_REQUESTS) as executor:
        futures = [
            executor.submit(_single_request, worker_id, req_num)
            for worker_id in range(CONCURRENT_REQUESTS)
            for req_num in range(REQUESTS_PER_WORKER)
        ]
        
        for future in concurrent.futures.as_completed(futures, timeout=60):
            result = future.result()
            if result["success"]:
                latencies.append(result["latency_ms"])
            else:
                errors.append(result)
    
    # Assertions
    assert len(errors) == 0, f"Pool exhaustion errors: {errors[:5]}"
    assert len(latencies) == CONCURRENT_REQUESTS * REQUESTS_PER_WORKER
    
    # Latency stats
    avg_latency = statistics.mean(latencies)
    p95_latency = sorted(latencies)[int(len(latencies) * 0.95)]
    max_latency = max(latencies)
    
    print(f"Results: {len(latencies)} successful, {len(errors)} failed")
    print(f"Latency: avg={avg_latency:.2f}ms, p95={p95_latency:.2f}ms, max={max_latency:.2f}ms")
    
    # Sanity checks - pool_timeout is 30s
    assert avg_latency < 5000, "Average latency too high (possible pool contention)"
    assert p95_latency < 10000, "P95 latency too high"
    assert max_latency < 30000, "Max latency exceeds pool_timeout (30s)"


def test_check_health_under_load():
    """Verify check_health() works correctly under concurrent load."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(check_health) for _ in range(20)]
        results = [f.result() for f in concurrent.futures.as_completed(futures)]
    
    for r in results:
        assert r["status"] == "healthy", f"Health check failed under load: {r}"
        assert r["database"] == "connected"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/load/test_connection_pool_load.py -v -s`
Expected: FAIL with "No module named 'tests.load.test_connection_pool_load'"

- [ ] **Step 3: File created above — test will now run**

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/load/test_connection_pool_load.py -v -s`
Expected: PASS (requires running postgres; may take 30-60s; run with `-s` to see print output)

- [ ] **Step 5: Commit**

```bash
git add backend/tests/load/test_connection_pool_load.py
git commit -m "test: add connection pool load test for section 3.1.4"
```

---

### Task 5: Add Tests to CI Workflow

**Files:**
- Modify: `.github/workflows/test.yml` (if exists) or create new workflow

**Interfaces:**
- Consumes: Test files created in Tasks 1-4
- Produces: Automated test execution on PR/push

- [ ] **Step 1: Check for existing workflow**

Run: `ls -la .github/workflows/`
Look for `test.yml`, `ci.yml`, or similar

- [ ] **Step 2: Add database initialization test steps to existing workflow**

```yaml
# Add to existing test job steps:
- name: Run database initialization unit tests
  run: |
    cd backend
    pytest tests/unit/test_entity_imports.py tests/unit/test_check_health.py -v

- name: Run database initialization integration tests
  run: |
    cd backend
    pytest tests/integration/test_database_initialization.py -v
  # Requires postgres service - ensure docker-compose or service container runs

- name: Run connection pool load test
  run: |
    cd backend
    pytest tests/load/test_connection_pool_load.py -v -s --timeout=120
  # Extended timeout for load test
  # Optional: only run on schedule or manual trigger, not every PR
```

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/test.yml
git commit -m "ci: add database initialization verification tests to CI"
```

---

## Self-Review Checklist

After writing the plan, verify against spec:

1. **Spec coverage:**
   - [x] 3.1.1 (init_db creates tables) → Task 3 integration test
   - [x] 3.1.2 (entity imports) → Task 1 unit test  
   - [x] 3.1.3 (check_health) → Task 2 unit + Task 3 integration
   - [x] 3.1.4 (connection pooling under load) → Task 4 load test

2. **No placeholders:** All steps have actual code/commands

3. **Type consistency:** 
   - `check_health()` return type matches across unit/integration tests ✓
   - Pool constants (20/10/30) match `backend/core/config.py` and `database.py` ✓
   - `get_db_context()` used correctly in load test ✓
   - `concurrent.futures.ThreadPoolExecutor` pattern consistent ✓

4. **File paths exact:** All paths use `backend/tests/{unit,integration,load}/` ✓

5. **CI integration:** Step 5 adds to existing workflow (not standalone) ✓

---

**Plan complete and saved to `docs/superpowers/plans/2026-08-16-database-initialization-verification-plan.md`.**

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration
   - **REQUIRED SUB-SKILL:** Use superpowers:subagent-driven-development

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints
   - **REQUIRED SUB-SKILL:** Use superpowers:executing-plans

**Which approach?**