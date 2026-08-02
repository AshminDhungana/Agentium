# Design Document: Fix 6 Failing Integration Tests

**Date:** 2026-08-02  
**Status:** Approved  
**Author:** Ashmin Dhungana

---

## Problem Statement

CI run shows 6 failing integration tests across 2 test files, plus coverage at 32% (below 80% gate):

- **4 failures** in `tests/integration/test_initialization_service_integration.py`
- **2 failures** in `tests/integration/test_workflow_engine.py`

---

## Root Cause Analysis

| Test | Error | Root Cause |
|------|-------|------------|
| `test_genesis_grants_council_privileges` | `ImportError: cannot import name 'AgentCapability'` | Test imports non-existent `AgentCapability` from `agents.py`; capabilities are defined in `CapabilityRegistry.Capability` enum |
| `test_broadcast_to_user` | `IntegrityError: duplicate key value violates unique constraint "users_email_key"` | Fixture creates "admin" user; test creates another with same email |
| `test_genesis_commits_at_each_stage` | `AttributeError: 'Session' object has no attribute 'called'` | Test checks `.called` on real `db.commit`/`db.flush` instead of mocks |
| `test_genesis_stops_when_paused` | Same as above | Same mock assertion issue |
| `test_triggers_execution_and_steps_advance` | `ProgrammingError: column workflow_executions.agentium_id does not exist` | `WorkflowExecution._generate_execution_id()` queries `agentium_id` column that doesn't exist in DB table |
| `test_eta_estimation_within_20_percent` | Same as above | Same schema mismatch |

---

## Proposed Fixes (4 Changes)

### Fix 1: Replace `AgentCapability` Import

**File:** `tests/integration/test_initialization_service_integration.py:128`

```python
# OLD (broken)
from backend.models.entities.agents import ..., AgentCapability

# NEW
from backend.services.capability_registry import Capability
```

Update test assertions to use `Capability.SPAWN_LEAD` etc. — enum values match exactly.

---

### Fix 2: Fix Duplicate Admin User

**File:** `tests/integration/test_initialization_service_integration.py` (around line 286)

Query for existing admin user instead of creating a new one:

```python
# OLD
sovereign = User(email="admin@agentium.local", ...)
db.add(sovereign)

# NEW
sovereign = db.query(User).filter_by(is_admin=True, is_active=True).first()
if not sovereign:
    sovereign = User(email="broadcast_test@agentium.local", ...)
    db.add(sovereign)
```

---

### Fix 3: Fix Mock Assertions for Commit/Flush

**File:** `tests/integration/test_initialization_service_integration.py` (lines 384, 426)

Properly patch `commit` and `flush` as `AsyncMock` before checking `.called`:

```python
from unittest.mock import AsyncMock, patch

with patch.object(svc.db, 'commit', new_callable=AsyncMock) as mock_commit:
    with patch.object(svc.db, 'flush', new_callable=AsyncMock) as mock_flush:
        await svc.some_method()
        assert mock_commit.called
        assert mock_flush.called
```

Apply to both `test_genesis_commits_at_each_stage` and `test_genesis_stops_when_paused`.

---

### Fix 4: Fix WorkflowExecution agentium_id Schema Mismatch

**File:** `backend/models/entities/workflow.py` — `WorkflowExecution._generate_execution_id()` (lines 108-126)

The model generates `agentium_id` in `__init__` but `_generate_execution_id()` queries the DB for the last `agentium_id` — this column doesn't exist in the table.

**Option A (Chosen - no migration needed):** Use UUID-based generation instead of querying missing column:

```python
def _generate_execution_id(self) -> str:
    """Generate execution ID: WX + 5-char UUID (no DB query needed)."""
    import uuid
    return f"WX{uuid.uuid4().hex[:5].upper()}"
```

This avoids the missing column query entirely while maintaining unique IDs.

---

## Coverage Note

Current coverage: **32%** (gate: **80%**). Fixing these 6 tests will improve coverage but likely not reach 80%. Additional test coverage work may be needed separately.

---

## Implementation Order

1. Fix 1: `AgentCapability` import (test file only)
2. Fix 2: Duplicate admin user (test file only)
3. Fix 3: Mock assertions (test file only)
4. Fix 4: `WorkflowExecution._generate_execution_id()` (model file)

All fixes are independent and can be done in parallel.

---

## Acceptance Criteria

- [ ] All 6 previously failing tests pass
- [ ] No new test failures introduced
- [ ] Tests run successfully in CI