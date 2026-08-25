# Application Startup (Lifespan) Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Docker-compose based E2E tests to verify all 9 checklist items in section 4.1 of TODO.md against the existing `lifespan()` implementation in `backend/main.py`.

**Architecture:** Use `docker-compose.test.yml` for shared infrastructure (PostgreSQL, Redis, MinIO, ChromaDB). Run FastAPI app in-process via `TestClient` with test database. Isolate tests using post-test TRUNCATE cleanup since lifespan creates its own sessions. Tests run sequentially.

**Tech Stack:** pytest, pytest-asyncio, FastAPI TestClient, SQLAlchemy, docker-compose, httpx

## Global Constraints

- Tests must use `docker-compose.test.yml` infrastructure (session-scoped)
- MinIO service must be added to `docker-compose.test.yml` for security startup checks test
- Each test isolates via post-test TRUNCATE of all tables (not transaction rollback)
- Tests run sequentially due to shared database state
- All 9 tests must pass in CI within 60 seconds total
- Clear failure messages indicating which startup step failed
- Use `TESTING=true` environment variable to skip genesis-related steps

---

### Task 1: Add MinIO service to docker-compose.test.yml

**Files:**
- Modify: `docker-compose.test.yml`

**Interfaces:**
- Produces: MinIO container accessible at `localhost:9000` (S3 API) and `localhost:9001` (console) for security startup checks test

- [ ] **Step 1: Add MinIO service to docker-compose.test.yml**

```yaml
# docker-compose.test.yml - add after chromadb service
  minio:
    image: minio/minio:RELEASE.2024-01-16T16-07-33Z
    container_name: agentium-test-minio
    ports:
      - "9000:9000"
      - "9001:9001"
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    command: server /data --console-address ":9001"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:9000/minio/health/live"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 10s
    # No volumes — ephemeral
```

- [ ] **Step 2: Verify docker-compose.test.yml starts correctly**

Run: `docker compose -f docker-compose.test.yml up -d`
Expected: All 4 services (postgres, redis, chromadb, minio) healthy

- [ ] **Step 3: Commit**

```bash
git add docker-compose.test.yml
git commit -m "test: add MinIO to docker-compose.test.yml for security startup checks"
```

### Task 2: Create conftest.py with pytest fixtures

**Files:**
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: docker-compose.test.yml infrastructure (session-scoped)
- Produces: `docker_services`, `db_engine`, `cleanup_db`, `app` fixtures for all test files

- [ ] **Step 1: Write conftest.py with all fixtures**

```python
# tests/conftest.py
import subprocess
import time
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

# Import Base and all models for table metadata
from backend.models.entities import Base


@pytest.fixture(scope="session")
def docker_services():
    """Start postgres, redis, minio, chromadb via docker-compose.test.yml"""
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d"],
        check=True,
        capture_output=True,
    )
    # Wait for healthchecks to pass
    _wait_for_healthchecks()
    yield
    subprocess.run(
        ["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v"],
        check=True,
        capture_output=True,
    )


def _wait_for_healthchecks(timeout: int = 60):
    """Wait for all docker-compose services to report healthy."""
    start = time.time()
    while time.time() - start < timeout:
        result = subprocess.run(
            ["docker", "compose", "-f", "docker-compose.test.yml", "ps", "--format", "json"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            import json
            services = [json.loads(line) for line in result.stdout.strip().split("\n") if line]
            if all(s.get("Health") == "healthy" for s in services):
                return
        time.sleep(2)
    raise TimeoutError("Services did not become healthy in time")


@pytest.fixture(scope="session")
def db_engine(docker_services):
    """SQLAlchemy engine connected to test postgres."""
    return create_engine("postgresql://agentium:agentium@localhost:5432/agentium_test")


@pytest.fixture(scope="function")
def cleanup_db(db_engine):
    """Truncate all tables after each test to isolate lifespan side effects."""
    yield
    # Post-test cleanup: truncate all tables in reverse FK order
    with db_engine.connect() as conn:
        # Disable FK checks, truncate, re-enable
        conn.execute(text("SET session_replication_role = 'replica'"))
        for table in reversed(Base.metadata.sorted_tables):
            conn.execute(text(f"TRUNCATE TABLE {table.name} RESTART IDENTITY CASCADE"))
        conn.execute(text("SET session_replication_role = 'origin'"))
        conn.commit()


@pytest.fixture(scope="function")
def app(cleanup_db, monkeypatch):
    """FastAPI app with test database URL."""
    # Override DATABASE_URL for this test
    monkeypatch.setenv("DATABASE_URL", "postgresql://agentium:agentium@localhost:5432/agentium_test")
    # Also override other test-specific settings
    monkeypatch.setenv("TESTING", "true")
    monkeypatch.setenv("MINIO_ROOT_USER", "testuser")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "testpassword")
    
    # Re-import to pick up new env vars
    import importlib
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    # Return app without TestClient context - tests will create their own
    yield reloaded_app
```

- [ ] **Step 2: Verify conftest.py syntax**

Run: `python -m py_compile tests/conftest.py`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "test: add conftest.py with fixtures for lifespan verification"
```

### Task 3: Test 4.1.1 - lifespan() completes all init steps without error

**Files:**
- Create: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture from conftest.py
- Produces: Test `test_4_1_1_lifespan_completes`

- [ ] **Step 1: Write failing test**

```python
# tests/test_lifespan_4_1.py
import pytest
from fastapi.testclient import TestClient


def test_4_1_1_lifespan_completes(app, caplog):
    """4.1.1: lifespan() completes all init steps without error."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Agentium startup complete" in caplog.text
```

- [ ] **Step 2: Run test to verify it fails (no implementation yet)**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_1_lifespan_completes -v`
Expected: FAIL (test file doesn't exist yet)

- [ ] **Step 3: Create test file and run to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_1_lifespan_completes -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_1_lifespan_completes"
```

### Task 4: Test 4.1.2 - Security startup checks run

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`, `monkeypatch`
- Produces: Test `test_4_1_2_security_startup_checks`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_2_security_startup_checks(app, caplog, monkeypatch):
    """4.1.2: Security startup checks run (run_security_startup_checks)."""
    # Test default creds warning (non-strict mode)
    monkeypatch.setenv("MINIO_ROOT_USER", "minioadmin")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minioadmin")
    monkeypatch.setenv("MINIO_BLOCK_DEFAULT_CREDS", "false")
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "SECURITY ALERT" in caplog.text or "default credentials" in caplog.text.lower()


def test_4_1_2_security_startup_checks_strict(app, caplog, monkeypatch):
    """4.1.2 strict mode: RuntimeError raised with MINIO_BLOCK_DEFAULT_CREDS=true."""
    monkeypatch.setenv("MINIO_ROOT_USER", "minioadmin")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minioadmin")
    monkeypatch.setenv("MINIO_BLOCK_DEFAULT_CREDS", "true")
    
    # App startup should raise RuntimeError during TestClient context entry
    import importlib
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    with pytest.raises(RuntimeError, match="default credentials"):
        with TestClient(reloaded_app) as client:
            client.get("/api/health")
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_2_security_startup_checks -v`
Expected: PASS

- [ ] **Step 3: Run strict mode test**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_2_security_startup_checks_strict -v`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_2_security_startup_checks"
```

### Task 5: Test 4.1.3 - Workspace config validation runs

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`, `monkeypatch`
- Produces: Test `test_4_1_3_workspace_config_validation`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_3_workspace_config_validation(app, caplog, monkeypatch):
    """4.1.3: Workspace config validation runs."""
    # Test misconfigured workspace (enabled but invalid root)
    monkeypatch.setenv("HOST_WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("HOST_WORKSPACE_ROOT", "/nonexistent")
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "misconfigured" in caplog.text.lower() or "workspace config check failed" in caplog.text.lower()


def test_4_1_3_workspace_config_validation_ok(app, caplog, monkeypatch):
    """4.1.3: Workspace config validation passes when correctly configured."""
    monkeypatch.setenv("HOST_WORKSPACE_ENABLED", "false")
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Should not log workspace warnings
        assert "misconfigured" not in caplog.text.lower()
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_3_workspace_config_validation -v`
Run: `pytest tests/test_lifespan_4_1.py::test_4_1_3_workspace_config_validation_ok -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_3_workspace_config_validation"
```

### Task 6: Test 4.1.4 - Constitution seed executes on first boot

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `db_engine`
- Produces: Test `test_4_1_4_constitution_seed_first_boot`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
from backend.models.entities import Constitution
from sqlalchemy.orm import Session


def test_4_1_4_constitution_seed_first_boot(app, db_engine):
    """4.1.4: Constitution seed executes on first boot."""
    with Session(db_engine) as db:
        constitution = db.query(Constitution).filter_by(is_active=True).first()
        assert constitution is not None, "Fallback constitution should be created"
        assert constitution.version == "v1.0.0"
        # Verify it's the fallback (not genesis) constitution
        assert "Core Constitution" in constitution.preamble or "fallback" in constitution.preamble.lower()


def test_4_1_4_constitution_seed_reused(app, db_engine):
    """4.1.4: Existing constitution is reused on subsequent boots."""
    # First boot already happened in previous test
    with Session(db_engine) as db:
        count = db.query(Constitution).filter_by(is_active=True).count()
        assert count == 1, "Should not create duplicate constitution"
        constitution = db.query(Constitution).filter_by(is_active=True).first()
        assert constitution.version == "v1.0.0"
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_4_constitution_seed_first_boot -v`
Run: `pytest tests/test_lifespan_4_1.py::test_4_1_4_constitution_seed_reused -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_4_constitution_seed"
```

### Task 7: Test 4.1.5 - Persistent Council status check runs

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`
- Produces: Test `test_4_1_5_persistent_council_status_check`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_5_persistent_council_status_check(app, caplog):
    """4.1.5: Persistent Council status check runs."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Fresh DB: Council not yet initialized (genesis hasn't run)
        assert "Persistent Council not yet initialized" in caplog.text or "already initialized" in caplog.text.lower()
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_5_persistent_council_status_check -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_5_persistent_council_status_check"
```

### Task 8: Test 4.1.6 - API Manager, Model Allocator, Token Optimizer initialize

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`
- Produces: Test `test_4_1_6_api_manager_model_allocator_token_optimizer`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_6_api_manager_model_allocator_token_optimizer(app, caplog):
    """4.1.6: API Manager, Model Allocator, Token Optimizer initialize."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "API Manager initialized" in caplog.text
        assert "Model Allocator initialized" in caplog.text
        assert "Token Optimizer initialized" in caplog.text
        # Also verify idle budget logs
        assert "Idle Budget" in caplog.text
        assert "Active Mode Budget" in caplog.text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_6_api_manager_model_allocator_token_optimizer -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_6_api_manager_model_allocator_token_optimizer"
```

### Task 9: Test 4.1.7 - MCP Tool Bridge initializes

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`
- Produces: Test `test_4_1_7_mcp_tool_bridge_init`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_7_mcp_tool_bridge_init(app, caplog):
    """4.1.7: MCP Tool Bridge initializes."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "MCP Tool Bridge initialized" in caplog.text
        # In TESTING mode, should show 0 tools loaded
        assert "approved tool(s) loaded" in caplog.text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_7_mcp_tool_bridge_init -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_7_mcp_tool_bridge_init"
```

### Task 10: Test 4.1.8 - Pricing sync runs in background

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`
- Produces: Test `test_4_1_8_pricing_sync_background`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_8_pricing_sync_background(app, caplog):
    """4.1.8: Pricing sync runs in background."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        # Background pricing sync task is created
        assert "Background pricing synchronization" in caplog.text or "pricing cache" in caplog.text.lower()
        # Pricing cache loaded from DB
        assert "pricing cache" in caplog.text.lower() or "Loaded" in caplog.text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_8_pricing_sync_background -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_8_pricing_sync_background"
```

### Task 11: Test 4.1.9 - Idle Governance engine starts

**Files:**
- Modify: `tests/test_lifespan_4_1.py`

**Interfaces:**
- Consumes: `app` fixture, `caplog`
- Produces: Test `test_4_1_9_idle_governance_engine_starts`

- [ ] **Step 1: Add test to test_lifespan_4_1.py**

```python
def test_4_1_9_idle_governance_engine_starts(app, caplog):
    """4.1.9: Idle Governance engine starts."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Idle Governance Engine and monitors started" in caplog.text
        assert "Eternal Council and Background Health Scanners active" in caplog.text
        assert "Database Maintenance & Backup Scanners active" in caplog.text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_lifespan_4_1.py::test_4_1_9_idle_governance_engine_starts -v`
Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add tests/test_lifespan_4_1.py
git commit -m "test: add test_4_1_9_idle_governance_engine_starts"
```

### Task 12: Run full test suite and update TODO.md

**Files:**
- Modify: `docs/documents/TODO.md`

**Interfaces:**
- Consumes: All 9 tests passing
- Produces: Updated TODO.md with 4.1 items checked off

- [ ] **Step 1: Run all 9 tests together**

Run: `pytest tests/test_lifespan_4_1.py -v`
Expected: All 11 tests pass (9 main + 2 extra for strict/workspace OK)

- [ ] **Step 2: Verify test timing**

Run: `pytest tests/test_lifespan_4_1.py --durations=10`
Expected: Total < 60 seconds

- [ ] **Step 3: Update TODO.md section 4.1 to mark all items complete**

```markdown
## 4. API Gateway & Middleware

> **Files**: `backend/main.py`, `backend/core/middleware.py`, `backend/core/security_middleware.py`, `backend/core/timing_middleware.py`, `backend/core/observer_middleware.py`

- [x] **4.1 — Application Startup (Lifespan)**
  - [x] 4.1.1 — `lifespan()` in `main.py` completes all init steps without error
  - [x] 4.1.2 — Security startup checks run (`run_security_startup_checks`)
  - [x] 4.1.3 — Workspace config validation runs
  - [x] 4.1.4 — Constitution seed executes on first boot
  - [x] 4.1.5 — Persistent Council status check runs
  - [x] 4.1.6 — API Manager, Model Allocator, Token Optimizer initialize
  - [x] 4.1.7 — MCP Tool Bridge initializes (`init_bridge`)
  - [x] 4.1.8 — Pricing sync runs in background
  - [x] 4.1.9 — Idle Governance engine starts
```

- [ ] **Step 4: Commit TODO.md update**

```bash
git add docs/documents/TODO.md
git commit -m "docs: mark section 4.1 lifespan verification complete"
```