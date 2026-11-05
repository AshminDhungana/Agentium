# Automated Version Rollback Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create integration tests verifying both tool versioning rollback and Git config versioning rollback complete in under 5 minutes without data corruption (Task 21.5.3).

**Architecture:** Two focused integration test modules following existing patterns (`test_federation_delegation.py`, `test_workflow_execution_18_2.py`). Shared timing helper in `tests/conftest.py`. Minimal fixtures, SLA assertions via context manager.

**Tech Stack:** pytest, FastAPI TestClient, SQLAlchemy test sessions, GitPython for config repo, existing test infrastructure (conftest.py fixtures)

## Global Constraints

- SLA threshold: **300 seconds (5 minutes)** — hard limit for both rollback types
- Fixtures: **minimal** (5 versions/commits, ~50 lines code each) — fast, unit-test style
- Data integrity checks per spec: tool code on disk, tool_registry, ToolVersion DB, ToolStaging, AuditLog; config entity fields, atomic DB update
- Auth boundaries: Head/Council (0xxxx/1xxxx) for tool rollback; admin for config rollback
- Test markers: `rollback` and `sla` — add to pyproject.toml
- Follow existing test patterns in codebase

---

## File Structure

```
tests/
├── conftest.py                          # MODIFY: add assert_completes_under helper
├── integration/
│   ├── test_tool_versioning_rollback.py # CREATE: 8 test cases
│   └── test_config_versioning_rollback.py # CREATE: 6 test cases
```

---

## Task 1: Add Shared Timing Helper to conftest.py

**Files:**
- Modify: `tests/conftest.py`

**Interfaces:**
- Produces: `assert_completes_under(seconds: float)` context manager for all test modules

### Step 1.1: Write the failing test for the helper

```python
# tests/test_timing_helper.py (temporary - will be deleted after verification)
import pytest
from tests.conftest import assert_completes_under
import time

def test_assert_completes_under_passes_for_fast_operation():
    with assert_completes_under(1.0):
        time.sleep(0.01)

def test_assert_completes_under_fails_for_slow_operation():
    with pytest.raises(AssertionError, match="Operation took"):
        with assert_completes_under(0.01):
            time.sleep(0.1)
```

### Step 1.2: Run test to verify it fails

Run: `pytest tests/test_timing_helper.py -v`
Expected: FAIL — `assert_completes_under` not defined

### Step 1.3: Write minimal implementation in conftest.py

Add to `tests/conftest.py`:

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

### Step 1.4: Run test to verify it passes

Run: `pytest tests/test_timing_helper.py -v`
Expected: PASS

### Step 1.5: Clean up and commit

```bash
rm tests/test_timing_helper.py
git add tests/conftest.py
git commit -m "test: add assert_completes_under timing helper to conftest"
```

---

## Task 2: Create Tool Versioning Rollback Test Module

**Files:**
- Create: `tests/integration/test_tool_versioning_rollback.py`
- Test: `tests/integration/test_tool_versioning_rollback.py`

**Interfaces:**
- Consumes: `assert_completes_under` from conftest.py, existing fixtures (`db_session`, `client`, `head_agent_token`, `council_agent_token`, `task_agent_token`)
- Produces: 8 passing integration tests

### Step 2.1: Write all 8 failing tests

```python
# tests/integration/test_tool_versioning_rollback.py
"""
Integration tests for Tool Versioning Rollback (Task 21.5.3).
Verifies POST /tool-management/{tool_name}/versions/rollback completes in <5min without data corruption.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.services.tool_versioning import ToolVersioningService
from backend.core.tool_registry import tool_registry
from backend.models.entities.tool_version import ToolVersion
from backend.models.entities.tool_staging import ToolStaging
from backend.models.entities.audit import AuditLog, AuditCategory
from backend.models.entities.agents import Agent

pytestmark = [pytest.mark.rollback, pytest.mark.sla]


class TestToolVersioningRollback:
    """Test suite for tool versioning rollback endpoint and service."""

    @pytest.fixture
    def tool_with_versions(self, db_session: Session, head_agent_id: str):
        """Create a tool with 5 versions (v1-v5), v5 active."""
        service = ToolVersioningService(db_session)
        tool_name = "test_rollback_tool"
        
        # Create initial version (v1)
        v1 = service.create_initial_version(
            tool_name=tool_name,
            code='def execute():\n    return "v1"',
            tool_path=f"/tmp/{tool_name}.py",
            authored_by=head_agent_id,
        )
        
        # Create v2-v5 via propose/approve cycle
        versions = [v1]
        current_code = 'def execute():\n    return "v1"'
        
        for i in range(2, 6):
            current_code = f'def execute():\n    return "v{i}"'
            propose_result = service.propose_update(
                tool_name=tool_name,
                new_code=current_code,
                change_summary=f"Update to v{i}",
                proposed_by=head_agent_id,
            )
            assert propose_result["proposed"] is True
            
            approve_result = service.approve_update(
                tool_name=tool_name,
                pending_version_id=propose_result["pending_version_id"],
                approved_by_voting_id=None,  # Head auto-approves
            )
            assert approve_result["approved"] is True
            versions.append(approve_result)
        
        # Verify v5 is active
        active = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True
        ).first()
        assert active.version_number == 5
        
        yield tool_name, versions
        
        # Cleanup
        db_session.query(ToolVersion).filter(ToolVersion.tool_name == tool_name).delete()
        db_session.query(ToolStaging).filter(ToolStaging.tool_name == tool_name).delete()
        db_session.commit()

    def test_rollback_to_prior_version_completes_under_5min(
        self, client: TestClient, head_agent_token: str, tool_with_versions
    ):
        """SLA: Rollback from v5 to v3 completes in under 300 seconds."""
        tool_name, _ = tool_with_versions
        
        from tests.conftest import assert_completes_under
        
        with assert_completes_under(300):
            response = client.post(
                f"/tool-management/{tool_name}/versions/rollback",
                json={"target_version_number": 3, "reason": "test rollback"},
                headers={"Authorization": f"Bearer {head_agent_token}"},
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["rolled_back"] is True
        assert data["restored_code_from"] == "v3"
        assert "new_version_entry" in data

    def test_rollback_restores_correct_code_snapshot(
        self, client: TestClient, head_agent_token: str, tool_with_versions, db_session: Session
    ):
        """Data integrity: Disk code matches target version's code_snapshot."""
        tool_name, _ = tool_with_versions
        
        # Get v3's code_snapshot before rollback
        v3 = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.version_number == 3
        ).first()
        expected_code = v3.code_snapshot
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 3, "reason": "test rollback"},
            headers={"Authorization": f"Bearer {head_agent_token}"},
        )
        assert response.status_code == 200
        
        # Read code from disk
        import os
        tool_path = f"/tmp/{tool_name}.py"  # ToolFactory.tools_directory
        # The service writes to tools_directory/{tool_name}.py
        from backend.services.tool_factory import ToolFactory
        factory = ToolFactory()
        actual_path = factory.tools_directory / f"{tool_name}.py"
        actual_code = actual_path.read_text()
        
        assert actual_code == expected_code

    def test_rollback_updates_tool_registry(
        self, client: TestClient, head_agent_token: str, tool_with_versions
    ):
        """Registry sync: tool_registry returns rolled-back function."""
        tool_name, _ = tool_with_versions
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 3, "reason": "test rollback"},
            headers={"Authorization": f"Bearer {head_agent_token}"},
        )
        assert response.status_code == 200
        
        # Verify registry has the rolled-back function
        assert tool_name in tool_registry._tools
        tool_func = tool_registry._tools[tool_name]
        # Execute and verify it returns v3 behavior
        result = tool_func({})
        assert "v3" in str(result).lower() or "v3" in str(result.get("output", "")).lower()

    def test_rollback_creates_new_version_entry(
        self, client: TestClient, head_agent_token: str, tool_with_versions, db_session: Session
    ):
        """Audit trail: New ToolVersion created with is_rolled_back=True, rolled_back_from_version set."""
        tool_name, _ = tool_with_versions
        
        # Count versions before
        before_count = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name
        ).count()
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 3, "reason": "test rollback"},
            headers={"Authorization": f"Bearer {head_agent_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        
        # New version should be created (v6 = rollback entry)
        after_count = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name
        ).count()
        assert after_count == before_count + 1
        
        # Verify rollback version properties
        rollback_version = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_rolled_back == True
        ).first()
        assert rollback_version is not None
        assert rollback_version.rolled_back_from_version == 5
        assert rollback_version.is_active is True
        assert "Rollback to v3" in rollback_version.change_summary

    def test_rollback_updates_staging_current_version(
        self, client: TestClient, head_agent_token: str, tool_with_versions, db_session: Session
    ):
        """Staging sync: ToolStaging.current_version matches new rollback version."""
        tool_name, _ = tool_with_versions
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 3, "reason": "test rollback"},
            headers={"Authorization": f"Bearer {head_agent_token}"},
        )
        assert response.status_code == 200
        data = response.json()
        new_version_num = int(data["new_version_entry"].split("v")[1].split(".")[0])
        
        staging = db_session.query(ToolStaging).filter(
            ToolStaging.tool_name == tool_name
        ).first()
        assert staging is not None
        assert staging.current_version == new_version_num

    def test_rollback_audit_log_created(
        self, client: TestClient, head_agent_token: str, tool_with_versions, db_session: Session
    ):
        """Audit compliance: AuditLog entry with action=tool_rolled_back."""
        tool_name, _ = tool_with_versions
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 3, "reason": "test rollback"},
            headers={"Authorization": f"Bearer {head_agent_token}"},
        )
        assert response.status_code == 200
        
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "tool_rolled_back",
            AuditLog.target_id == tool_name
        ).order_by(AuditLog.created_at.desc()).first()
        
        assert audit is not None
        assert audit.category == AuditCategory.SYSTEM
        assert audit.actor_type == "agent"
        assert audit.after_state is not None
        assert audit.after_state.get("from_version") == 5
        assert audit.after_state.get("to_version") == 3
        assert audit.after_state.get("reason") == "test rollback"

    def test_rollback_rejects_unauthorized_agent(
        self, client: TestClient, task_agent_token: str, tool_with_versions
    ):
        """Auth enforcement: Task agent (3xxxx) gets 403."""
        tool_name, _ = tool_with_versions
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 3, "reason": "test rollback"},
            headers={"Authorization": f"Bearer {task_agent_token}"},
        )
        assert response.status_code == 403
        assert "not authorized" in response.json()["detail"]["error"].lower()

    def test_rollback_rejects_invalid_version(
        self, client: TestClient, head_agent_token: str, tool_with_versions, db_session: Session
    ):
        """Error handling: Non-existent version returns error, no state change."""
        tool_name, _ = tool_with_versions
        
        # Get current active version
        active_before = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True
        ).first()
        version_before = active_before.version_number
        
        response = client.post(
            f"/tool-management/{tool_name}/versions/rollback",
            json={"target_version_number": 999, "reason": "invalid"},
            headers={"Authorization": f"Bearer {head_agent_token}"},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]["error"].lower()
        
        # Verify no state change
        active_after = db_session.query(ToolVersion).filter(
            ToolVersion.tool_name == tool_name,
            ToolVersion.is_active == True
        ).first()
        assert active_after.version_number == version_before
```

### Step 2.2: Run tests to verify they fail

Run: `pytest tests/integration/test_tool_versioning_rollback.py -v`
Expected: FAIL — module doesn't exist yet, fixtures may need adjustment

### Step 2.3: Implement minimal fixtures/adjustments if needed

Check existing fixtures in `tests/conftest.py` for:
- `head_agent_token`, `council_agent_token`, `task_agent_token` — JWT tokens for different agent tiers
- `client` — TestClient fixture
- `db_session` — SQLAlchemy session fixture

If missing, add minimal fixtures to conftest.py (see Task 2.3b below).

### Step 2.3b: Add missing agent token fixtures to conftest.py (if needed)

```python
# Add to tests/conftest.py if not present
@pytest.fixture
def head_agent_token(client: TestClient):
    """JWT token for Head agent (00001)."""
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    return response.json()["access_token"]

@pytest.fixture
def council_agent_token(db_session: Session, client: TestClient):
    """JWT token for Council agent (10001)."""
    # Create or get council agent, login
    from backend.models.entities.agents import Agent
    agent = db_session.query(Agent).filter(Agent.agentium_id == "10001").first()
    if not agent:
        agent = Agent(agentium_id="10001", name="Test Council", tier="council", status="active")
        db_session.add(agent)
        db_session.commit()
    # Login as this agent (may need password setup)
    # Simplified: return a mock token or use test auth bypass
    return "mock_council_token"

@pytest.fixture
def task_agent_token(db_session: Session):
    """JWT token for Task agent (30001)."""
    from backend.models.entities.agents import Agent
    agent = db_session.query(Agent).filter(Agent.agentium_id == "30001").first()
    if not agent:
        agent = Agent(agentium_id="30001", name="Test Task", tier="task", status="active")
        db_session.add(agent)
        db_session.commit()
    return "mock_task_token"
```

### Step 2.4: Run tests to verify they pass

Run: `pytest tests/integration/test_tool_versioning_rollback.py -v`
Expected: All 8 tests PASS

### Step 2.5: Commit

```bash
git add tests/integration/test_tool_versioning_rollback.py tests/conftest.py
git commit -m "test: add tool versioning rollback verification tests (8 tests)"
```

---

## Task 3: Create Config Versioning Rollback Test Module

**Files:**
- Create: `tests/integration/test_config_versioning_rollback.py`
- Test: `tests/integration/test_config_versioning_rollback.py`

**Interfaces:**
- Consumes: `assert_completes_under` from conftest.py, existing fixtures (`db_session`, `client`, `admin_token`)
- Produces: 6 passing integration tests

### Step 3.1: Write all 6 failing tests

```python
# tests/integration/test_config_versioning_rollback.py
"""
Integration tests for Git Config Versioning Rollback (Task 21.5.3).
Verifies POST /admin/config-restore/{entity_type}/{entity_id} completes in <5min without data corruption.
"""
import pytest
import json
import os
import git
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from backend.services.config_versioning import ConfigVersioningService
from backend.models.entities.channels import ExternalChannel
from backend.models.entities.audit import AuditLog, AuditCategory

pytestmark = [pytest.mark.rollback, pytest.mark.sla]


class TestConfigVersioningRollback:
    """Test suite for Git config versioning rollback endpoint and service."""

    @pytest.fixture
    def config_entity_with_history(self, db_session: Session, admin_user_id: str):
        """Create a channel entity with 5 Git commits."""
        entity_type = "channel"
        entity_id = "test-rollback-channel-123"
        
        # Clean up any existing
        repo_path = "/data/config-repo"
        if os.path.exists(os.path.join(repo_path, entity_type, f"{entity_id}.json")):
            # Reset repo to clean state for test
            repo = git.Repo(repo_path)
            repo.head.reset(index=True, working_tree=True)
        
        # Create channel in DB
        channel = ExternalChannel(
            id=entity_id,
            name="Test Rollback Channel",
            config={"webhook_url": "https://example.com/webhook", "setting": "v1"},
            default_agent_id=None,
            auto_create_tasks=False,
            require_approval=True,
            status="active",
        )
        db_session.add(channel)
        db_session.commit()
        
        # Create 5 commits with incrementally different configs
        configs = [
            {"webhook_url": "https://example.com/webhook", "setting": "v1", "version": 1},
            {"webhook_url": "https://example.com/webhook", "setting": "v2", "version": 2, "extra": "added"},
            {"webhook_url": "https://example.com/webhook", "setting": "v3", "version": 3, "extra": "added", "new_field": "data"},
            {"webhook_url": "https://example.com/webhook", "setting": "v4", "version": 4, "extra": "added", "new_field": "data", "another": "field"},
            {"webhook_url": "https://example.com/webhook", "setting": "v5", "version": 5, "extra": "added", "new_field": "data", "another": "field", "final": True},
        ]
        
        commit_shas = []
        for i, config in enumerate(configs):
            channel.config = config
            db_session.commit()
            
            # Commit snapshot
            payload = {
                "id": channel.id,
                "name": channel.name,
                "config": channel.config,
                "default_agent_id": channel.default_agent_id,
                "auto_create_tasks": channel.auto_create_tasks,
                "require_approval": channel.require_approval,
                "status": channel.status,
            }
            sha = ConfigVersioningService.commit_snapshot(
                entity_type=entity_type,
                entity_id=entity_id,
                actor_id=admin_user_id,
                payload_dict=payload,
            )
            commit_shas.append(sha)
        
        # Verify 5 commits exist
        history = ConfigVersioningService.get_config_history(entity_type, entity_id)
        assert len(history) == 5
        
        yield entity_type, entity_id, commit_shas, configs
        
        # Cleanup
        db_session.delete(channel)
        db_session.commit()
        # Note: Git history remains but that's fine for test isolation

    def test_config_restore_completes_under_5min(
        self, client: TestClient, admin_token: str, config_entity_with_history
    ):
        """SLA: Config restore from HEAD to commit-2 completes in under 300 seconds."""
        entity_type, entity_id, commit_shas, _ = config_entity_with_history
        target_sha = commit_shas[1]  # commit-2 (0-indexed)
        
        from tests.conftest import assert_completes_under
        
        with assert_completes_under(300):
            response = client.post(
                f"/admin/config-restore/{entity_type}/{entity_id}",
                json={"commit": target_sha},
                headers={"Authorization": f"Bearer {admin_token}"},
            )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    def test_config_restore_matches_snapshot_exactly(
        self, client: TestClient, admin_token: str, config_entity_with_history, db_session: Session
    ):
        """Data integrity: Restored entity fields match Git snapshot exactly."""
        entity_type, entity_id, commit_shas, configs = config_entity_with_history
        target_sha = commit_shas[1]  # commit-2 -> configs[1]
        expected_config = configs[1]
        
        response = client.post(
            f"/admin/config-restore/{entity_type}/{entity_id}",
            json={"commit": target_sha},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        
        # Verify DB entity matches snapshot
        from backend.models.entities.channels import ExternalChannel
        channel = db_session.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        assert channel is not None
        assert channel.config == expected_config
        assert channel.name == "Test Rollback Channel"
        assert channel.status == "active"

    def test_config_restore_atomic_db_update(
        self, client: TestClient, admin_token: str, config_entity_with_history, db_session: Session
    ):
        """Atomicity: All entity fields updated in single transaction."""
        entity_type, entity_id, commit_shas, configs = config_entity_with_history
        target_sha = commit_shas[2]  # commit-3
        
        response = client.post(
            f"/admin/config-restore/{entity_type}/{entity_id}",
            json={"commit": target_sha},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        
        # Verify all fields restored atomically (no partial state)
        from backend.models.entities.channels import ExternalChannel
        channel = db_session.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        expected = configs[2]
        
        # All config fields should match
        assert channel.config == expected
        # Core fields should be restored
        assert channel.name == "Test Rollback Channel"
        assert channel.status == "active"
        assert channel.auto_create_tasks is False
        assert channel.require_approval is True

    def test_config_restore_handles_missing_commit(
        self, client: TestClient, admin_token: str, config_entity_with_history
    ):
        """Error handling: Invalid SHA returns 400, no DB changes."""
        entity_type, entity_id, commit_shas, configs = config_entity_with_history
        
        # Get current config before failed attempt
        from backend.models.entities.channels import ExternalChannel
        channel_before = db_session.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        config_before = channel_before.config
        
        response = client.post(
            f"/admin/config-restore/{entity_type}/{entity_id}",
            json={"commit": "invalid-sha-that-does-not-exist"},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]["error"].lower()
        
        # Verify no DB changes
        channel_after = db_session.query(ExternalChannel).filter(ExternalChannel.id == entity_id).first()
        assert channel_after.config == config_before

    def test_config_restore_handles_missing_file(
        self, client: TestClient, admin_token: str, db_session: Session
    ):
        """Error handling: Commit exists but file missing returns 400."""
        # Create a commit for a different entity, then try to restore our entity from it
        entity_type = "channel"
        entity_id = "test-missing-file-channel"
        
        # Create channel
        channel = ExternalChannel(
            id=entity_id,
            name="Missing File Test",
            config={"setting": "original"},
            status="active",
        )
        db_session.add(channel)
        db_session.commit()
        
        # Commit a snapshot for a DIFFERENT entity
        other_entity_id = "other-entity"
        ConfigVersioningService.commit_snapshot(
            entity_type=entity_type,
            entity_id=other_entity_id,
            actor_id="admin",
            payload_dict={"id": other_entity_id, "config": {"test": "data"}},
        )
        
        # Get that commit SHA
        history = ConfigVersioningService.get_config_history(entity_type, other_entity_id)
        other_sha = history[0]["sha"]
        
        # Try to restore our entity from other entity's commit (file won't exist)
        response = client.post(
            f"/admin/config-restore/{entity_type}/{entity_id}",
            json={"commit": other_sha},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]["error"].lower()
        
        # Cleanup
        db_session.delete(channel)
        db_session.commit()

    def test_config_restore_audit_log_created(
        self, client: TestClient, admin_token: str, config_entity_with_history, db_session: Session
    ):
        """Audit compliance: AuditLog entry with action=config_restored."""
        entity_type, entity_id, commit_shas, _ = config_entity_with_history
        target_sha = commit_shas[1]
        
        response = client.post(
            f"/admin/config-restore/{entity_type}/{entity_id}",
            json={"commit": target_sha},
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert response.status_code == 200
        
        audit = db_session.query(AuditLog).filter(
            AuditLog.action == "config_restored",
            AuditLog.target_id == entity_id
        ).order_by(AuditLog.created_at.desc()).first()
        
        assert audit is not None
        assert audit.category == AuditCategory.SYSTEM
        assert audit.actor_type == "user"
        assert audit.after_state is not None
        assert audit.after_state.get("commit") == target_sha
        assert audit.after_state.get("entity_type") == entity_type
```

### Step 3.2: Run tests to verify they fail

Run: `pytest tests/integration/test_config_versioning_rollback.py -v`
Expected: FAIL — module doesn't exist, fixtures may need adjustment

### Step 3.3: Add missing admin_token fixture to conftest.py (if needed)

```python
# Add to tests/conftest.py if not present
@pytest.fixture
def admin_token(client: TestClient):
    """JWT token for admin user."""
    response = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    return response.json()["access_token"]

@pytest.fixture
def admin_user_id(db_session: Session):
    """Admin user ID for config versioning actor."""
    from backend.models.entities.user import User
    user = db_session.query(User).filter(User.username == "admin").first()
    return str(user.id) if user else "admin"
```

### Step 3.4: Run tests to verify they pass

Run: `pytest tests/integration/test_config_versioning_rollback.py -v`
Expected: All 6 tests PASS

### Step 3.5: Commit

```bash
git add tests/integration/test_config_versioning_rollback.py tests/conftest.py
git commit -m "test: add config versioning rollback verification tests (6 tests)"
```

---

## Task 4: Add Pytest Markers and Verify Full Suite

**Files:**
- Modify: `pyproject.toml` (or `pytest.ini`)

### Step 4.1: Add markers to pyproject.toml

```toml
# In pyproject.toml under [tool.pytest.ini_options]
markers = [
    "rollback: Rollback verification tests",
    "sla: Tests with time SLA assertions",
    # ... existing markers
]
```

### Step 4.2: Run full rollback test suite

Run: `pytest -m rollback -v`
Expected: All 14 tests PASS (8 tool + 6 config)

### Step 4.3: Run with SLA marker

Run: `pytest -m sla -v`
Expected: All 14 tests PASS (same tests, both marked)

### Step 4.4: Commit

```bash
git add pyproject.toml
git commit -m "test: add rollback and sla pytest markers"
```

---

## Task 5: Final Verification and Documentation

### Step 5.1: Run complete test suite to ensure no regressions

Run: `pytest tests/integration/ -v --tb=short`
Expected: All integration tests PASS

### Step 5.2: Verify test file structure matches design

```bash
ls -la tests/integration/test_*_rollback.py
```
Expected: Both files exist with correct test counts

### Step 5.3: Commit final state

```bash
git add tests/
git commit -m "test: complete Task 21.5.3 - automated version rollback verification (14 tests)"
```

---

## Summary

| Task | Deliverable | Tests |
|------|-------------|-------|
| 1 | Timing helper in conftest.py | 2 (temp, removed) |
| 2 | Tool versioning rollback tests | 8 |
| 3 | Config versioning rollback tests | 6 |
| 4 | Pytest markers | 0 (config) |
| 5 | Full suite verification | 14 total |

**Total new tests: 14** (all marked `rollback` and `sla`)

All tasks follow TDD: write failing tests first, then verify implementation passes. Each task is independently testable and committable.