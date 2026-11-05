# Design: Automated Version Rollback Verification (Task 21.5.3)

**Date**: 2026-11-05  
**Status**: Approved for implementation  
**Related**: TODO.md §21.5.3

---

## Objective

Verify that both rollback mechanisms complete in under 5 minutes without data corruption:

1. **Tool Versioning Rollback** — `POST /tool-management/{tool_name}/versions/rollback` → `ToolVersioningService.rollback()`
2. **Git Configuration Versioning Rollback** — `POST /admin/config-restore/{entity_type}/{entity_id}` → `ConfigVersioningService.restore_snapshot()`

---

## Test Strategy

**Approach**: Two dedicated integration test modules (Approach 1)  
**Fixtures**: Minimal (fast, unit-test style)  
**Verification**: pytest integration tests with SLA timing assertions

---

## Module 1: `tests/integration/test_tool_versioning_rollback.py`

### Fixtures

| Fixture | Description |
|---------|-------------|
| `tool_with_versions` | Tool with 5 versions (v1-v5), v5 active; created via service methods |
| `db_session` | Standard test database session |
| `head_agent_id` | Mock Head agent ID ("00001") for authorization |

### Test Cases

| Test | Purpose | Key Assertions |
|------|---------|----------------|
| `test_rollback_to_prior_version_completes_under_5min` | SLA verification | `elapsed < 300s`, `result["rolled_back"] == True` |
| `test_rollback_restores_correct_code_snapshot` | Data integrity | Disk code == target version's `code_snapshot` |
| `test_rollback_updates_tool_registry` | Registry sync | `tool_registry.get(tool_name)` returns rolled-back function |
| `test_rollback_creates_new_version_entry` | Audit trail | New `ToolVersion` with `is_rolled_back=True`, `rolled_back_from_version` set |
| `test_rollback_updates_staging_current_version` | Staging sync | `ToolStaging.current_version` matches new rollback version |
| `test_rollback_audit_log_created` | Audit compliance | `AuditLog` entry: action="tool_rolled_back", correct details |
| `test_rollback_rejects_unauthorized_agent` | Auth enforcement | Task agent (3xxxx) gets 403 |
| `test_rollback_rejects_invalid_version` | Error handling | Non-existent version returns error, no state change |

### Data Integrity Checks (per user direction)

- Tool code on disk matches rolled-back version's `code_snapshot`
- `tool_registry` has correct function reference
- `ToolVersion` DB records consistent (new version created, old deactivated)
- `ToolStaging.current_version` updated
- `AuditLog` entry created with correct metadata

---

## Module 2: `tests/integration/test_config_versioning_rollback.py`

### Fixtures

| Fixture | Description |
|---------|-------------|
| `config_entity_with_history` | Entity (e.g., `channel/test-123`) with 5 Git commits |
| `db_session` | Standard test database session |
| `admin_user` | Mock admin user for `/admin/config-restore` auth |

### Test Cases

| Test | Purpose | Key Assertions |
|------|---------|----------------|
| `test_config_restore_completes_under_5min` | SLA verification | `elapsed < 300s`, returns success |
| `test_config_restore_matches_snapshot_exactly` | Data integrity | All restored fields == Git snapshot at commit SHA |
| `test_config_restore_atomic_db_update` | Atomicity | All entity fields updated in single transaction |
| `test_config_restore_handles_missing_commit` | Error handling | Invalid SHA returns 400, no DB changes |
| `test_config_restore_handles_missing_file` | Error handling | Commit exists but file missing returns 400 |
| `test_config_restore_audit_log_created` | Audit compliance | `AuditLog` entry: action="config_restored" |

### Data Integrity Checks

- Restored entity fields match Git snapshot exactly
- DB update is atomic (all fields or none)
- No partial updates on error

---

## Shared Timing Helper

**Location**: `tests/conftest.py` (or new `tests/helpers/timing.py`)

```python
import time
from contextlib import contextmanager

@contextmanager
def assert_completes_under(seconds: float):
    """Assert the wrapped block completes within time limit."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed = time.perf_counter() - start
        assert elapsed < seconds, f"Operation took {elapsed:.2f}s, expected < {seconds}s"
```

**Usage in tests**:
```python
def test_rollback_completes_under_5min(tool_with_versions, db_session):
    with assert_completes_under(300):
        result = rollback_service.rollback(...)
    assert result["rolled_back"] is True
```

---

## Test Data Strategy (Minimal Fixtures)

### Tool Versioning
- 5 versions, ~50 lines of code each
- Created via service methods: `create_initial_version()` → `propose_update()` → `approve_update()`
- Rollback scenario: v5 (active) → v3 (target)

### Config Versioning
- Entity: `channel/test-channel-123`
- 5 commits with incrementally different JSON configs
- Restore scenario: HEAD → commit-2

---

## CI Integration

**Pytest markers** (add to `pyproject.toml` or `pytest.ini`):
```ini
[tool.pytest.ini_options]
markers = 
    rollback: "Rollback verification tests"
    sla: "Tests with time SLA assertions"
```

**Run command**:
```bash
pytest -m rollback -v
```

---

## Edge Cases (In/Out of Scope)

| Scenario | Coverage |
|----------|----------|
| Concurrent rollbacks | ❌ Out of scope |
| Partial failure mid-rollback | ✅ Verified via atomic DB transactions |
| Large payloads (1000+ versions) | ❌ Out of scope (minimal fixtures) |
| Network/filesystem failures | ❌ Not simulated (unit-test style) |
| Invalid authorization | ✅ Covered in auth tests |
| Invalid target version/commit | ✅ Covered in error handling tests |

---

## Deliverables

1. `tests/integration/test_tool_versioning_rollback.py`
2. `tests/integration/test_config_versioning_rollback.py`
3. Timing helper in `tests/conftest.py`
4. All tests passing, CI-ready

---

## Implementation Notes

- Follow existing test patterns: `test_federation_delegation.py`, `test_workflow_execution_18_2.py`
- Use existing test infrastructure: `conftest.py` fixtures, `TestClient` for API tests
- Mock external dependencies where appropriate (Redis, Docker)
- Ensure tests are isolated (no shared state between test runs)

---

## Self-Review Checklist

- [x] No TBD/TODO placeholders
- [x] Internal consistency: both modules follow same structure
- [x] Scope: focused on 21.5.3 only, no unrelated features
- [x] Ambiguity resolved: "data corruption" defined as specific integrity checks
- [x] SLA threshold explicit: 300 seconds (5 minutes)
- [x] Auth boundaries tested: Head/Council vs Task agents, admin vs non-admin
- [x] Error paths covered: invalid version, missing commit, unauthorized access