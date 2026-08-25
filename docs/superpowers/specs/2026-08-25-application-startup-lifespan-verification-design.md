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
- **Infrastructure**: `docker-compose.test.yml` starts PostgreSQL, Redis, MinIO once (session-scoped)
- **Test Runner**: pytest with `FastAPI TestClient` running the app in-process
- **Isolation**: Each test gets a fresh DB session wrapped in a transaction that rolls back after the test
- **Parallelization**: Tests can run in parallel since they share only read-only infrastructure

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
@pytest.fixture(scope="session")
def docker_services():
    """Start postgres, redis, minio via docker-compose.test.yml"""
    # ... subprocess docker compose up -d
    yield
    # ... docker compose down

@pytest.fixture(scope="session")
def db_engine(docker_services):
    """SQLAlchemy engine connected to test postgres"""
    # ... create_engine with test DB URL

@pytest.fixture(scope="function")
def db_session(db_engine):
    """Fresh session with transaction rollback"""
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()

@pytest.fixture(scope="function")
def app(db_session):
    """FastAPI app with overridden get_db dependency"""
    # ... override get_db to yield db_session
    # ... lifespan runs during TestClient context
    yield app
```

### Test Implementation Pattern
```python
# tests/test_lifespan_4_1.py
def test_4_1_1_lifespan_completes(app, caplog):
    with TestClient(app) as client:
        response = client.get("/api/health")
        assert response.status_code == 200
        assert "Agentium startup complete" in caplog.text

def test_4_1_2_security_startup_checks(monkeypatch, caplog):
    monkeypatch.setenv("MINIO_ROOT_USER", "minioadmin")
    monkeypatch.setenv("MINIO_ROOT_PASSWORD", "minioadmin")
    # ... start app, assert warning log
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
- `docker-compose.test.yml` must exist with postgres, redis, minio services
- `pytest`, `pytest-asyncio`, `httpx`, `testcontainers` (optional) in test requirements
- Test database user with CREATE DATABASE privileges (for potential future DB-per-test)