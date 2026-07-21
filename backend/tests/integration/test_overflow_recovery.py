"""
Tests for the Head-of-Council overflow recovery flow (Task 7.1).

These are integration tests: they need a real Postgres + Redis (the
`db_session` / `redis_client` fixtures from tests/integration/conftest.py).

Acceptance criteria covered:
  * Simulated full-capacity scenario triggers the temporary-Head review flow.
  * Idle agents are correctly identified and safely reclaimed.
  * New-task assignment resumes automatically once slots are freed (flag cleared).
  * The temporary instance is confirmed terminated afterward.
"""

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    HeadOfCouncil,
    TaskAgent,
    LeadAgent,
    AgentStatus,
    AgentType,
)
from backend.models.entities.task import Task, TaskStatus
from backend.services.reincarnation_service import ReincarnationService
from backend.services.overflow_recovery import (
    OverflowRecoveryService,
    CapacityRecoveryInProgress,
)


def _make_idle_task_agent(db: Session, agentium_id: str, idle_days: int = 30) -> TaskAgent:
    """Create a non-persistent, idle Task Agent directly (bypasses spawn perms)."""
    from datetime import datetime, timedelta
    agent = TaskAgent(
        agentium_id=agentium_id,
        name=f"Idle {agentium_id}",
        description="idle test agent",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        is_active=True,
        is_persistent=False,
        idle_mode_enabled=False,
        last_idle_action_at=datetime.utcnow() - timedelta(days=idle_days),
        created_by_agentium_id="20001",
    )
    db.add(agent)
    db.flush()
    return agent


def test_overflow_review_reclaims_idle_agents(db_session: Session, redis_client):
    """Idle agents are identified, reclaimed, and the temp Head terminates."""
    # A lead to act as parent context (not strictly required by the review).
    _make_idle_task_agent(db_session, "30001")
    _make_idle_task_agent(db_session, "30002")

    started = OverflowRecoveryService.maybe_trigger_overflow_review(
        db_session, reason="exhausted"
    )
    assert started is True

    # Temp head terminated: its row is gone.
    remaining_heads = (
        db_session.query(HeadOfCouncil)
        .filter(HeadOfCouncil.is_temporary_overflow_head == True)  # noqa: E712
        .count()
    )
    assert remaining_heads == 0

    # Idle agents reclaimed (rows hard-deleted -> IDs freed).
    assert db_session.query(Agent).filter_by(agentium_id="30001").first() is None
    assert db_session.query(Agent).filter_by(agentium_id="30002").first() is None

    # Flag cleared -> new task assignment may resume.
    assert OverflowRecoveryService.is_review_in_progress() is False


def test_overflow_review_skips_agents_with_active_tasks(db_session: Session, redis_client):
    """Idle agents that still own active tasks are NOT reclaimed."""
    agent = _make_idle_task_agent(db_session, "30003")
    db_session.flush()

    # Give it an active task.
    task = Task(
        agentium_id="T-1",
        title="active task",
        task_type="execution",
        description="active task",
        status=TaskStatus.IN_PROGRESS,
        is_active=True,
        assigned_task_agent_ids=["30003"],
    )
    db_session.add(task)
    db_session.flush()

    OverflowRecoveryService.maybe_trigger_overflow_review(db_session, reason="exhausted")

    # Agent still present (skipped) and temp head terminated.
    assert db_session.query(Agent).filter_by(agentium_id="30003").first() is not None
    assert (
        db_session.query(HeadOfCouncil)
        .filter(HeadOfCouncil.is_temporary_overflow_head == True)  # noqa: E712
        .count()
        == 0
    )
    assert OverflowRecoveryService.is_review_in_progress() is False


def test_exhaustion_triggers_recovery_in_spawn(db_session: Session, redis_client, monkeypatch):
    """A full-capacity (ID-pool exhaustion) spawn failure triggers the review."""
    # Parent lead that passes the permission check.
    lead = LeadAgent(
        agentium_id="20001",
        name="Lead",
        description="lead",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        is_active=True,
        is_persistent=False,
        created_by_agentium_id="10001",
    )
    db_session.add(lead)
    db_session.flush()

    # Bypass capability check without genesis.
    import backend.services.reincarnation_service as rs
    monkeypatch.setattr(
        rs.CapabilityRegistry, "can_agent", staticmethod(lambda *a, **k: True)
    )
    # Simulate ID-pool exhaustion for the *task* tier only (so the temporary
    # Head can still mint its own 0xxxx ID and run the review).
    real_gen = rs.ReincarnationService._generate_next_id

    def _fake_generate_next_id(tier, db):
        if tier == "task":
            raise ValueError("ID pool exhausted for task tier")
        return real_gen(tier, db)

    monkeypatch.setattr(
        rs.ReincarnationService,
        "_generate_next_id",
        staticmethod(_fake_generate_next_id),
    )

    with pytest.raises(ValueError):
        rs.ReincarnationService.spawn_task_agent(
            parent=lead, name="T", description="d", db=db_session
        )

    # The recovery flow ran and cleaned up after itself.
    assert OverflowRecoveryService.is_review_in_progress() is False
    assert (
        db_session.query(HeadOfCouncil)
        .filter(HeadOfCouncil.is_temporary_overflow_head == True)  # noqa: E712
        .count()
        == 0
    )


def test_pause_gate_blocks_task_spawn_during_review(db_session: Session, redis_client):
    """While a review runs, Task-Agent spawns are paused via the gate."""
    OverflowRecoveryService.set_review_in_progress()

    lead = LeadAgent(
        agentium_id="20002",
        name="Lead2",
        description="lead",
        agent_type=AgentType.LEAD_AGENT,
        status=AgentStatus.ACTIVE,
        is_active=True,
        is_persistent=False,
        created_by_agentium_id="10001",
    )
    db_session.add(lead)
    db_session.flush()

    import backend.services.reincarnation_service as rs
    with pytest.raises(CapacityRecoveryInProgress):
        rs.ReincarnationService.spawn_task_agent(
            parent=lead, name="T", description="d", db=db_session
        )

    OverflowRecoveryService.clear_review_in_progress()
