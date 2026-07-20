"""
Regression tests for Agentic-Loop Hardening (lifecycle contract).

Contract under test:
  1. Every agent runs its task to a terminal state (done / failed / escalated)
     — no silent stalls.
  2. The Head of Council (00001) is a persistent process for the system's whole
     lifetime and must never terminate while the system is running.
  3. The Head is exempt from the 7-day idle-liquidation rule AND every other
     auto-termination path.
  4. The heartbeat monitor + Reincarnation Service cover the Head specifically
     and auto-restart it from checkpoint if it crashes.

Key regression: force the Head to "crash" and assert it comes back under the
SAME identity (no minted 00002 that orphans the ~90 hardcoded lookups).
"""

import uuid
from datetime import datetime, timedelta
from contextlib import contextmanager
from unittest.mock import patch, AsyncMock

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    AgentStatus,
    AgentType,
    HeadOfCouncil,
)
from backend.models.entities.task import Task, TaskStatus, TaskType, TaskPriority
from backend.models.entities.audit import AuditLog
from backend.services.reincarnation_service import ReincarnationService
from backend.services.idle_governance import idle_governance
from backend.services.predictive_scaling import PredictiveScalingService
from backend.services.self_healing_service import SelfHealingService

pytestmark = pytest.mark.integration


# ─────────────────────────────────────────────────────────────────────────────
# Contract 2 / 4 — Head crash recovery revives IN PLACE
# ─────────────────────────────────────────────────────────────────────────────

def test_head_crash_recovered_in_place(seeded_db: Session):
    """
    Simulate the Head of Council (00001) crashing while WORKING with a stale
    heartbeat. The crash-recovery path must revive it under the SAME identity —
    status flipped back to ACTIVE, NO new Head ID minted (no 00002), and any
    interrupted task re-queued to itself.
    """
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None, "Genesis must seed Head 00001"

    # Give the Head an interrupted task to re-queue.
    task = Task(
        agentium_id="THEAD01",
        title="Head interrupted task",
        description="Task the Head was running when it crashed.",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.SOVEREIGN,
        assigned_task_agent_ids=["00001"],
        is_active=True,
    )
    seeded_db.add(task)
    seeded_db.flush()

    # Simulate a crash: Head stuck in WORKING with a stale heartbeat.
    head.status = AgentStatus.WORKING
    head.last_heartbeat_at = datetime.utcnow() - timedelta(minutes=10)
    head.current_task_id = task.id
    seeded_db.commit()

    result = SelfHealingService.detect_crashed_agents(seeded_db)

    # Head revived in place — same id, active, not replaced.
    seeded_db.refresh(head)
    assert head.is_active is True
    assert head.status == AgentStatus.ACTIVE
    assert head.agentium_id == "00001"
    assert head.terminated_at is None

    # No second Head identity was minted (the bug repair_head_incarnation.py
    # exists to fix after the fact — this must never happen again).
    head_ids = [
        h.agentium_id
        for h in seeded_db.query(Agent)
        .filter(Agent.agent_type == AgentType.HEAD_OF_COUNCIL)
        .all()
    ]
    assert head_ids == ["00001"], f"Unexpected Head identities minted: {head_ids}"

    # Interrupted task re-queued to the (same) Head, ready to resume.
    seeded_db.refresh(task)
    assert task.status == TaskStatus.ASSIGNED
    assert task.assigned_task_agent_ids == ["00001"]

    # Audit trail proving in-place recovery (not a fresh incarnation elsewhere).
    assert (
        seeded_db.query(AuditLog)
        .filter_by(action="head_crash_recovered_in_place")
        .count()
        >= 1
    )
    assert result["detected"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Contract 3 — Head exempt from EVERY auto-termination path
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_auto_liquidation_predicate_excludes_head(seeded_db: Session):
    """
    The central eligibility predicate must treat the Head of Council as NEVER
    auto-liquidatable, while a never-idle non-persistent worker IS eligible.
    This is the single source of truth every auto-termination path relies on.
    """
    from datetime import timedelta as _td

    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None

    threshold = datetime.utcnow() - _td(days=idle_governance.IDLE_THRESHOLD_DAYS)

    # Head is persistent + 00001 -> ineligible regardless of idle time.
    assert idle_governance.is_eligible_for_auto_liquidation(head, threshold) is False

    # A never-idle, non-persistent worker -> eligible (NULL last_idle_action_at).
    worker = Agent(
        agentium_id="39997",
        name="Predicate Worker",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        is_persistent=False,
        parent_id=head.id,
        created_by_agentium_id="00001",
        last_idle_action_at=None,
    )
    # An active, recently-idle worker -> NOT eligible.
    fresh = Agent(
        agentium_id="39996",
        name="Fresh Worker",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        is_persistent=False,
        parent_id=head.id,
        created_by_agentium_id="00001",
        last_idle_action_at=datetime.utcnow() - _td(days=1),
    )
    seeded_db.add_all([worker, fresh])
    seeded_db.commit()

    assert idle_governance.is_eligible_for_auto_liquidation(worker, threshold) is True
    assert idle_governance.is_eligible_for_auto_liquidation(fresh, threshold) is False


@pytest.mark.asyncio
async def test_head_exempt_from_all_auto_termination(seeded_db: Session):
    head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
    assert head is not None

    # 1) liquidate_agent must refuse the Head outright.
    with pytest.raises(ValueError):
        ReincarnationService.liquidate_agent(
            agent_id="00001",
            liquidated_by=head,
            reason="test: head must never be liquidated",
            db=seeded_db,
        )

    # 2) Idle auto-liquidation must NEVER include 00001 and MUST include a
    #    never-idle, non-persistent agent (NULL last_idle_action_at — the leak
    #    the old query missed).
    never_idle = Agent(
        agentium_id="39998",
        name="Never Idle Worker",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        is_persistent=False,
        parent_id=head.id,
        created_by_agentium_id="00001",
        last_idle_action_at=None,
    )
    seeded_db.add(never_idle)
    seeded_db.commit()

    summary = await idle_governance.auto_liquidate_expired(seeded_db)
    assert "00001" not in summary["liquidated"]
    assert never_idle.agentium_id in summary["liquidated"]

    # 3) Predictive pre-liquidation must route via liquidate_agent (which
    #    protects the Head) and must NOT terminate 00001.
    idle_victim = Agent(
        agentium_id="39999",
        name="Predictive Victim",
        agent_type=AgentType.TASK_AGENT,
        status=AgentStatus.ACTIVE,
        is_persistent=False,
        parent_id=head.id,
        created_by_agentium_id="00001",
        last_idle_action_at=datetime.utcnow() - timedelta(minutes=60),
    )
    seeded_db.add(idle_victim)
    seeded_db.commit()

    PredictiveScalingService.evaluate_scaling(
        seeded_db,
        {
            "current_capacity": 5,
            "next_1h": 1,
            "next_6h": 0.1,  # < 30% of capacity -> pre-liquidation branch
            "recommendation": "liquidate",
        },
    )

    seeded_db.refresh(head)
    seeded_db.refresh(idle_victim)
    assert head.is_active is True
    assert head.status == AgentStatus.ACTIVE
    assert idle_victim.is_active is False
    assert idle_victim.status == AgentStatus.TERMINATED


# ─────────────────────────────────────────────────────────────────────────────
# Contract 1 — task reaches a terminal state even after retry exhaustion
# ─────────────────────────────────────────────────────────────────────────────

def test_task_reaches_terminal_state_on_retry_exhaustion(seeded_db: Session):
    """
    Drive the REAL executor with a generic (non-provider-exhaustion) exception
    and simulate exhausted retries. The task must end FAILED (terminal), never
    stranded in IN_PROGRESS — closing the silent-stall gap.
    """
    from backend.services.tasks.task_executor import execute_task_async
    from backend.core.llm_client import LLMClient

    @contextmanager
    def _fake_get_task_db():
        yield seeded_db

    task = Task(
        agentium_id="TTERM01",
        title="Terminal-state test task",
        description="Must reach a terminal state even if execution keeps failing.",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.IN_PROGRESS,
        priority=TaskPriority.NORMAL,
        assigned_task_agent_ids=["10003"],
        is_active=True,
    )
    seeded_db.add(task)
    seeded_db.flush()

    with patch("backend.core.llm_client.LLMClient") as MockLLM, patch(
        "backend.services.tasks.task_executor.get_task_db", _fake_get_task_db
    ):
        inst = MockLLM.return_value
        # Generic (non-RuntimeError) exception => hits the generic except branch.
        inst.generate = AsyncMock(side_effect=ValueError("generic boom"))

        # Simulate Celery having already exhausted its retries.
        execute_task_async.push_request()
        execute_task_async.request.retries = 1
        try:
            result = execute_task_async.run(task.agentium_id, "10003")
        finally:
            execute_task_async.pop_request()

    seeded_db.refresh(task)
    assert task.status == "failed", f"Task stranded in {task.status}"
    assert result["status"] == "failed"
    assert (
        seeded_db.query(AuditLog).filter_by(action="task_failed_execution").count()
        >= 1
    )
