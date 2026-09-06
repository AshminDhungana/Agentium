# Missing Agent Detection & Re-creation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `verify_and_repair()` method to `InitializationService` that detects and recreates missing genesis agents (Head 00001, Council 10001/10002, Lead 20001), with integration points at startup, API, and Celery periodic task.

**Architecture:** Extend existing `InitializationService` class with a new idempotent verification method that reuses existing agent creation logic (`_create_head_of_council`, `_create_council_members`, `_create_default_lead`). Three invocation paths: FastAPI lifespan, REST endpoint, and Celery beat task.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Celery 5.3, PostgreSQL

---

## Global Constraints

- Use existing `InitializationService` creation methods — no duplicate logic
- `force_exact_ids=True` by default: attempt exact genesis IDs first; if occupied by different agent type, use next available + warning
- Idempotent: safe to run repeatedly, produces same result
- Transactional: flush per agent, single commit at end, rollback on error
- Audit every recreation to `AuditLog` (category: `GOVERNANCE`, action: `agent_recreated`)
- Graceful degradation: if API key unavailable, log warning but continue (unlike genesis)
- No database migration required
- Configuration via env vars: `AGENT_VERIFICATION_ENABLED`, `AGENT_VERIFICATION_INTERVAL_SECONDS`, `AGENT_VERIFICATION_EXACT_IDS`

---

## File Structure Map

| File | Responsibility |
|------|----------------|
| `backend/services/initialization_service.py` | Core `verify_and_repair()` method |
| `backend/main.py` | Lifespan integration |
| `backend/api/routes/agents.py` | REST endpoint `POST /api/v1/agents/verify` |
| `backend/services/tasks/verification_tasks.py` | Celery task (new file) |
| `backend/celery_app.py` | Beat schedule registration |
| `tests/services/test_initialization_service.py` | Unit tests (new file) |
| `tests/api/test_agents_verify.py` | API integration tests (new file) |

---

## Task 1: Add `verify_and_repair()` to InitializationService

**Files:**
- Modify: `backend/services/initialization_service.py`
- Test: `tests/services/test_initialization_service.py`

**Interfaces:**
- Produces: `async def verify_and_repair(self, db: Session, force_exact_ids: bool = True) -> Dict[str, Any]`

### Step 1: Write failing unit test for `verify_and_repair()` — all agents present

```python
# tests/services/test_initialization_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.orm import Session
from backend.services.initialization_service import InitializationService
from backend.models.entities.agents import HeadOfCouncil, CouncilMember, LeadAgent, AgentStatus


class TestVerifyAndRepair:
    @pytest.fixture
    def mock_db(self):
        return MagicMock(spec=Session)

    @pytest.fixture
    def init_service(self, mock_db):
        with patch("backend.services.initialization_service.get_vector_store"), \
             patch("backend.services.initialization_service.get_knowledge_service"):
            return InitializationService(db=mock_db)

    @pytest.mark.asyncio
    async def test_verify_and_repair_all_present(self, init_service, mock_db):
        """When all 4 genesis agents exist, return status ok with no recreated."""
        # Setup: mock queries to return existing agents
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        
        council1 = MagicMock(spec=CouncilMember)
        council1.agentium_id = "10001"
        council1.is_active = True
        
        council2 = MagicMock(spec=CouncilMember)
        council2.agentium_id = "10002"
        council2.is_active = True
        
        lead = MagicMock(spec=LeadAgent)
        lead.agentium_id = "20001"
        lead.is_active = True

        # Configure query chains
        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            head,    # Head 00001
            council1, # Council 10001
            council2, # Council 10002
            lead,     # Lead 20001
        ]

        result = await init_service.verify_and_repair(mock_db)

        assert result["status"] == "ok"
        assert result["checked"] == 4
        assert result["missing"] == []
        assert result["recreated"] == []
        assert result["warnings"] == []
        assert all(d["status"] == "ok" for d in result["details"].values())
```

### Step 2: Run test to verify it fails

```bash
cd E:\Ongoing Projects\Agentium
pytest tests/services/test_initialization_service.py::TestVerifyAndRepair::test_verify_and_repair_all_present -v
```
Expected: FAIL — `AttributeError: 'InitializationService' object has no attribute 'verify_and_repair'`

### Step 3: Implement `verify_and_repair()` method

Add to `InitializationService` class in `backend/services/initialization_service.py` (after `_clear_existing_data` method, before `_log`):

```python
    async def verify_and_repair(
        self,
        db: Session,
        force_exact_ids: bool = True
    ) -> Dict[str, Any]:
        """
        Verify all required genesis agents exist; recreate missing ones.

        Required agents:
        - Head of Council: 00001
        - Council Members: 10001, 10002
        - Lead Agent: 20001

        Args:
            db: Database session
            force_exact_ids: If True, attempt exact genesis IDs first.
                             If occupied by different agent, use next available + warning.

        Returns:
            Repair report dict with status, checked, missing, recreated, warnings, details.
        """
        required_agents = [
            {"id": "00001", "model": HeadOfCouncil, "creator": self._create_head_of_council, "tier": "head"},
            {"id": "10001", "model": CouncilMember, "creator": lambda: self._create_council_members(head)[0], "tier": "council"},
            {"id": "10002", "model": CouncilMember, "creator": lambda: self._create_council_members(head)[1], "tier": "council"},
            {"id": "20001", "model": LeadAgent, "creator": lambda: self._create_default_lead(head), "tier": "lead"},
        ]

        # First, ensure Head exists (needed as parent for others)
        head = db.query(HeadOfCouncil).filter_by(agentium_id="00001", is_active=True).first()
        if not head:
            head = await self._create_head_of_council()
            db.flush()

        results = {
            "status": "ok",
            "checked": 0,
            "missing": [],
            "recreated": [],
            "warnings": [],
            "details": {},
        }

        for agent_spec in required_agents:
            agent_id = agent_spec["id"]
            model = agent_spec["model"]
            creator = agent_spec["creator"]
            tier = agent_spec["tier"]

            results["checked"] += 1

            # Check if agent exists and is active
            existing = db.query(model).filter_by(agentium_id=agent_id, is_active=True).first()

            if existing:
                results["details"][agent_id] = {"status": "ok", "existed": True}
                continue

            # Agent missing — attempt recreation
            results["missing"].append(agent_id)

            # Check if exact ID slot is occupied by a different agent
            if force_exact_ids:
                occupied = db.query(Agent).filter_by(agentium_id=agent_id).first()
                if occupied:
                    results["warnings"].append(
                        f"Slot {agent_id} occupied by {occupied.agent_type.value} "
                        f"({occupied.agentium_id}); using next available ID in tier"
                    )
                    force_exact_for_this = False
                else:
                    force_exact_for_this = True
            else:
                force_exact_for_this = False

            try:
                # Temporarily override ID generation if we want exact ID
                # The creator methods use ReincarnationService which respects gaps
                # For exact ID, we need to ensure the slot is free (checked above)
                new_agent = await creator()
                actual_id = new_agent.agentium_id

                if force_exact_for_this and actual_id != agent_id:
                    results["warnings"].append(
                        f"Expected {agent_id} but got {actual_id} (ID generation chose next available)"
                    )

                results["recreated"].append(actual_id)
                results["details"][agent_id] = {
                    "status": "recreated",
                    "existed": False,
                    "new_id": actual_id,
                }

                # Audit log
                audit = AuditLog.log(
                    level=AuditLevel.INFO,
                    category=AuditCategory.GOVERNANCE,
                    actor_type="system",
                    actor_id="VERIFICATION",
                    action="agent_recreated",
                    target_type="agent",
                    target_id=actual_id,
                    description=f"Genesis agent {agent_id} recreated as {actual_id} during verification",
                    meta_data={
                        "requested_id": agent_id,
                        "actual_id": actual_id,
                        "tier": tier,
                        "force_exact_ids": force_exact_for_this,
                    }
                )
                db.add(audit)

            except Exception as e:
                self._log("ERROR", f"Failed to recreate {agent_id}: {e}")
                results["details"][agent_id] = {
                    "status": "error",
                    "existed": False,
                    "error": str(e),
                }
                results["status"] = "error"

        # Commit all changes
        if results["status"] != "error":
            try:
                db.commit()
                if results["recreated"]:
                    results["status"] = "repaired"
            except Exception as e:
                db.rollback()
                results["status"] = "error"
                results["warnings"].append(f"Commit failed: {e}")
        else:
            db.rollback()

        return results
```

### Step 4: Run test to verify it passes

```bash
pytest tests/services/test_initialization_service.py::TestVerifyAndRepair::test_verify_and_repair_all_present -v
```
Expected: PASS

### Step 5: Write failing test — missing agents recreated

```python
# tests/services/test_initialization_service.py (add to TestVerifyAndRepair class)

    @pytest.mark.asyncio
    async def test_verify_and_repair_missing_council_and_lead(self, init_service, mock_db):
        """When Council 10001 and Lead 20001 missing, they are recreated."""
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        head.id = 1

        council2 = MagicMock(spec=CouncilMember)
        council2.agentium_id = "10002"
        council2.is_active = True

        # Missing: 10001, 20001
        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            head,      # Head 00001 - exists
            None,      # Council 10001 - MISSING
            council2,  # Council 10002 - exists
            None,      # Lead 20001 - MISSING
        ]

        # Mock creator methods to return new agents
        new_council = MagicMock(spec=CouncilMember)
        new_council.agentium_id = "10001"
        new_lead = MagicMock(spec=LeadAgent)
        new_lead.agentium_id = "20001"

        init_service._create_council_members = AsyncMock(return_value=[new_council, MagicMock()])
        init_service._create_default_lead = AsyncMock(return_value=new_lead)

        with patch("backend.services.initialization_service.AuditLog") as mock_audit:
            result = await init_service.verify_and_repair(mock_db)

        assert result["status"] == "repaired"
        assert result["checked"] == 4
        assert set(result["missing"]) == {"10001", "20001"}
        assert set(result["recreated"]) == {"10001", "20001"}
        assert mock_db.commit.called
```

### Step 6: Run test, fix implementation, commit

```bash
pytest tests/services/test_initialization_service.py::TestVerifyAndRepair::test_verify_and_repair_missing_council_and_lead -v
# Fix any issues, then:
git add backend/services/initialization_service.py tests/services/test_initialization_service.py
git commit -m "feat: add verify_and_repair() to InitializationService with unit tests"
```

---

## Task 2: Add Lifespan Integration in main.py

**Files:**
- Modify: `backend/main.py`
- Test: `tests/api/test_lifespan_verification.py` (or integration test)

**Interfaces:**
- Consumes: `InitializationService.verify_and_repair()`

### Step 1: Write failing integration test

```python
# tests/api/test_lifespan_verification.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app


class TestLifespanVerification:
    @pytest.fixture
    def mock_db(self):
        return MagicMock()

    @pytest.mark.asyncio
    async def test_lifespan_calls_verify_and_repair(self, mock_db):
        """Lifespan should call verify_and_repair after init_db."""
        with patch("backend.main.get_db", return_value=iter([mock_db])), \
             patch("backend.main.init_db") as mock_init_db, \
             patch("backend.main.InitializationService") as mock_init_class, \
             TestClient(app) as client:
            
            mock_init_service = AsyncMock()
            mock_init_service.verify_and_repair = AsyncMock(return_value={
                "status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}
            })
            mock_init_class.return_value = mock_init_service

            # Trigger lifespan by making a request
            response = client.get("/health")
            assert response.status_code == 200

            mock_init_service.verify_and_repair.assert_called_once_with(mock_db)
```

### Step 2: Run test to verify it fails

```bash
pytest tests/api/test_lifespan_verification.py::TestLifespanVerification::test_lifespan_calls_verify_and_repair -v
```
Expected: FAIL — lifespan doesn't call verify_and_repair yet

### Step 3: Modify `main.py` lifespan

Find the `lifespan` async context manager in `backend/main.py`. Add after `init_db()` and before other initializations:

```python
        # Initialize database
        init_db()
        logger.info("Database initialized")

        # Verify and repair genesis agents
        if os.environ.get("AGENT_VERIFICATION_ENABLED", "true").lower() == "true":
            try:
                from backend.models.database import get_db_context
                from backend.services.initialization_service import InitializationService
                
                with get_db_context() as db:
                    init_service = InitializationService(db)
                    result = await init_service.verify_and_repair(db)
                    if result["status"] == "error":
                        logger.error(f"Agent verification failed: {result}")
                    elif result["status"] == "repaired":
                        logger.warning(f"Agent verification repaired missing agents: {result['recreated']}")
                    else:
                        logger.info("Agent verification: all genesis agents present")
            except Exception as e:
                logger.error(f"Agent verification error (non-blocking): {e}")
```

### Step 4: Run test to verify it passes

```bash
pytest tests/api/test_lifespan_verification.py::TestLifespanVerification::test_lifespan_calls_verify_and_repair -v
```
Expected: PASS

### Step 5: Commit

```bash
git add backend/main.py tests/api/test_lifespan_verification.py
git commit -m "feat: add agent verification to FastAPI lifespan"
```

---

## Task 3: Add REST API Endpoint

**Files:**
- Modify: `backend/api/routes/agents.py` (or create if not exists)
- Test: `tests/api/test_agents_verify.py`

**Interfaces:**
- Produces: `POST /api/v1/agents/verify` → returns verification report

### Step 1: Write failing API test

```python
# tests/api/test_agents_verify.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app


class TestAgentsVerifyEndpoint:
    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.fixture
    def auth_headers(self):
        return {"Authorization": "Bearer test-admin-token"}

    def test_verify_endpoint_requires_admin(self, client):
        """Non-admin users get 403."""
        response = client.post("/api/v1/agents/verify", headers={"Authorization": "Bearer user-token"})
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_verify_endpoint_returns_report(self, client, auth_headers):
        """Admin gets verification report."""
        with patch("backend.api.routes.agents.get_db", return_value=iter([MagicMock()])), \
             patch("backend.api.routes.agents.InitializationService") as mock_init_class:
            
            mock_service = AsyncMock()
            mock_service.verify_and_repair = AsyncMock(return_value={
                "status": "repaired",
                "checked": 4,
                "missing": ["10001"],
                "recreated": ["10001"],
                "warnings": [],
                "details": {
                    "00001": {"status": "ok", "existed": True},
                    "10001": {"status": "recreated", "existed": False, "new_id": "10001"},
                    "10002": {"status": "ok", "existed": True},
                    "20001": {"status": "ok", "existed": True},
                }
            })
            mock_init_class.return_value = mock_service

            response = client.post("/api/v1/agents/verify", headers=auth_headers)
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "repaired"
            assert data["recreated"] == ["10001"]
```

### Step 2: Run test to verify it fails

```bash
pytest tests/api/test_agents_verify.py::TestAgentsVerifyEndpoint::test_verify_endpoint_returns_report -v
```
Expected: FAIL — endpoint doesn't exist

### Step 3: Add endpoint to `backend/api/routes/agents.py`

```python
# Add to existing agents router or create new file
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from backend.models.database import get_db
from backend.services.initialization_service import InitializationService
from backend.api.middleware.auth import get_current_user
from backend.models.entities.user import User

router = APIRouter(prefix="/agents", tags=["agents"])


@router.post("/verify")
async def verify_agents(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Verify and repair missing genesis agents.
    
    Requires admin/sovereign access.
    """
    # Check admin permission
    if not current_user.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    
    init_service = InitializationService(db)
    result = await init_service.verify_and_repair(db)
    return result
```

Ensure the router is included in `main.py` (should already be if agents routes exist).

### Step 4: Run test to verify it passes

```bash
pytest tests/api/test_agents_verify.py -v
```
Expected: PASS

### Step 5: Commit

```bash
git add backend/api/routes/agents.py tests/api/test_agents_verify.py
git commit -m "feat: add POST /api/v1/agents/verify endpoint"
```

---

## Task 4: Create Celery Verification Task

**Files:**
- Create: `backend/services/tasks/verification_tasks.py`
- Modify: `backend/celery_app.py` (add beat schedule)
- Test: `tests/tasks/test_verification_tasks.py`

**Interfaces:**
- Produces: Celery task `verify_agents_task` registered in beat schedule

### Step 1: Write failing test for Celery task

```python
# tests/tasks/test_verification_tasks.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.tasks.verification_tasks import verify_agents_task


class TestVerificationTasks:
    @pytest.mark.asyncio
    async def test_verify_agents_task_executes(self):
        """Celery task runs verification and returns result."""
        mock_db = MagicMock()
        
        with patch("backend.services.tasks.verification_tasks.get_db_context") as mock_get_db, \
             patch("backend.services.tasks.verification_tasks.InitializationService") as mock_init_class:
            
            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            
            mock_service = AsyncMock()
            mock_service.verify_and_repair = AsyncMock(return_value={
                "status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}
            })
            mock_init_class.return_value = mock_service

            result = verify_agents_task()
            
            assert result["status"] == "ok"
            mock_service.verify_and_repair.assert_called_once_with(mock_db)
```

### Step 2: Run test to verify it fails

```bash
pytest tests/tasks/test_verification_tasks.py::TestVerificationTasks::test_verify_agents_task_executes -v
```
Expected: FAIL — module doesn't exist

### Step 3: Create `backend/services/tasks/verification_tasks.py`

```python
"""
Celery tasks for agent verification.
"""
import asyncio
import logging
from celery import shared_task
from backend.celery_app import celery_app
from backend.models.database import get_db_context
from backend.services.initialization_service import InitializationService

logger = logging.getLogger(__name__)


@celery_app.task(
    name="backend.services.tasks.verification_tasks.verify_agents_task",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def verify_agents_task(self):
    """
    Periodic task to verify and repair missing genesis agents.
    
    Runs every AGENT_VERIFICATION_INTERVAL_SECONDS (default 300s).
    """
    try:
        with get_db_context() as db:
            init_service = InitializationService(db)
            result = asyncio.run(init_service.verify_and_repair(db))
            logger.info(f"Periodic agent verification: {result['status']} - checked: {result['checked']}, recreated: {result['recreated']}")
            return result
    except Exception as e:
        logger.error(f"Agent verification task failed: {e}")
        # Retry on transient failures
        raise self.retry(exc=e)
```

### Step 4: Register beat schedule in `backend/celery_app.py`

Find the `beat_schedule` dict and add:

```python
beat_schedule = {
    # ... existing tasks ...
    "verify-agents-every-5-minutes": {
        "task": "backend.services.tasks.verification_tasks.verify_agents_task",
        "schedule": 300.0,  # 5 minutes, configurable via env
    },
}
```

Make interval configurable:

```python
import os
VERIFICATION_INTERVAL = float(os.environ.get("AGENT_VERIFICATION_INTERVAL_SECONDS", "300"))

beat_schedule = {
    # ... existing ...
    "verify-agents-every-5-minutes": {
        "task": "backend.services.tasks.verification_tasks.verify_agents_task",
        "schedule": VERIFICATION_INTERVAL,
    },
}
```

### Step 5: Run test to verify it passes

```bash
pytest tests/tasks/test_verification_tasks.py -v
```
Expected: PASS

### Step 6: Commit

```bash
git add backend/services/tasks/verification_tasks.py backend/celery_app.py tests/tasks/test_verification_tasks.py
git commit -m "feat: add Celery periodic task for agent verification"
```

---

## Task 5: Add Configuration & Env Var Support

**Files:**
- Modify: `backend/services/initialization_service.py` (read env vars)
- Modify: `.env.example` (document new vars)
- Test: `tests/services/test_initialization_service.py` (config tests)

### Step 1: Write failing test for env var config

```python
# tests/services/test_initialization_service.py (add to TestVerifyAndRepair)

    @pytest.mark.asyncio
    async def test_verify_and_repair_respects_env_config(self, init_service, mock_db):
        """verify_and_repair respects AGENT_VERIFICATION_EXACT_IDS."""
        import os
        
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        head.id = 1

        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            head, None, None, None  # Only head exists
        ]

        # Test with force_exact_ids=False (simulating env var)
        with patch.dict(os.environ, {"AGENT_VERIFICATION_EXACT_IDS": "false"}):
            # Re-create service to pick up env var
            with patch("backend.services.initialization_service.get_vector_store"), \
                 patch("backend.services.initialization_service.get_knowledge_service"):
                service = InitializationService(db=mock_db)
                # The service should read env var in __init__ or method
                # For now, test the parameter directly
                result = await service.verify_and_repair(mock_db, force_exact_ids=False)

        assert result["status"] in ("repaired", "ok")
```

### Step 2: Run test to verify it fails

```bash
pytest tests/services/test_initialization_service.py::TestVerifyAndRepair::test_verify_and_repair_respects_env_config -v
```

### Step 3: Update `InitializationService.__init__` to read config

In `backend/services/initialization_service.py`, add to `__init__`:

```python
    def __init__(self, db: Optional[Session] = None) -> None:
        # ... existing init ...
        import os
        self.verification_enabled = os.environ.get("AGENT_VERIFICATION_ENABLED", "true").lower() == "true"
        self.verification_exact_ids = os.environ.get("AGENT_VERIFICATION_EXACT_IDS", "true").lower() == "true"
        self.verification_interval = int(os.environ.get("AGENT_VERIFICATION_INTERVAL_SECONDS", "300"))
```

Update `verify_and_repair` to use instance defaults:

```python
    async def verify_and_repair(
        self,
        db: Session,
        force_exact_ids: Optional[bool] = None
    ) -> Dict[str, Any]:
        if force_exact_ids is None:
            force_exact_ids = self.verification_exact_ids
        # ... rest of method
```

### Step 4: Update `.env.example`

Add to `.env.example`:

```bash
# Agent Verification
AGENT_VERIFICATION_ENABLED=true
AGENT_VERIFICATION_INTERVAL_SECONDS=300
AGENT_VERIFICATION_EXACT_IDS=true
```

### Step 5: Run tests, commit

```bash
pytest tests/services/test_initialization_service.py -v
git add backend/services/initialization_service.py .env.example tests/services/test_initialization_service.py
git commit -m "feat: add env var configuration for agent verification"
```

---

## Task 6: Integration Test — Full Verification Flow

**Files:**
- Test: `tests/integration/test_agent_verification_flow.py`

### Step 1: Write integration test

```python
# tests/integration/test_agent_verification_flow.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from fastapi.testclient import TestClient
from backend.main import app


class TestAgentVerificationFlow:
    """End-to-end test of agent verification across all triggers."""

    @pytest.fixture
    def client(self):
        return TestClient(app)

    @pytest.mark.asyncio
    async def test_full_verification_flow(self, client):
        """Test lifespan -> API -> Celery task consistency."""
        mock_db = MagicMock()
        
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        head.id = 1

        # All agents missing except head
        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            head, None, None, None
        ]

        new_council1 = MagicMock(spec=CouncilMember)
        new_council1.agentium_id = "10001"
        new_council2 = MagicMock(spec=CouncilMember)
        new_council2.agentium_id = "10002"
        new_lead = MagicMock(spec=LeadAgent)
        new_lead.agentium_id = "20001"

        with patch("backend.main.get_db_context") as mock_get_db, \
             patch("backend.api.routes.agents.get_db", return_value=iter([mock_db])), \
             patch("backend.services.tasks.verification_tasks.get_db_context") as mock_task_db, \
             patch("backend.services.initialization_service.InitializationService") as mock_init_class:

            mock_get_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_get_db.return_value.__exit__ = MagicMock(return_value=None)
            mock_task_db.return_value.__enter__ = MagicMock(return_value=mock_db)
            mock_task_db.return_value.__exit__ = MagicMock(return_value=None)

            mock_service = AsyncMock()
            mock_service.verify_and_repair = AsyncMock(side_effect=[
                # Lifespan call
                {"status": "repaired", "checked": 4, "missing": ["10001", "10002", "20001"], "recreated": ["10001", "10002", "20001"], "warnings": [], "details": {}},
                # API call (after lifespan, all exist)
                {"status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}},
                # Celery task call
                {"status": "ok", "checked": 4, "missing": [], "recreated": [], "warnings": [], "details": {}},
            ])
            mock_init_class.return_value = mock_service

            # 1. Simulate lifespan by making first request
            response = client.get("/health")
            assert response.status_code == 200

            # 2. Call API endpoint
            response = client.post("/api/v1/agents/verify", headers={"Authorization": "Bearer admin-token"})
            assert response.status_code == 200
            assert response.json()["status"] == "ok"

            # 3. Call Celery task directly
            from backend.services.tasks.verification_tasks import verify_agents_task
            result = verify_agents_task()
            assert result["status"] == "ok"

            # Verify all three calls happened
            assert mock_service.verify_and_repair.call_count == 3
```

### Step 2: Run test, fix, commit

```bash
pytest tests/integration/test_agent_verification_flow.py -v
git add tests/integration/test_agent_verification_flow.py
git commit -m "test: add integration test for full agent verification flow"
```

---

## Task 7: Additional Unit Tests for Edge Cases

**Files:**
- Modify: `tests/services/test_initialization_service.py`

### Step 1: Add edge case tests

```python
# tests/services/test_initialization_service.py (add to TestVerifyAndRepair)

    @pytest.mark.asyncio
    async def test_verify_and_repair_exact_id_occupied_by_wrong_type(self, init_service, mock_db):
        """When exact ID slot has wrong agent type, use next available + warning."""
        head = MagicMock(spec=HeadOfCouncil)
        head.agentium_id = "00001"
        head.is_active = True
        head.id = 1

        # Slot 10001 occupied by a TaskAgent (wrong type)
        wrong_agent = MagicMock()
        wrong_agent.agentium_id = "10001"
        wrong_agent.agent_type = MagicMock(value="task_agent")
        wrong_agent.is_active = True

        council2 = MagicMock(spec=CouncilMember)
        council2.agentium_id = "10002"
        council2.is_active = True

        lead = MagicMock(spec=LeadAgent)
        lead.agentium_id = "20001"
        lead.is_active = True

        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            head,           # Head 00001
            wrong_agent,    # Council 10001 - occupied by wrong type
            council2,       # Council 10002
            lead,           # Lead 20001
        ]
        # Second query for Agent (base class) to check occupation
        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            head, wrong_agent, council2, lead,  # model-specific queries
            wrong_agent,  # Agent base query for 10001 occupation check
        ]

        new_council = MagicMock(spec=CouncilMember)
        new_council.agentium_id = "10003"  # Next available
        init_service._create_council_members = AsyncMock(return_value=[new_council, council2])

        with patch("backend.services.initialization_service.AuditLog"):
            result = await init_service.verify_and_repair(mock_db, force_exact_ids=True)

        assert result["status"] == "repaired"
        assert "10001" in result["missing"]
        assert "10003" in result["recreated"]
        assert any("occupied by" in w for w in result["warnings"])

    @pytest.mark.asyncio
    async def test_verify_and_repair_head_missing_creates_head(self, init_service, mock_db):
        """When Head 00001 missing, it is recreated first (parent for others)."""
        council1 = MagicMock(spec=CouncilMember)
        council1.agentium_id = "10001"
        council1.is_active = True

        mock_db.query.return_value.filter_by.return_value.first.side_effect = [
            None,      # Head 00001 - MISSING
            council1,  # Council 10001
            None,      # Council 10002
            None,      # Lead 20001
        ]

        new_head = MagicMock(spec=HeadOfCouncil)
        new_head.agentium_id = "00001"
        new_head.id = 1
        new_council2 = MagicMock(spec=CouncilMember)
        new_council2.agentium_id = "10002"
        new_lead = MagicMock(spec=LeadAgent)
        new_lead.agentium_id = "20001"

        init_service._create_head_of_council = AsyncMock(return_value=new_head)
        init_service._create_council_members = AsyncMock(return_value=[council1, new_council2])
        init_service._create_default_lead = AsyncMock(return_value=new_lead)

        with patch("backend.services.initialization_service.AuditLog"):
            result = await init_service.verify_and_repair(mock_db)

        assert result["status"] == "repaired"
        assert "00001" in result["recreated"]
        assert mock_db.flush.called  # Head flushed before children created
```

### Step 2: Run tests, commit

```bash
pytest tests/services/test_initialization_service.py -v
git add tests/services/test_initialization_service.py
git commit -m "test: add edge case tests for verify_and_repair"
```

---

## Task 8: Documentation Update

**Files:**
- Modify: `docs/superpowers/specs/2026-09-06-missing-agent-detection-recreation-design.md` (add implementation notes if needed)
- Create: `docs/agent-verification.md` (optional user-facing doc)

### Step 1: Update spec with implementation notes (optional)

Add a brief "Implementation Notes" section to the spec referencing the tasks above.

### Step 2: Commit any doc updates

```bash
git add docs/
git commit -m "docs: update agent verification documentation"
```

---

## Execution Order Summary

| Task | Dependencies | Deliverable |
|------|--------------|-------------|
| 1. Core method + unit tests | None | `verify_and_repair()` working |
| 2. Lifespan integration | Task 1 | Startup verification |
| 3. REST endpoint | Task 1 | `POST /api/v1/agents/verify` |
| 4. Celery task + beat | Task 1 | Periodic verification |
| 5. Config/env vars | Task 1 | Configurable behavior |
| 6. Integration test | Tasks 1-4 | E2E validation |
| 7. Edge case tests | Task 1 | Robustness |
| 8. Documentation | All | Updated docs |

---

## Verification Checklist

After all tasks complete, verify:

- [ ] `pytest tests/services/test_initialization_service.py -v` — all pass
- [ ] `pytest tests/api/test_agents_verify.py -v` — all pass
- [ ] `pytest tests/tasks/test_verification_tasks.py -v` — all pass
- [ ] `pytest tests/integration/test_agent_verification_flow.py -v` — passes
- [ ] `docker compose up` — startup logs show verification running
- [ ] `curl -X POST /api/v1/agents/verify` — returns report
- [ ] Celery beat triggers task every 5 min — check logs
- [ ] AuditLog entries created for each recreation
- [ ] TODO.md item 6.5.3 marked `[x]`

---

**Plan complete and saved to `docs/superpowers/plans/2026-09-06-missing-agent-detection-recreation-plan.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**