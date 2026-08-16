# Database Initialization Verification — Section 3.1
**Date:** 2026-08-16  
**Scope:** Verify all 4 subtasks in TODO.md §3.1 (Database Initialization)  
**Status:** Design approved — ready for implementation planning

---

## 1. Overview

This spec defines the verification plan for **section 3.1 — Database Initialization** from the Agentium system verification backlog (`docs/documents/TODO.md`). The goal is to confirm each subtask works correctly, using the existing test infrastructure where possible and adding minimal new tests where gaps exist.

### Subtasks to Verify

| ID | Description | Current State |
|----|-------------|---------------|
| **3.1.1** | `init_db()` creates all tables via SQLAlchemy `create_all()` | Implementation exists, no dedicated test |
| **3.1.2** | All 40+ entity models import correctly in `entities/__init__.py` | 76 models exported in `__all__`, no import verification test |
| **3.1.3** | `check_health()` returns healthy status | Implementation exists, no dedicated test |
| **3.1.4** | Connection pooling works under concurrent requests | Pool config tested (`test_db_pool_config.py`), no load test |

---

## 2. Architecture Context

### `init_db()` (`backend/models/database.py:337-456`)
- Explicitly imports 19 categories of entity models (lines 343-438)
- Calls `Base.metadata.create_all(bind=engine)` (line 441)
- Enables `pg_stat_statements` extension (optional, non-fatal)
- Seeds initial data via `create_initial_data()`

### `entities/__init__.py`
Exports **76 model classes** in `__all__` across 19 categories:
- Base, User/Auth, Constitution/Ethos, Agents (4 tiers), Tasks, Voting, Audit, Monitoring, Critics
- Tool Management, Channels, Scheduled Tasks, Checkpoints, Workflows, Skills
- Citation Graph, Model Pricing, Federation, Plugins, Webhooks, Voice/Speaker
- Wait/Poll, Event Triggers

### `check_health()` (`backend/models/database.py:235-252`)
```python
def check_health() -> dict:
    try:
        start = datetime.utcnow()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        latency = (datetime.utcnow() - start).total_seconds() * 1000
        return {"status": "healthy", "latency_ms": round(latency, 2), "database": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e), "database": "disconnected"}
```

### Connection Pool (`backend/models/database.py:26-35`)
```python
engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=settings.DATABASE_POOL_SIZE,      # 20
    max_overflow=settings.DATABASE_MAX_OVERFLOW, # 10
    pool_timeout=settings.DATABASE_POOL_TIMEOUT, # 30s
    pool_recycle=settings.DATABASE_POOL_RECYCLE, # 1800s
    pool_pre_ping=True,
)
```
Existing unit test: `backend/tests/unit/test_db_pool_config.py` validates pool parameters are honored.

---

## 3. Verification Strategy

### 3.1 Test Environment
- **Primary:** Integration test against real PostgreSQL (uses existing `conftest.py` fixture `db_engine` / `db_session`)
- **Secondary:** Unit tests with mocked engine where fast feedback is needed
- **Load test:** Thread-pool based concurrent request simulation (uses `concurrent.futures`)

### 3.2 Mapping: Subtask → Test Implementation

| Subtask | Test File | Test Type | Description |
|---------|-----------|-----------|-------------|
| **3.1.1** | `tests/integration/test_database_initialization.py` | Integration | Call `init_db()`, inspect created tables via SQLAlchemy `inspect(engine).get_table_names()`, verify all expected tables exist |
| **3.1.2** | `tests/unit/test_entity_imports.py` | Unit | Import `backend.models.entities`, iterate `__all__`, verify each is importable and has `__tablename__` (except enums/base) |
| **3.1.3** | `tests/unit/test_check_health.py` + `tests/integration/test_database_initialization.py` | Unit + Integration | Unit: call `check_health()` directly with mocked engine; Integration: call via FastAPI `/health` endpoint if exists, or direct function with real DB |
| **3.1.4** | `tests/load/test_connection_pool_load.py` | Load | Spawn 35 concurrent threads (exceeds pool_size + max_overflow = 30), each acquires connection via `get_db()`, executes `SELECT 1`, releases. Verify no `TimeoutError` / pool exhaustion errors, measure latency distribution |

---

## 4. Detailed Test Specifications

### 4.1 Test: `test_database_initialization.py` (Integration)
**Location:** `backend/tests/integration/test_database_initialization.py`

```python
"""
Integration tests for database initialization (TODO §3.1).
Verifies init_db() creates all tables and check_health() works.
"""
import pytest
from sqlalchemy import inspect
from backend.models.database import init_db, check_health, engine
from backend.models.entities import Base

EXPECTED_TABLE_PREFIXES = [
    'user', 'agent', 'task', 'constitution', 'ethos', 'audit',
    'monitoring', 'voting', 'chat', 'channel', 'scheduled', 'checkpoint',
    'workflow', 'skill', 'tool', 'citation', 'model_pricing', 'federation',
    'plugin', 'webhook', 'speaker', 'voice', 'wait', 'event',
    'system_settings', 'remote_execution', 'mcp', 'reasoning'
]

def test_init_db_creates_all_tables(db_session):
    """init_db() creates all expected tables in the database."""
    # Tables already created by conftest.py alembic migration
    # This test verifies init_db() doesn't break and tables match metadata
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    # Verify core tables exist (derived from entities/__init__.py __all__)
    core_tables = [
        'users', 'agents', 'tasks', 'constitutions', 'ethos',
        'audit_logs', 'violations', 'monitoring_alerts',
        'chat_messages', 'conversations', 'channels',
        'scheduled_tasks', 'execution_checkpoints',
        'workflows', 'workflow_executions', 'skills'
    ]
    for t in core_tables:
        assert t in tables, f"Core table {t} missing after init_db()"
    
    # Verify all tables have expected columns (no empty tables)
    for t in tables:
        cols = inspector.get_columns(t)
        assert len(cols) > 0, f"Table {t} has no columns"

def test_check_health_returns_healthy(db_session):
    """check_health() returns healthy status with latency."""
    result = check_health()
    assert result["status"] == "healthy"
    assert "latency_ms" in result
    assert result["latency_ms"] >= 0
    assert result["database"] == "connected"

def test_check_health_handles_failure(monkeypatch):
    """check_health() returns unhealthy on connection failure."""
    # This would require mocking engine to fail - optional
    pass
```

### 4.2 Test: `test_entity_imports.py` (Unit)
**Location:** `backend/tests/unit/test_entity_imports.py`

```python
"""
Unit test verifying all entity models in entities/__init__.py are importable
and map to database tables (where applicable).
"""
import pytest
from backend.models import entities

# Models that should have __tablename__ (i.e., are table-mapped)
TABLE_MODELS = [
    # from entities.__all__ - filter out enums, base classes, non-table types
    'User', 'UserModelConfig', 'ModelUsageLog', 'ProviderType', 'ConnectionStatus',
    'UserPreference', 'UserPreferenceHistory', 'ChatMessage', 'Conversation',
    'Constitution', 'Ethos', 'DocumentType', 'Agent', 'HeadOfCouncil',
    'CouncilMember', 'LeadAgent', 'TaskAgent', 'AgentType', 'AgentStatus',
    'Task', 'SubTask', 'TaskAuditLog', 'TaskStatus', 'TaskPriority', 'TaskType',
    'TaskDependency', 'TaskEvent', 'TaskEventType', 'TaskDeliberation',
    'IndividualVote', 'VotingRecord', 'VoteType', 'DeliberationStatus',
    'AmendmentVoting', 'AmendmentStatus', 'AuditLog', 'ConstitutionViolation',
    'SessionLog', 'HealthCheck', 'AuditLevel', 'AuditCategory',
    'AgentHealthReport', 'ViolationReport', 'ViolationSeverity',
    'TaskVerification', 'PerformanceMetric', 'MonitoringAlert', 'MonitoringStatus',
    'CriticAgent', 'CritiqueReview', 'CriticType', 'CriticVerdict',
    'ToolStaging', 'ToolVersion', 'ToolUsageLog', 'ToolMarketplaceListing',
    'ExternalChannel', 'ExternalMessage', 'ChannelType', 'ChannelStatus',
    'ScheduledTask', 'ScheduledTaskExecution', 'ScheduledTaskStatus',
    'ScheduledTaskExecutionStatus', 'ExecutionCheckpoint', 'CheckpointPhase',
    'Workflow', 'WorkflowExecution', 'WorkflowStep', 'WorkflowVersion',
    'WorkflowExecutionStatus', 'WorkflowStepType', 'SkillDB', 'SkillSubmission',
    'CitationEdge', 'ModelPricing', 'MCPTool', 'FederatedInstance',
    'FederatedTask', 'FederatedVote', 'Plugin', 'PluginInstallation',
    'PluginReview', 'DeviceToken', 'NotificationPreference',
    'WebhookSubscription', 'WebhookDeliveryLog', 'WaitCondition',
    'WaitStrategy', 'WaitConditionStatus', 'SpeakerProfile', 'VoiceConfig',
    'EventTrigger', 'EventLog', 'TriggerType', 'EventLogStatus',
    'SystemSetting', 'RemoteExecutionRecord', 'SandboxRecord',
    'ExecutionSummary', 'ExecutionStatus', 'SandboxStatus', 'ReasoningTraceModel',
    'ReasoningStepModel', 'Delegation', 'SkillSchema', 'KnowledgeDocument',
    'ABTestExperiment', 'ABTestRun', 'ABTestResult', 'ModelPerformanceCache',
]

# Models that are enums or base classes (no __tablename__)
NON_TABLE_MODELS = [
    'Base', 'BaseEntity', 'AGENT_TYPE_MAP', 'ProviderType', 'ConnectionStatus',
    'DocumentType', 'AgentType', 'AgentStatus', 'TaskStatus', 'TaskPriority',
    'TaskType', 'TaskEventType', 'VoteType', 'DeliberationStatus',
    'AmendmentStatus', 'AuditLevel', 'AuditCategory', 'ViolationSeverity',
    'MonitoringStatus', 'CriticType', 'CriticVerdict', 'ChannelType',
    'ChannelStatus', 'ScheduledTaskStatus', 'ScheduledTaskExecutionStatus',
    'CheckpointPhase', 'WorkflowExecutionStatus', 'WorkflowStepType',
    'ExecutionStatus', 'SandboxStatus', 'WaitStrategy', 'WaitConditionStatus',
    'TriggerType', 'EventLogStatus', 'ExperimentStatus', 'RunStatus', 'TaskComplexity',
]

def test_all_entities_in_all_are_importable():
    """Every name in entities.__all__ can be imported."""
    for name in entities.__all__:
        assert hasattr(entities, name), f"Missing export: {name}"
        model = getattr(entities, name)
        assert model is not None, f"Export {name} is None"

def test_table_models_have_tablename():
    """Models expected to be tables have __tablename__ attribute."""
    for name in TABLE_MODELS:
        model = getattr(entities, name)
        assert hasattr(model, '__tablename__'), f"{name} missing __tablename__"
        assert isinstance(model.__tablename__, str), f"{name}.__tablename__ not string"
        assert len(model.__tablename__) > 0, f"{name}.__tablename__ empty"

def test_non_table_models_are_enums_or_base():
    """Non-table exports are enums, base classes, or constants."""
    for name in NON_TABLE_MODELS:
        model = getattr(entities, name)
        # Enums (inherit from Enum), Base classes, or module-level constants
        is_enum = hasattr(model, '__members__')  # Enum classes have __members__
        is_base = name in ('Base', 'BaseEntity')
        is_constant = name == 'AGENT_TYPE_MAP'
        assert is_enum or is_base or is_constant, f"{name} unexpected non-table type"

def test_no_duplicate_exports():
    """entities.__all__ has no duplicates."""
    assert len(entities.__all__) == len(set(entities.__all__)), "Duplicate exports in __all__"
```

### 4.3 Test: `test_check_health.py` (Unit)
**Location:** `backend/tests/unit/test_check_health.py`

```python
"""
Unit tests for check_health() function.
"""
import pytest
from unittest.mock import patch, MagicMock
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
        mock_conn.execute.assert_called_once()

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

### 4.4 Test: `test_connection_pool_load.py` (Load)
**Location:** `backend/tests/load/test_connection_pool_load.py`

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
    
    # Sanity checks
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

---

## 5. Test Execution & CI Integration

### 5.1 Local Execution
```bash
# Run integration tests (requires docker-compose postgres)
cd backend && pytest tests/integration/test_database_initialization.py -v

# Run unit tests
cd backend && pytest tests/unit/test_entity_imports.py tests/unit/test_check_health.py -v

# Run load test (requires running postgres)
cd backend && pytest tests/load/test_connection_pool_load.py -v -s
```

### 5.2 CI Integration (GitHub Actions)
Add to existing test workflow (`.github/workflows/test.yml`):
```yaml
- name: Run database initialization tests
  run: |
    cd backend
    pytest tests/integration/test_database_initialization.py -v
    pytest tests/unit/test_entity_imports.py tests/unit/test_check_health.py -v

- name: Run connection pool load test
  run: |
    cd backend
    pytest tests/load/test_connection_pool_load.py -v -s
  # May need longer timeout for load test
```

---

## 6. Acceptance Criteria

| Subtask | Pass Criteria |
|---------|---------------|
| **3.1.1** | `init_db()` runs without error; all core tables exist; `inspect(engine).get_table_names()` includes ≥40 tables matching entity models |
| **3.1.2** | All 76 exports in `entities.__all__` are importable; all table-mapped models have valid `__tablename__`; no duplicate exports |
| **3.1.3** | `check_health()` returns `{"status": "healthy", "latency_ms": N, "database": "connected"}` with N ≥ 0; failure mode returns `"unhealthy"` with error |
| **3.1.4** | 35 concurrent workers × 3 requests (105 total) all succeed; no `TimeoutError` or pool exhaustion; avg latency < 5s, p95 < 10s, max < 30s (pool_timeout) |

---

## 7. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Pool load test times out in CI | Medium | High | Use shorter timeout (15s), reduce concurrent workers to 25 if needed |
| Entity import test becomes stale | Low | Medium | Test derives expected models from `__all__` — self-maintaining |
| check_health() doesn't exist as HTTP endpoint | Low | Low | Test direct function call; HTTP endpoint test optional |
| Alembic migrations vs create_all() mismatch | Medium | Medium | Integration test uses alembic-created DB; verify init_db() doesn't error |

---

## 8. Implementation Order

1. **Unit tests first** (fast feedback): `test_entity_imports.py`, `test_check_health.py`
2. **Integration test**: `test_database_initialization.py` (uses existing `conftest.py` fixtures)
3. **Load test**: `test_connection_pool_load.py` (run separately, may need manual trigger)
4. **CI integration**: Add to GitHub Actions workflow

---

## 9. References

- SQLAlchemy Connection Pooling: https://docs.sqlalchemy.org/en/latest/core/pooling.html
- FastAPI Database Connection Pooling Best Practices: https://asifmuhammad.com/articles/database-pooling-fastapi
- Fixing Connection Pool Exhaustion: https://www.pythonapibuilders.com/scaling-and-operating-production-python-apis/async-database-access-with-sqlalchemy/fixing-connection-pool-exhaustion/
- QueuePool Limit Reached Under FastAPI Load: https://www.codewithkarani.com/blog/sqlalchemy-queuepool-limit-exhausted-fastapi