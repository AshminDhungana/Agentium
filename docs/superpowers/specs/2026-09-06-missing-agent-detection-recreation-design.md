# Missing Agent Detection & Re-creation — Design Spec

**Date:** 2026-09-06  
**Status:** Approved  
**Related TODO:** 6.5.3 — Missing agents are detected and re-created

---

## 1. Problem Statement

The Agentium genesis protocol creates 4 required agents on first boot:
- Head of Council: `00001`
- Council Members: `10001`, `10002`
- Lead Agent: `20001`

Currently, `InitializationService.is_system_initialized()` only checks for Head `00001`. If any of the other three agents are deleted or become inactive (e.g., via liquidation, database corruption, or manual deletion), the system has no mechanism to detect or repair the gap. This leaves the governance hierarchy incomplete.

---

## 2. Solution Overview

Extend `InitializationService` with a `verify_and_repair()` method that:
1. Checks for all 4 required genesis agents
2. Recreates any missing agents using existing creation logic
3. Returns a detailed repair report
4. Is idempotent and safe to run repeatedly

The method is invoked from three triggers:
- **Startup** (FastAPI lifespan)
- **On-demand API** (`POST /api/v1/agents/verify`)
- **Periodic Celery beat task** (every 5 minutes by default)

---

## 3. Required Agents Definition

| Agent | Agentium ID | Tier | Parent | Creation Method |
|-------|-------------|------|--------|-----------------|
| Head of Council | `00001` | 0 | — | `_create_head_of_council()` |
| Council Member 1 | `10001` | 1 | Head (00001) | `_create_council_members()` |
| Council Member 2 | `10002` | 1 | Head (00001) | `_create_council_members()` |
| Lead Agent | `20001` | 2 | Head (00001) | `_create_default_lead()` |

---

## 4. API: `verify_and_repair()`

```python
async def verify_and_repair(
    self,
    db: Session,
    force_exact_ids: bool = True
) -> Dict[str, Any]:
```

### Parameters
- `db`: Active SQLAlchemy session
- `force_exact_ids`: If `True`, attempt exact genesis IDs first. If the slot is occupied by a different agent, use next available ID in tier and log a warning. If `False`, always use next available ID.

### Return Value
```python
{
    "status": "ok" | "repaired" | "error",
    "checked": 4,
    "missing": ["10001", "20001"],           # agentium_ids that were missing
    "recreated": ["10001", "20001"],         # agentium_ids that were created
    "warnings": ["Slot 10001 occupied by different agent; created 10003 instead"],
    "details": {
        "00001": {"status": "ok", "existed": True},
        "10001": {"status": "recreated", "existed": False, "new_id": "10001"},
        "10002": {"status": "ok", "existed": True},
        "20001": {"status": "recreated", "existed": False, "new_id": "20001"},
    }
}
```

### Behavior
1. Query each required agent by `agentium_id` + `is_active=True`
2. For each missing agent:
   - If `force_exact_ids` and exact ID is free → create with exact ID
   - If `force_exact_ids` and exact ID is taken → generate next available ID in tier, log warning
   - If not `force_exact_ids` → generate next available ID in tier
3. Reuse existing creation methods to ensure consistency with genesis
4. Flush after each creation; commit once at end
5. Log every recreation to `AuditLog` (category: `GOVERNANCE`, action: `agent_recreated`)

---

## 5. Integration Points

### 5.1 Startup (FastAPI Lifespan)
**File:** `backend/main.py`

In `lifespan()`, after `init_db()` and before other initializations:
```python
init_service = InitializationService(db)
result = await init_service.verify_and_repair(db)
if result["status"] == "error":
    logger.error(f"Agent verification failed: {result}")
elif result["status"] == "repaired":
    logger.warning(f"Agent verification repaired missing agents: {result['recreated']}")
```

### 5.2 On-Demand API Endpoint
**File:** `backend/api/routes/agents.py` (new or existing)

```python
@router.post("/verify", response_model=AgentVerificationResponse)
async def verify_agents(db: Session = Depends(get_db)):
    """Verify and repair missing genesis agents."""
    init_service = InitializationService(db)
    result = await init_service.verify_and_repair(db)
    return result
```

**Permission:** Requires admin/sovereign access (Head of Council tier).

### 5.3 Periodic Celery Task
**File:** `backend/celery_app.py` beat schedule

```python
beat_schedule = {
    # ... existing tasks ...
    "verify-agents-every-5-minutes": {
        "task": "backend.services.tasks.verification_tasks.verify_agents_task",
        "schedule": 300.0,  # 5 minutes
    },
}
```

**New Task File:** `backend/services/tasks/verification_tasks.py`
```python
@celery_app.task(name="backend.services.tasks.verification_tasks.verify_agents_task")
def verify_agents_task():
    from backend.models.database import get_db_context
    from backend.services.initialization_service import InitializationService
    
    with get_db_context() as db:
        init_service = InitializationService(db)
        result = asyncio.run(init_service.verify_and_repair(db))
        logger.info(f"Periodic agent verification: {result['status']}")
        return result
```

---

## 6. Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `AGENT_VERIFICATION_ENABLED` | `true` | Master toggle for all verification |
| `AGENT_VERIFICATION_INTERVAL_SECONDS` | `300` | Celery beat interval (seconds) |
| `AGENT_VERIFICATION_EXACT_IDS` | `true` | Prefer exact genesis IDs |

All three are read in `InitializationService.__init__` or at call sites.

---

## 7. Safety & Idempotency Guarantees

| Property | Implementation |
|----------|----------------|
| **Idempotent** | Running multiple times produces identical result; existing agents are skipped |
| **Transactional** | Each creation does `db.flush()`; single `db.commit()` at end; rollback on any error |
| **No cascade** | Only touches the 4 genesis agents; never affects dynamically spawned agents |
| **Audit trail** | Every recreation logged to `AuditLog` with full context |
| **Graceful degradation** | If API key check fails, logs warning but continues (unlike genesis which blocks) |
| **Concurrency safe** | Uses existing `ReincarnationService.generate_id_with_retry()` with advisory locks |

---

## 8. Error Handling

| Scenario | Behavior |
|----------|----------|
| Database connection lost | Propagate exception; Celery will retry; API returns 500 |
| ID pool exhausted for tier | Log error, skip that agent, continue with others, return `status: "error"` |
| Parent agent (Head) missing | This should never happen (Head is checked first); if it does, abort with error |
| Permission denied on API | Return 403; log audit event |
| Concurrent verification runs | Advisory locks in ID generation prevent conflicts; flush/commit ordering handles rest |

---

## 9. Testing Requirements

### Unit Tests
- `verify_and_repair()` with all agents present → `status: "ok"`
- `verify_and_repair()` with 1 missing agent → `status: "repaired"`, agent recreated
- `verify_and_repair()` with all 3 non-Head agents missing → all recreated
- `force_exact_ids=False` → next available IDs used
- `force_exact_ids=True` with slot occupied → warning logged, next ID used

### Integration Tests
- Full lifespan startup with missing agents → agents recreated before API serves traffic
- API endpoint returns correct response shape
- Celery task executes and logs result
- AuditLog entries created for each recreation

---

## 10. Migration Notes

No database migration required. The feature works with existing schema.

If `agentium_id` values `10001`, `10002`, or `20001` are currently held by non-genesis agents (e.g., a Task Agent was manually assigned `10001`), the `force_exact_ids=True` logic will detect the mismatch (wrong `agent_type`) and create a new agent with the next available ID, logging a warning. This is intentional — it preserves data integrity while ensuring the required genesis agents exist.

---

## 11. Future Extensions (Out of Scope)

- Configurable required agent list (beyond the 4 genesis agents)
- Health checks beyond existence (e.g., "agent has checked in within 1 hour")
- Auto-liquidation of orphaned/duplicate agents
- WebSocket broadcast of verification results to dashboard

These can be added in follow-up specs if needed.

---

## 12. Approval

- [x] Design reviewed and approved
- [ ] Implementation complete
- [ ] Tests passing
- [ ] Deployed to staging