# Design: Application Startup (Lifespan) Verification — Section 4.1

## Overview
Verify the existing `lifespan()` implementation in `backend/main.py` against the 9 checklist items in `docs/documents/TODO.md` section 4.1 using Docker-compose based E2E tests with shared infrastructure and transaction rollback isolation.

## Current State Analysis
The `lifespan()` function in `backend/main.py:156-514` already implements all 9 checklist items:
1. **Security startup checks** (`run_security_startup_checks`) — lines 176-181
2. **Workspace config validation** — lines 189-203
3. **Database initialization** + default admin + pricing cache — lines 208-244
4. **Constitution seed** (fallback) — lines 249-264
5. **Persistent Council status check** — lines 269-287
6. **API Manager, Model Allocator, Token Optimizer init** — lines 292-390
7. **MCP Tool Bridge init** — lines 439-454
8. **Pricing sync (background)** — lines 229-239
9. **Idle Governance engine start** — lines 408-423

Plus additional steps: Capability Registry, Knowledge Base bootstrap, optional skill seeding, VOICE_JWT_SECRET generation, Browser service init.

## Verification Strategy

### Test Architecture
- **Infrastructure**: `docker-compose.test.yml` starts PostgreSQL, Redis, **MinIO**, ChromaDB once (session-scoped)
  - *Note: MinIO must be added to docker-compose.test.yml for security startup checks test*
- **Test Runner**: pytest with `FastAPI TestClient` running the app in-process
- **Isolation**: Shared test database with **post-test cleanup** (TRUNCATE all tables) since lifespan creates its own sessions and commits independently
  - Transaction rollback fixtures only work for request-scoped sessions, not lifespan initialization
  - Cleanup fixture runs after each test to reset database state
- **Parallelization**: Tests run sequentially (not parallel) due to shared database state; session-scoped infrastructure is reused

### Test Matrix (9 Tests)

| Test ID | Checklist Item | Verification Approach |
|---------|----------------|----------------------|
| `test_4_1_1_lifespan_completes` | 4.1.1 | Start app, assert no exceptions during lifespan, verify "Agentium startup complete" log |
| `test_4_1_2_security_startup_checks` | 4.1.2 | With default MinIO creds, assert warning logged; with `MINIO_BLOCK_DEFAULT_CREDS=true`, assert RuntimeError |
| `test_4_1_3_workspace_config_validation` | 4.1.3 | Enable host workspace, assert warning when misconfigured; assert info log when correct |
| `test_4_1_4_constitution_seed_first_boot` | 4.1.4 | Fresh DB: assert fallback constitution created with version "v1.0.0"; second boot: assert existing constitution reused |
| `test_4_1_5_persistent_council_status_check` | 4.1.5 | Fresh DB: assert "Persistent Council not yet initialized" log; after genesis: assert "already initialized" log |
| `test_4_1_6_api_manager_model_allocator_token_optimizer` | 4.1.6 | Assert all three services initialize without error; verify logs contain expected messages |
| `test_4_1_7_mcp_tool_bridge_init` | 4.1.7 | Assert bridge initializes; verify tool registry has MCP tools after sync |
| `test_4_1_8_pricing_sync_background` | 4.1.8 | Assert background task created; verify pricing cache loaded from DB |
| `test_4_1_9_idle_governance_engine_starts` | 4.1.9 | Assert idle governance starts; verify background monitors started |

### Fixtures
```python
# conftest.py
import subprocess
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient
from backend.main import app as fastapi_app
from backend.models.database import get_db, Base

@pytest.fixture(scope="session")
def docker_services():
    """Start postgres, redis, minio, chromadb via docker-compose.test.yml"""
    subprocess.run(["docker", "compose", "-f", "docker-compose.test.yml", "up", "-d"], check=True)
    # Wait for healthchecks
    yield
    subprocess.run(["docker", "compose", "-f", "docker-compose.test.yml", "down", "-v"], check=True)

@pytest.fixture(scope="session")
def db_engine(docker_services):
    """SQLAlchemy engine connected to test postgres"""
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
    
    # Re-import to pick up new env vars
    import importlib
    import backend.main
    importlib.reload(backend.main)
    from backend.main import app as reloaded_app
    
    with TestClient(reloaded_app) as client:
        yield reloaded_app
```

### Test Implementation Pattern
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

def test_4_1_2_security_startup_checks(app, caplog, monkeypatch):
    """4.1.2: Security startup checks run (run_security_startup_checks)."""
    # Test default creds warning
    monkeypatch.setenv("MINIO_ROOT_USER", "minioadmin")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minioadmin")
    monkeypatch.setenv("MINIO_BLOCK_DEFAULT_CREDS", "false")
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "SECURITY ALERT" in caplog.text or "default credentials" in caplog.text.lower()

def test_4_1_3_workspace_config_validation(app, caplog, monkeypatch):
    """4.1.3: Workspace config validation runs."""
    monkeypatch.setenv("HOST_WORKSPACE_ENABLED", "true")
    monkeypatch.setenv("HOST_WORKSPACE_ROOT", "/nonexistent")
    
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "misconfigured" in caplog.text.lower() or "workspace config check failed" in caplog.text.lower()

def test_4_1_4_constitution_seed_first_boot(app, db_engine):
    """4.1.4: Constitution seed executes on first boot."""
    from backend.models.entities.constitution import Constitution
    from sqlalchemy.orm import Session
    
    with Session(db_engine) as db:
        constitution = db.query(Constitution).filter_by(is_active=True).first()
        assert constitution is not None
        assert constitution.version == "v1.0.0"
        # Verify it's the fallback (not genesis) constitution
        assert "Core Constitution" in constitution.preamble or "fallback" in constitution.preamble.lower()

def test_4_1_5_persistent_council_status_check(app, caplog):
    """4.1.5: Persistent Council status check runs."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Persistent Council not yet initialized" in caplog.text or "already initialized" in caplog.text.lower()

def test_4_1_6_api_manager_model_allocator_token_optimizer(app, caplog):
    """4.1.6: API Manager, Model Allocator, Token Optimizer initialize."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "API Manager initialized" in caplog.text
        assert "Model Allocator initialized" in caplog.text
        assert "Token Optimizer initialized" in caplog.text

def test_4_1_7_mcp_tool_bridge_init(app, caplog):
    """4.1.7: MCP Tool Bridge initializes."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "MCP Tool Bridge initialized" in caplog.text

def test_4_1_8_pricing_sync_background(app, caplog):
    """4.1.8: Pricing sync runs in background."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Background pricing synchronization" in caplog.text or "pricing cache" in caplog.text.lower()

def test_4_1_9_idle_governance_engine_starts(app, caplog):
    """4.1.9: Idle Governance engine starts."""
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Idle Governance Engine and monitors started" in caplog.text
```

## Success Criteria
- All 9 tests pass in CI
- Tests complete in < 60 seconds total
- No flaky tests (deterministic transaction rollback)
- Clear failure messages indicating which startup step failed

## Out of Scope
- Testing genesis protocol (separate from startup)
- Testing individual tool integrations
- Load/performance testing of startup

## Dependencies
- `docker-compose.test.yml` must include **MinIO** service (currently missing — needs to be added)
- `pytest`, `pytest-asyncio`, `httpx` in test requirements
- Test database user with TRUNCATE privileges on all tables
- `sqlalchemy` for engine/cleanup operations