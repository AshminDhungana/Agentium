# Fix CI Load Test WebSocket Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `backend/tests/load/seed_db.py` to create minimal genesis agents (Head 00001, Council 10001/10002, Lead 20001) when `TESTING=true` so WebSocket authentication succeeds in CI load tests.

**Architecture:** The seed script will create the governance hierarchy directly in the database using existing SQLAlchemy models and the reincarnation service. This bypasses the full genesis protocol (no country name vote, no constitution loading) but provides the agents required for WebSocket auth. The change is guarded by `TESTING=true` so production is unaffected.

**Tech Stack:** Python 3.11+, SQLAlchemy 2.0, existing Agentium models (HeadOfCouncil, CouncilMember, LeadAgent, Ethos), reincarnation_service

## Global Constraints

- Only runs when `os.environ.get("TESTING") == "true"` (CI environment)
- Must be idempotent: check if agents exist before creating
- Must commit transaction so agents are visible to WebSocket handler's separate DB session
- Use existing model constructors and reincarnation_service.spawn_lead_agent()
- Follow existing code style in seed_db.py
- No changes to production code paths

---

### Task 1: Add imports and create_genesis_agents() function to seed_db.py

**Files:**
- Modify: `backend/tests/load/seed_db.py`

**Interfaces:**
- Consumes: SQLAlchemy Session, existing models from backend.models.entities.agents
- Produces: `create_genesis_agents(db: Session) -> dict` function that returns created agents

- [ ] **Step 1: Read current seed_db.py to understand structure**

```bash
cat backend/tests/load/seed_db.py
```

Expected: See existing imports, main() function, admin user + agents 10003/10004 creation

- [ ] **Step 2: Add required imports at top of file**

```python
# Add to existing imports
from backend.models.entities.agents import (
    HeadOfCouncil,
    CouncilMember,
    LeadAgent,
    AgentStatus,
)
from backend.models.entities.constitution import Ethos
from backend.services.reincarnation_service import reincarnation_service
from sqlalchemy.orm import Session
```

- [ ] **Step 3: Write the create_genesis_agents() function**

```python
async def create_genesis_agents(db: Session) -> dict:
    """
    Create minimal genesis agents for testing (CI load tests).
    
    Creates: Head 00001, Council 10001/10002, Lead 20001.
    Only runs when TESTING=true. Idempotent.
    """
    result = {"head": None, "council": [], "lead": None}
    
    # ── Head 00001 ──────────────────────────────────────────────
    head = db.query(HeadOfCouncil).filter_by(agentium_id="00001", is_active=True).first()
    if not head:
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head of Council Prime",
            description="The supreme authority of Agentium. Eternal and persistent.",
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=True,
            idle_mode_enabled=True,
            constitution_version="v1.0.0"
        )
        db.add(head)
        db.flush()
        
        # Create minimal ethos for Head (required for auth path)
        head_ethos = Ethos(
            agentium_id="E00001",
            agent_type="head_of_council",
            mission_statement="Supreme executive authority of Agentium for testing.",
            core_values=json.dumps(["Constitutional Fidelity", "Sovereign Loyalty"]),
            behavioral_rules=json.dumps(["Read Constitution before tasks"]),
            restrictions=json.dumps(["Cannot violate Constitution"]),
            capabilities=json.dumps(["Full governance authority"]),
            created_by_agentium_id="00001",
            agent_id=head.id,
            is_verified=True,
            verified_by_agentium_id="00001"
        )
        db.add(head_ethos)
        db.flush()
        head.ethos_id = head_ethos.id
        db.flush()
        
        result["head"] = head
    else:
        result["head"] = head
    
    # ── Council Members 10001, 10002 ───────────────────────────
    specializations = ["Constitutional Law", "System Security"]
    for i in range(2):
        agentium_id = f"1{i+1:04d}"  # 10001, 10002
        member = db.query(CouncilMember).filter_by(agentium_id=agentium_id, is_active=True).first()
        if not member:
            member = CouncilMember(
                agentium_id=agentium_id,
                name=f"Council Member {i+1}",
                description=f"Founding Council Member {i+1}",
                status=AgentStatus.ACTIVE,
                is_active=True,
                parent_id=head.id,
                specialization=specializations[i]
            )
            db.add(member)
            db.flush()
            
            # Create minimal ethos for Council
            member_ethos = Ethos(
                agentium_id=f"E{agentium_id}",
                agent_type="council_member",
                mission_statement=f"Council Member {i+1} — specialist in {specializations[i]}.",
                core_values=json.dumps(["Democratic Deliberation", "Constitutional Compliance"]),
                behavioral_rules=json.dumps(["Vote on amendments", "Monitor compliance"]),
                restrictions=json.dumps(["Cannot unilaterally approve amendments"]),
                capabilities=json.dumps(["Voting rights", "Oversight access"]),
                created_by_agentium_id="00001",
                agent_id=member.id,
                is_verified=True,
                verified_by_agentium_id="00001"
            )
            db.add(member_ethos)
            db.flush()
            member.ethos_id = member_ethos.id
            db.flush()
        
        result["council"].append(member)
    
    # ── Lead Agent 20001 ────────────────────────────────────────
    lead = db.query(LeadAgent).filter_by(agentium_id="20001", is_active=True).first()
    if not lead:
        lead = reincarnation_service.spawn_lead_agent(
            parent=head,
            name="Prime Lead",
            description="Default Lead Agent seeded for CI load testing.",
            db=db
        )
        # Override agentium_id to 20001 if different
        if lead.agentium_id != "20001":
            lead.agentium_id = "20001"
        db.flush()
        result["lead"] = lead
    else:
        result["lead"] = lead
    
    # Commit so agents are visible to other DB sessions (WebSocket handler)
    db.commit()
    
    return result
```

- [ ] **Step 4: Add json import if not present**

```python
# At top of file, ensure json is imported
import json
```

- [ ] **Step 5: Call create_genesis_agents() in main() when TESTING=true**

```python
# In main(), after existing seed logic, add:
if os.environ.get("TESTING") == "true":
    print("TESTING=true detected — creating genesis agents for CI load test...")
    await create_genesis_agents(db)
    print("Genesis agents created successfully.")
```

- [ ] **Step 6: Run seed_db.py locally to verify**

```bash
cd backend
TESTING=true DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test python tests/load/seed_db.py
```

Expected: Output shows "Genesis agents created successfully" and agents exist in DB

- [ ] **Step 7: Verify agents in database**

```bash
docker compose -f docker-compose.test.yml exec -T postgres psql -U agentium -d agentium_test -c "SELECT agentium_id, agent_type, is_active FROM agents WHERE agentium_id IN ('00001', '10001', '10002', '20001');"
```

Expected: 4 rows returned with correct agentium_ids and is_active=true

- [ ] **Step 8: Commit**

```bash
git add backend/tests/load/seed_db.py
git commit -m "feat(load-test): seed genesis agents (Head 00001, Council, Lead) for CI WebSocket auth"
```

---

### Task 2: Add unit test for create_genesis_agents()

**Files:**
- Create: `backend/tests/load/test_seed_db.py`

**Interfaces:**
- Consumes: create_genesis_agents() from seed_db.py
- Produces: Test coverage for the new function

- [ ] **Step 1: Create test file**

```python
"""Tests for seed_db.py genesis agent creation."""
import os
import pytest
from sqlalchemy.orm import Session

# Set TESTING before importing seed_db
os.environ["TESTING"] = "true"

from backend.tests.load.seed_db import create_genesis_agents
from backend.models.entities.agents import HeadOfCouncil, CouncilMember, LeadAgent


@pytest.mark.asyncio
async def test_create_genesis_agents_creates_all_agents(db_session: Session):
    """Test that create_genesis_agents creates Head, Council, and Lead."""
    result = await create_genesis_agents(db_session)
    
    # Verify return structure
    assert result["head"] is not None
    assert len(result["council"]) == 2
    assert result["lead"] is not None
    
    # Verify Head 00001
    head = db_session.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None
    assert head.name == "Head of Council Prime"
    assert head.is_active is True
    assert head.is_persistent is True
    assert head.ethos_id is not None
    
    # Verify Council 10001, 10002
    council = db_session.query(CouncilMember).filter(
        CouncilMember.agentium_id.in_(["10001", "10002"])
    ).all()
    assert len(council) == 2
    for member in council:
        assert member.is_active is True
        assert member.parent_id == head.id
        assert member.ethos_id is not None
    
    # Verify Lead 20001
    lead = db_session.query(LeadAgent).filter_by(agentium_id="20001").first()
    assert lead is not None
    assert lead.is_active is True
    assert lead.parent_id == head.id


@pytest.mark.asyncio
async def test_create_genesis_agents_idempotent(db_session: Session):
    """Test that running create_genesis_agents twice doesn't duplicate."""
    await create_genesis_agents(db_session)
    result2 = await create_genesis_agents(db_session)
    
    # Should return same objects, not create duplicates
    assert result2["head"].id == result2["head"].id
    assert len(result2["council"]) == 2
    
    # Verify DB has exactly one of each
    head_count = db_session.query(HeadOfCouncil).filter_by(agentium_id="00001").count()
    council_count = db_session.query(CouncilMember).filter(
        CouncilMember.agentium_id.in_(["10001", "10002"])
    ).count()
    lead_count = db_session.query(LeadAgent).filter_by(agentium_id="20001").count()
    
    assert head_count == 1
    assert council_count == 2
    assert lead_count == 1
```

- [ ] **Step 2: Run the test**

```bash
cd backend
pytest tests/load/test_seed_db.py -v
```

Expected: Both tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/tests/load/test_seed_db.py
git commit -m "test(load): add unit tests for create_genesis_agents"
```

---

### Task 3: Run full CI load test locally (integration verification)

**Files:**
- No new files (uses existing CI workflow components)

**Interfaces:**
- Consumes: Updated seed_db.py, existing Locust test suite
- Produces: Verification that WebSocket auth now passes

- [ ] **Step 1: Start test infrastructure**

```bash
docker compose -f docker-compose.test.yml up -d
```

- [ ] **Step 2: Wait for healthy services**

```bash
for i in {1..30}; do
  healthy=$(docker compose -f docker-compose.test.yml ps | grep -ci "healthy" || true)
  [ "$healthy" -eq 3 ] && break
  sleep 2
done
```

- [ ] **Step 3: Initialize database and run seed**

```bash
cd backend
alembic upgrade head
TESTING=true DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test python tests/load/seed_db.py
```

- [ ] **Step 4: Start backend server**

```bash
DATABASE_URL=postgresql://agentium:agentium@localhost:5432/agentium_test \
REDIS_URL=redis://localhost:6379/1 \
CELERY_BROKER_URL=redis://localhost:6379/1 \
CELERY_RESULT_BACKEND=redis://localhost:6379/1 \
CHROMA_HOST=localhost \
CHROMA_PORT=8001 \
CELERY_TASK_ALWAYS_EAGER=true \
TESTING=true \
PYTHONPATH=$(pwd) \
nohup python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000 &> /tmp/backend.log &
sleep 10
curl -sf http://localhost:8000/api/health
```

- [ ] **Step 5: Run Locust load test (scaled down for local)**

```bash
cd backend/tests/load
locust \
  --host http://localhost:8000 \
  --users 10 \
  --spawn-rate 2 \
  --run-time 60s \
  --headless \
  --html locust_report.html
```

Expected: WebSocket `ws:connect_and_auth` shows 0% failure rate

- [ ] **Step 6: Check Locust report**

```bash
cat locust_report.html | grep -A 10 "ws:connect_and_auth"
```

Expected: 0 failures for ws:connect_and_auth

- [ ] **Step 7: Cleanup**

```bash
docker compose -f docker-compose.test.yml down
```

- [ ] **Step 8: Commit any final adjustments**

```bash
git add -A
git commit -m "fix(load-test): final adjustments after local verification"
```

---

### Task 4: Verify CI pipeline passes

**Files:**
- No changes (uses existing `.github/workflows/integration-tests.yml`)

**Interfaces:**
- Consumes: All previous tasks
- Produces: Green CI build

- [ ] **Step 1: Push changes to trigger CI**

```bash
git push origin main
```

- [ ] **Step 2: Monitor GitHub Actions**

Watch the `integration-tests.yml` → `performance-tests` job

Expected: Job completes in <5 minutes with WebSocket auth 0% failure

- [ ] **Step 3: If CI fails, debug and iterate**

Check Locust report artifact for failure details

---

## Execution Handoff

**Plan complete and saved to** `docs/superpowers/plans/2026-11-07-fix-ci-load-test-websocket-auth.md`

**Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**