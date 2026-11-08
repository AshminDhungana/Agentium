# Fix CI Load Test WebSocket Auth by Seeding Genesis Agents

**Date:** 2026-11-07
**Status:** Approved
**Author:** Claude (brainstorming session)

---

## Problem Statement

The performance regression gate in CI (`.github/workflows/integration-tests.yml` → `performance-tests` job) fails after ~9 minutes because the WebSocket authentication phase fails 100%.

**Error from Locust logs:**
```
WebSocket  ws:connect_and_auth                                                                2   2(100.00%) |   1876     103    3650   3650 |    0.17        0.17
```

**Root Cause:** The WebSocket endpoint (`backend/api/routes/websocket.py:150-209`) requires **Head of Council 00001** to exist. The authentication logic returns "System is not yet initialized. Please add an API key on the Models page — genesis will start automatically." when Head 00001 is missing.

**Why Head 00001 is missing in CI:**
1. `backend/tests/load/seed_db.py` only seeds: admin user + agents 10003/10004
2. Genesis protocol (which creates Head 00001) only runs when an API key is configured
3. CI has no API keys configured
4. Therefore genesis never runs, Head 00001 never exists, WebSocket auth fails

---

## Solution Overview

Extend `backend/tests/load/seed_db.py` to create the minimal genesis agent set when `TESTING=true`:
- **Head of Council 00001**
- **Council Members 10001, 10002** (parented to Head)
- **Lead Agent 20001** (parented to Head)

This bypasses the full genesis protocol (no country name vote, no constitution loading, no vector DB indexing) but provides the governance hierarchy required for WebSocket authentication to succeed.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    CI Load Test Flow (Fixed)                    │
├─────────────────────────────────────────────────────────────────┤
│  1. docker-compose.test.yml starts Postgres/Redis/Chroma       │
│  2. alembic upgrade head → creates schema                       │
│  3. seed_db.py runs ──► creates Head 00001 + Council + Lead   │
│  4. Backend server starts                                       │
│  5. Locust runs: WebSocketUser.authenticate() finds Head 00001 │
│  6. Load test passes ✅                                         │
└─────────────────────────────────────────────────────────────────┘
```

---

## Files to Modify

### 1. `backend/tests/load/seed_db.py` (Primary Change)

**Add new function:**
```python
async def create_genesis_agents(db: Session) -> dict:
    """
    Create minimal genesis agents for testing.
    
    Creates: Head 00001, Council 10001/10002, Lead 20001.
    Skips: country name vote, constitution loading, vector indexing.
    Only runs when TESTING=true (CI environment).
    """
```

**Call from `main()` when `os.environ.get("TESTING") == "true"`**

**Implementation details:**
- Idempotent: checks if agents exist before creating
- Uses existing models: `HeadOfCouncil`, `CouncilMember`, `LeadAgent`, `Ethos`
- Uses `reincarnation_service.spawn_lead_agent()` for Lead 20001
- Creates minimal Ethos for each agent (required for auth path)
- Commits transaction so agents are visible to WebSocket handler's separate DB session

### 2. `backend/tests/load/websocket_user.py` (No Change Needed)

The WebSocket auth logic already queries for Head 00001. Once seeded, it will find it and succeed.

---

## Data Model

### Head of Council (00001)
| Field | Value |
|-------|-------|
| agentium_id | "00001" |
| name | "Head of Council Prime" |
| status | AgentStatus.ACTIVE |
| is_active | True |
| is_persistent | True |
| constitution_version | "v1.0.0" |
| ethos_id | (linked Ethos row) |

### Council Members (10001, 10002)
| Field | 10001 | 10002 |
|-------|-------|-------|
| agentium_id | "10001" | "10002" |
| name | "Council Member 1" | "Council Member 2" |
| parent_id | Head.id | Head.id |
| specialization | "Constitutional Law" | "System Security" |
| status | ACTIVE | ACTIVE |

### Lead Agent (20001)
| Field | Value |
|-------|-------|
| agentium_id | "20001" |
| name | "Prime Lead" |
| parent_id | Head.id |
| status | ACTIVE |

---

## Error Handling

| Scenario | Handling |
|----------|----------|
| Agents already exist | Skip creation (idempotent) |
| DB constraint violation | Log warning, continue |
| Ethos creation fails | Log error, raise (fail fast) |
| Lead spawn fails | Log error, raise (fail fast) |
| `TESTING != true` | Function not called (production safe) |

---

## Testing Strategy

### Local Verification
```bash
# In backend directory
TESTING=true DATABASE_URL=postgresql://... python tests/load/seed_db.py
# Verify: Head 00001 exists in agentium_test DB
```

### CI Verification
1. Push change → GitHub Actions runs `integration-tests.yml`
2. `performance-tests` job runs Locust with 20 users for 2 minutes
3. WebSocket `ws:connect_and_auth` should show 0% failure rate
4. Overall failure rate should be <1% (only WebSocket was failing before)

### Regression Tests
- Run existing integration tests → should pass unchanged
- Run unit tests for seed_db.py → add test for `create_genesis_agents()`

---

## Acceptance Criteria

- [ ] `seed_db.py` creates Head 00001, Council 10001/10002, Lead 20001 when `TESTING=true`
- [ ] CI `performance-tests` job passes (WebSocket auth 0% failure)
- [ ] No regression in existing integration tests
- [ ] Production unchanged (guarded by `TESTING=true`)

---

## Out of Scope

- Full genesis protocol in CI (requires API key, adds 30-60s)
- Constitution loading / vector indexing in tests
- Country name vote simulation
- WebSocket auth bypass (weakens test realism)

---

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Seed conflicts with existing data | Low | Medium | Idempotent checks, `TESTING` guard |
| Ethos schema changes break seed | Low | High | Use model constructors, not raw SQL |
| Lead agent spawn API changes | Medium | Medium | Pin to reincarnation_service API |
| CI flakiness from timing | Low | Low | Add retry/wait in seed if needed |

---

## Rollback Plan

If issues arise:
1. Revert `seed_db.py` changes
2. CI falls back to current behavior (WebSocket auth fails, but REST load test passes)
3. Investigate and re-design

---

## Related Files

- `backend/tests/load/locustfile.py` — Load test entry point
- `backend/api/routes/websocket.py` — WebSocket auth logic (lines 150-209)
- `backend/services/initialization_service.py` — Genesis protocol reference
- `.github/workflows/integration-tests.yml` — Performance test job (lines 224-366)