"""Integration tests for drag-and-drop agent reassignment."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from unittest.mock import AsyncMock

from backend.main import app
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.models.database import get_db as get_db_dependency
from backend.core.auth import get_current_active_user

# Re-use the test DB session from the main integration test conftest
# If no conftest.py exists with a test_db fixture, define a simple override here.

def _bypass_auth():
    """Override dependency so tests don't need a real JWT."""
    app.dependency_overrides[get_current_active_user] = lambda: {
        "id": 1,
        "username": "test_user",
        "is_active": True,
    }

def test_reassign_agent_allow(client, seeded_db):
    """Test ALLOW: valid reassignment of a task agent to a new Lead."""
    _bypass_auth()
    db_session = seeded_db

    # Reuse the Head (00001) created by genesis
    head = db_session.query(Agent).filter_by(agentium_id="00001").first()
    assert head is not None, "Genesis should have created Head 00001"
    # Create Lead A (20001)
    lead_a = Agent(
        agentium_id="20001",
        name="Lead A",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        parent=head,
    )
    # Create Lead B (20002)
    lead_b = Agent(
        agentium_id="20002",
        name="Lead B",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        parent=head,
    )
    # Create Task Agent (30101) under Lead A
    task = Agent(
        agentium_id="30101",
        name="Task Agent 1",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        parent=lead_a,
    )

    db_session.add_all([lead_a, lead_b, task])
    db_session.commit()

    response = client.patch(
        "/api/v1/agents/30101/parent",
        json={"new_parent_id": "20002", "reason": "Test reassignment"},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["constitutional_verdict"] == "ALLOW"
    assert data["old_parent_id"] == "20001"
    assert data["new_parent_id"] == "20002"
    assert data["success"] is True

    # Verify DB state
    updated = db_session.query(Agent).filter_by(agentium_id="30101").first()
    assert updated.parent.agentium_id == "20002"

    # Verify audit log
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "agent_reassigned")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.level == AuditLevel.INFO
    assert audit.category == AuditCategory.AGENT_LIFECYCLE


def test_reassign_agent_block(client, db_session):
    """Test BLOCK: reassignment that violates hierarchy (e.g., Council under Task)."""
    _bypass_auth()

    head = Agent(
        agentium_id="00001",
        name="Head",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
    )
    # Create a Council Member (1xxxx) and a Lead (2xxxx)
    council = Agent(
        agentium_id="10001",
        name="Council Member",
        agent_type=AgentType.COUNCIL_MEMBER,
        status=AgentStatus.ACTIVE,
        parent=head,
    )
    lead = Agent(
        agentium_id="20001",
        name="Lead",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        parent=head,
    )

    db_session.add_all([head, council, lead])
    db_session.commit()

    # Mock the guard to return BLOCK (real guard may not have this exact rule)
    from unittest.mock import patch

    with patch("backend.api.routes.reassign_routes.ConstitutionalGuard") as MockGuard:
        mock_guard = MockGuard.return_value
        mock_guard.initialize = AsyncMock()

        async def mock_check(*args, **kwargs):
            from backend.core.constitutional_guard import ConstitutionalDecision, Verdict, ViolationSeverity
            return ConstitutionalDecision(
                verdict=Verdict.BLOCK,
                severity=ViolationSeverity.CRITICAL,
                explanation="Lead (2xxxx) cannot supervise Council member (1xxxx).",
                citations=["Article 3 – Hierarchy Inversion"],
            )

        mock_guard.check_action = mock_check

        # Attempt: Move Council under Lead (lower tier → higher tier is illegal)
        response = client.patch(
            "/api/v1/agents/10001/parent",
            json={"new_parent_id": "20001", "reason": "Test block"},
        )

    assert response.status_code == 403
    data = response.json()
    # Error response shape: {error, code, detail}
    assert data["detail"]["verdict"] == "BLOCK"
    assert "cannot supervise" in data["detail"]["explanation"]

    # Verify no DB mutation
    db_session.refresh(council)
    assert council.parent.agentium_id == "00001"

    # Verify constitutional audit log
    audit = (
        db_session.query(AuditLog)
        .filter(AuditLog.action == "constitutional_check:reassign_agent")
        .order_by(AuditLog.created_at.desc())
        .first()
    )
    assert audit is not None
    assert audit.level == AuditLevel.CRITICAL
    assert audit.category == AuditCategory.CONSTITUTION


def test_reassign_guard_vote_required(client, db_session):
    """Test VOTE_REQUIRED: simulated scenario by mocking guard."""
    _bypass_auth()

    # This test stubs the guard to return VOTE_REQUIRED
    # In a real scenario, the guard would return VOTE_REQUIRED for
    # reassignments affecting >3 agents.
    head = Agent(
        agentium_id="00001",
        name="Head",
        agent_type=AgentType.HEAD_OF_COUNCIL,
        status=AgentStatus.ACTIVE,
    )
    lead_a = Agent(
        agentium_id="20001",
        name="Lead A",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        parent=head,
    )
    lead_b = Agent(
        agentium_id="20002",
        name="Lead B",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        parent=head,
    )
    task = Agent(
        agentium_id="30101",
        name="Task Agent",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        parent=lead_a,
    )

    db_session.add_all([head, lead_a, lead_b, task])
    db_session.commit()

    # For this test, we patch the guard to return VOTE_REQUIRED
    from unittest.mock import patch

    with patch("backend.api.routes.reassign_routes.ConstitutionalGuard") as MockGuard:
        mock_guard = MockGuard.return_value
        mock_guard.initialize = AsyncMock()

        async def mock_check(*args, **kwargs):
            from backend.core.constitutional_guard import ConstitutionalDecision, Verdict, ViolationSeverity
            return ConstitutionalDecision(
                verdict=Verdict.VOTE_REQUIRED,
                severity=ViolationSeverity.MEDIUM,
                explanation="Affects >3 agents – Council vote required",
                citations=["Article 5 – Multi-agent reassignments"],
            )

        mock_guard.check_action = mock_check

        response = client.patch(
            "/api/v1/agents/30101/parent",
            json={"new_parent_id": "20002", "reason": "Test vote required"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["constitutional_verdict"] == "VOTE_REQUIRED"
    assert data["requires_vote"] is True
    assert "Council vote" in data["message"]

    # Verify no DB mutation (agent stays under original parent)
    db_session.refresh(task)
    assert task.parent.agentium_id == "20001"
