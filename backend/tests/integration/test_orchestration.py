"""
Integration tests for Phase 13 Autonomous Agent Orchestration.

Covers:
  Group 1 — Auto-delegation complexity scoring (1-10) maps to the correct tier
  Group 2 — Sub-task DAG dispatches independent branches in parallel
  Group 3 — Crash detection (last_heartbeat_at > 2 min) triggers reincarnation
            from checkpoint
  Group 4 — Predictive scaling pre-spawns agents before a simulated surge

========================================================================
NOTES ON SCOPE / KNOWN GAPS (do not silently "fix" by guessing internals)
========================================================================

GAP-ORCH-001 (DelegationEngine.delegate target_tier mapping):
  Per auto_delegation_service.py, DelegationEngine.delegate() currently maps
  complexity >= 8 -> tier "2" (Lead) and everything else -> tier "3" (Task).
  This file tests the documented/expected mapping ("1-10 maps to correct
  tier") against the ComplexityAnalyzer score directly (which is provider-
  agnostic and stable), and separately documents the DelegationEngine's
  actual tier assignment behavior so a future tightening of the tier
  thresholds doesn't silently regress without a failing test.

GAP-ORCH-002 (SelfHealingService not present in reviewed source):
  task_executor.detect_crashed_agents() delegates to
  backend.services.self_healing_service.SelfHealingService, which was not
  available for direct inspection. Group 3 tests therefore verify crash
  detection at the data layer Agentium actually owns and document/exercise
  (last_heartbeat_at staleness -> Agent considered crashed) using the same
  reincarnation primitives verified in test_agent_lifecycle.py
  (CheckpointService.create_checkpoint / resume_from_checkpoint and
  ReincarnationService.execute_reincarnation), rather than asserting on
  unseen SelfHealingService internals. A thin call-through test patches
  SelfHealingService.detect_crashed_agents to confirm task_executor wires
  it correctly without assuming undocumented return shape.

GAP-ORCH-003 (predictive_scaling_service uses module-level psycopg/redis):
  predictive_scaling_service.py instantiates a module-level Redis client
  bound to CELERY_BROKER_URL at import time. Tests patch
  PredictiveScalingService.evaluate_scaling's collaborators
  (ReincarnationService.spawn_task_agent, AuditLog.log, the websocket
  manager broadcast) rather than requiring a live Redis connection, since
  evaluate_scaling()'s spawn decision is pure given `predictions`.
========================================================================
"""

import asyncio
import uuid
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from sqlalchemy.orm import Session

from backend.models.entities.agents import (
    Agent,
    AgentStatus,
    AgentType,
    CouncilMember,
    HeadOfCouncil,
    LeadAgent,
    TaskAgent,
)
from backend.models.entities.task import (
    Task,
    TaskStatus,
    TaskPriority,
    TaskType,
    TaskDependency,
)
from backend.models.entities.audit import AuditLog, AuditCategory, AuditLevel
from backend.services.auto_delegation_service import (
    ComplexityAnalyzer,
    AgentRanker,
    DelegationEngine,
)
from backend.services.reincarnation_service import reincarnation_service, ReincarnationService
from backend.services.checkpoint_service import CheckpointService
from backend.models.entities.checkpoint import CheckpointPhase

pytestmark = pytest.mark.integration


# ===========================================================================
# Helpers
# ===========================================================================

def _make_task(
    title: str = "Test task",
    description: str = "",
    priority: TaskPriority = TaskPriority.NORMAL,
    task_type: TaskType = TaskType.EXECUTION,
    parent_task_id: str = None,
) -> Task:
    """Build an unsaved Task row with sane defaults for complexity scoring tests."""
    return Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title=title,
        description=description,
        task_type=task_type,
        status=TaskStatus.PENDING,
        priority=priority,
        created_by="system",
        is_active=True,
        parent_task_id=parent_task_id,
    )


def _spawn_task_agent(db: Session, parent: Agent, name: str) -> TaskAgent:
    """Spawn a real Task Agent via the production service (mirrors test_agent_lifecycle.py)."""
    agent = reincarnation_service.spawn_task_agent(
        parent=parent,
        name=name,
        description=f"Worker agent for orchestration tests: {name}",
        db=db,
    )
    db.commit()
    return agent


# ===========================================================================
# Group 1 — Complexity scoring maps to the correct tier
# ===========================================================================

class TestComplexityScoringTierMapping:
    """
    ComplexityAnalyzer.score() must return an integer in [1, 10], and that
    score must drive DelegationEngine's tier assignment deterministically.
    """

    def test_score_is_clamped_between_1_and_10(self):
        """Even a maximally 'simple' or maximally 'complex' task stays in range."""
        trivial = _make_task(description="hi")
        score = ComplexityAnalyzer.score(trivial)
        assert 1 <= score <= 10

        maximal = _make_task(
            description=(
                "deploy migrate refactor integrate architecture security "
                "authentication database distributed multi-step orchestrate "
                "pipeline workflow concurrent parallel " * 5
            ),
            priority=TaskPriority.SOVEREIGN,
            task_type=TaskType.RESEARCH,
        )
        score = ComplexityAnalyzer.score(maximal)
        assert 1 <= score <= 10
        assert score == 10  # all signals saturated must hit the ceiling

    @pytest.mark.parametrize(
        "description,priority,task_type,expected_min_score",
        [
            ("update the readme typo", TaskPriority.LOW, TaskType.EXECUTION, 1),
            ("configure the api endpoint and optimize it", TaskPriority.NORMAL, TaskType.EXECUTION, 3),
            (
                "migrate the database and refactor the authentication architecture",
                TaskPriority.CRITICAL,
                TaskType.ANALYSIS,
                8,
            ),
        ],
    )
    def test_score_increases_with_keyword_and_signal_density(
        self, description, priority, task_type, expected_min_score
    ):
        """Higher-signal tasks must never score below their documented floor."""
        task = _make_task(description=description, priority=priority, task_type=task_type)
        score = ComplexityAnalyzer.score(task)
        assert score >= expected_min_score

    def test_subtask_discount_lowers_score_relative_to_parent(self, seeded_db: Session):
        """A sub-task (has parent_task_id) scores at least 1 point lower than the same
        description scored as a top-level task, per the -1 sub-task discount rule."""
        description = "integrate the distributed orchestrate pipeline"
        parent = _make_task(description=description)
        child = _make_task(description=description, parent_task_id="some-parent-id")

        parent_score = ComplexityAnalyzer.score(parent)
        child_score = ComplexityAnalyzer.score(child)

        assert child_score <= parent_score - 1 or child_score == 1  # respects floor of 1

    @pytest.mark.asyncio
    async def test_low_complexity_task_assigned_to_task_tier(self, seeded_db: Session):
        """Score <= 6 (per DelegationEngine) routes to tier '3' (Task Agent)."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None
        _spawn_task_agent(seeded_db, head, "Tier3-Candidate-A")

        task = _make_task(description="fix a small typo in the help text")
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)

        assert result["complexity_score"] <= 6
        assert result["delegation_metadata"]["target_tier"] == "3"

    @pytest.mark.asyncio
    async def test_very_high_complexity_task_assigned_to_lead_tier(self, seeded_db: Session):
        """Score >= 8 routes to tier '2' (Lead Agent) per DelegationEngine's mapping."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Need a Lead agent candidate available on tier '2' for the ranker to find.
        council = seeded_db.query(CouncilMember).first()
        assert council is not None
        lead = reincarnation_service.spawn_lead_agent(
            parent=head if head.agentium_id.startswith("0") else council,
            name="Lead-Candidate-A",
            description="Lead candidate for high-complexity routing",
            db=seeded_db,
        )
        seeded_db.commit()

        task = _make_task(
            description=(
                "migrate and refactor the distributed authentication architecture "
                "with security review and database integration"
            ),
            priority=TaskPriority.CRITICAL,
            task_type=TaskType.ANALYSIS,
        )
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)

        assert result["complexity_score"] >= 8
        assert result["delegation_metadata"]["target_tier"] == "2"
        # Routed to a Lead-tier agent (2xxxx). The seeded DB already contains a
        # Lead (20001); AgentRanker picks the best-scored lead, so we assert on
        # tier membership rather than a specific agentium_id.
        assert result["assigned_to"] is not None
        assert result["assigned_to"].startswith("2")
        assert any(c["agentium_id"] == lead.agentium_id for c in result.get("candidates", []))

    @pytest.mark.asyncio
    async def test_decision_trail_records_complexity_and_tier(self, seeded_db: Session):
        """The full delegation decision (complexity, tier, candidates) must be persisted
        on Task.delegation_metadata for later audit (GET /tasks/{id}/delegation-log)."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        _spawn_task_agent(seeded_db, head, "Tier3-Candidate-B")

        task = _make_task(description="process and validate the uploaded csv data")
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)
        seeded_db.flush()

        assert task.complexity_score == result["complexity_score"]
        meta = task.delegation_metadata
        assert meta is not None
        assert "complexity_score" in meta
        assert "target_tier" in meta
        assert "delegated_at" in meta

        # Re-running without force is a no-op (idempotency of auto-delegation)
        rerun = await DelegationEngine.delegate(task, seeded_db)
        assert rerun.get("skipped") == "already_delegated"

    @pytest.mark.asyncio
    async def test_no_candidate_agents_yields_unassigned_but_scored(self, seeded_db: Session):
        """When no agent exists on the target tier, delegation still records the
        complexity score and tier decision, but assigned_to is None."""
        # Remove all task agents so tier '3' ranking is empty.
        seeded_db.query(TaskAgent).delete()
        seeded_db.flush()

        task = _make_task(description="run a quick lookup")
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)

        assert result["delegated"] is False
        assert result["assigned_to"] is None
        assert result["complexity_score"] >= 1


# ===========================================================================
# Group 2 — Sub-task DAG dispatches independent branches in parallel
# ===========================================================================

class TestDependencyGraphParallelDispatch:
    """
    Tasks with no unresolved TaskDependency predecessors are independent
    branches and must all be dispatched together by process_dependency_graph,
    while dependent tasks wait for their predecessor to complete.
    """

    def _make_parent_with_children(self, db: Session, n_children: int, agent_id: str):
        parent = _make_task(title="DAG parent")
        db.add(parent)
        db.flush()

        children = []
        for i in range(n_children):
            child = _make_task(title=f"DAG child {i}", parent_task_id=parent.id)
            child.assigned_task_agent_ids = [agent_id]  # used by process_dependency_graph dispatch
            db.add(child)
            db.flush()
            children.append(child)

        return parent, children

    def test_independent_branches_all_marked_dispatched_in_one_pass(self, seeded_db: Session):
        """
        Two children with the SAME dependency_order (both order=0, i.e. no
        predecessor) are independent branches: process_dependency_graph must
        flip both from PENDING -> IN_PROGRESS / dispatched in a single call,
        proving they run concurrently rather than waiting on each other.
        """
        from backend.services.tasks.task_executor import process_dependency_graph

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "DAG-Parallel-Worker")

        parent, children = self._make_parent_with_children(seeded_db, n_children=2, agent_id=agent.agentium_id)

        dep_a = TaskDependency(
            agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
            parent_task_id=parent.id,
            child_task_id=children[0].id,
            dependency_order=0,  # independent — no predecessor
            status="pending",
        )
        dep_b = TaskDependency(
            agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
            parent_task_id=parent.id,
            child_task_id=children[1].id,
            dependency_order=0,  # also independent — same wave as dep_a
            status="pending",
        )
        seeded_db.add_all([dep_a, dep_b])
        seeded_db.commit()

        with patch(
            "backend.services.tasks.task_executor.execute_task_async.delay"
        ) as mock_delay:
            result = process_dependency_graph(db=seeded_db)

        # Both independent branches dispatched in the same pass.
        assert result["dispatched"] == 2

        seeded_db.refresh(children[0])
        seeded_db.refresh(children[1])
        assert children[0].status == TaskStatus.IN_PROGRESS
        assert children[1].status == TaskStatus.IN_PROGRESS

        seeded_db.refresh(dep_a)
        seeded_db.refresh(dep_b)
        assert dep_a.status == "dispatched"
        assert dep_b.status == "dispatched"

        # Each independent branch fired its own async execution call.
        assert mock_delay.call_count == 2

    def test_dependent_branch_waits_for_predecessor(self, seeded_db: Session):
        """
        A child at dependency_order=1 must NOT dispatch while the order=0
        predecessor under the same parent has not completed yet.
        """
        from backend.services.tasks.task_executor import process_dependency_graph

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "DAG-Sequential-Worker")

        parent, children = self._make_parent_with_children(seeded_db, n_children=2, agent_id=agent.agentium_id)

        predecessor_dep = TaskDependency(
            agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
            parent_task_id=parent.id,
            child_task_id=children[0].id,
            dependency_order=0,
            status="pending",
        )
        dependent_dep = TaskDependency(
            agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
            parent_task_id=parent.id,
            child_task_id=children[1].id,
            dependency_order=1,  # must wait for order=0 to complete first
            status="pending",
        )
        seeded_db.add_all([predecessor_dep, dependent_dep])
        seeded_db.commit()

        with patch("backend.services.tasks.task_executor.execute_task_async.delay"):
            result = process_dependency_graph(db=seeded_db)

        # Only the order=0 predecessor dispatches this pass.
        assert result["dispatched"] == 1

        seeded_db.refresh(children[0])
        seeded_db.refresh(children[1])
        assert children[0].status == TaskStatus.IN_PROGRESS
        assert children[1].status == TaskStatus.PENDING  # still blocked

        seeded_db.refresh(predecessor_dep)
        seeded_db.refresh(dependent_dep)
        assert predecessor_dep.status == "dispatched"
        assert dependent_dep.status == "pending"

    def test_completed_predecessor_unblocks_dependent_branch_on_next_pass(self, seeded_db: Session):
        """
        Once the predecessor's Task is marked COMPLETED (and its dependency
        row reflects that), a subsequent process_dependency_graph pass must
        dispatch the previously-blocked dependent branch.
        """
        from backend.services.tasks.task_executor import process_dependency_graph

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "DAG-Unblock-Worker")

        parent, children = self._make_parent_with_children(seeded_db, n_children=2, agent_id=agent.agentium_id)

        predecessor_dep = TaskDependency(
            agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
            parent_task_id=parent.id,
            child_task_id=children[0].id,
            dependency_order=0,
            status="completed",  # already resolved
        )
        dependent_dep = TaskDependency(
            agentium_id=f"DEP{uuid.uuid4().hex[:6].upper()}",
            parent_task_id=parent.id,
            child_task_id=children[1].id,
            dependency_order=1,
            status="pending",
        )
        # Simulate the predecessor task itself having already finished.
        children[0].status = TaskStatus.COMPLETED
        seeded_db.add_all([predecessor_dep, dependent_dep])
        seeded_db.commit()

        with patch("backend.services.tasks.task_executor.execute_task_async.delay"):
            result = process_dependency_graph(db=seeded_db)

        assert result["dispatched"] == 1
        seeded_db.refresh(children[1])
        seeded_db.refresh(dependent_dep)
        assert children[1].status == TaskStatus.IN_PROGRESS
        assert dependent_dep.status == "dispatched"


# ===========================================================================
# Group 3 — Crash detection (stale heartbeat) -> reincarnation from checkpoint
# ===========================================================================

class TestCrashDetectionAndReincarnation:
    """
    Per Phase 13.2: an agent whose last_heartbeat_at exceeds the crash
    threshold (2 minutes) while status == WORKING is considered crashed.
    Recovery restores state from the latest checkpoint and re-queues the
    interrupted task. These tests exercise the underlying Agentium primitives
    (heartbeat staleness, CheckpointService, ReincarnationService) that any
    correct SelfHealingService.detect_crashed_agents() implementation must
    rely on, plus a thin wiring test against task_executor's Celery task.
    """

    def test_stale_heartbeat_beyond_two_minutes_is_detectable(self, seeded_db: Session):
        """
        Simulate an agent stuck in WORKING with a heartbeat older than the
        2-minute crash threshold; this is the precondition crash detection
        must act on.
        """
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "Heartbeat-Stale-Agent")

        agent.status = AgentStatus.WORKING
        agent.last_heartbeat_at = datetime.utcnow() - timedelta(minutes=5)
        seeded_db.commit()
        seeded_db.refresh(agent)

        threshold = datetime.utcnow() - timedelta(minutes=2)
        is_stale = agent.last_heartbeat_at < threshold and agent.status == AgentStatus.WORKING
        assert is_stale is True

    def test_fresh_heartbeat_within_two_minutes_is_not_flagged(self, seeded_db: Session):
        """A heartbeat updated 30 seconds ago must NOT be treated as crashed."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "Heartbeat-Fresh-Agent")

        agent.status = AgentStatus.WORKING
        agent.last_heartbeat_at = datetime.utcnow() - timedelta(seconds=30)
        seeded_db.commit()
        seeded_db.refresh(agent)

        threshold = datetime.utcnow() - timedelta(minutes=2)
        is_stale = agent.last_heartbeat_at < threshold and agent.status == AgentStatus.WORKING
        assert is_stale is False

    def test_reincarnation_restores_state_from_latest_checkpoint(self, seeded_db: Session):
        """
        Simulates the recovery half of crash handling: given a checkpoint
        taken while a task was IN_PROGRESS, resume_from_checkpoint must
        restore the task's status and assigned agents — the same mechanism
        a crash-recovery routine would invoke to restart interrupted work.
        """
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "Crash-Recovery-Worker")

        task = Task(
            agentium_id="TCRASHRC1",
            title="Task interrupted by simulated crash",
            description="Work in progress when the agent crashed",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent.agentium_id],
            is_active=True,
            supervisor_id=head.agentium_id,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.commit()

        # Checkpoint while the task is healthy and in progress.
        checkpoint = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task.id,
            phase=CheckpointPhase.PRE_EXECUTION if hasattr(CheckpointPhase, "PRE_EXECUTION") else list(CheckpointPhase)[0],
            actor_id="crash_test",
        )
        assert checkpoint.task_id == task.id
        assert agent.agentium_id in checkpoint.agent_states

        # Simulate the crash: agent goes stale/working, task result gets corrupted.
        agent.status = AgentStatus.WORKING
        agent.last_heartbeat_at = datetime.utcnow() - timedelta(minutes=10)
        task.result_data = {"partial": "corrupted-mid-write"}
        seeded_db.commit()

        # Recovery: restore from the last good checkpoint.
        restored_task = CheckpointService.resume_from_checkpoint(
            db=seeded_db,
            checkpoint_id=checkpoint.id,
            actor_id="crash_recovery",
        )

        assert restored_task.id == task.id
        assert restored_task.status == TaskStatus.IN_PROGRESS
        assert agent.agentium_id in (restored_task.assigned_task_agent_ids or [])

        # The audit trail must show the time-travel recovery action occurred.
        recovery_audit = (
            seeded_db.query(AuditLog)
            .filter(AuditLog.action == "checkpoint_resumed", AuditLog.target_id == task.id)
            .order_by(AuditLog.created_at.desc())
            .first()
        )
        assert recovery_audit is not None
        assert recovery_audit.level == AuditLevel.WARNING

    @pytest.mark.asyncio
    async def test_full_reincarnation_cycle_spawns_successor_with_wisdom(
        self, seeded_db: Session, mock_ai_provider
    ):
        """
        End-to-end reincarnation: a crashed/exhausted agent is terminated and
        a successor is spawned that inherits summarized wisdom, exercising
        the actual recovery path crash detection would trigger for an agent
        beyond simple restart (full reincarnation rather than just resume).
        """
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        agent = _spawn_task_agent(seeded_db, head, "Crash-Reincarnate-Source")
        original_id = agent.agentium_id

        # Mark crashed precondition explicitly before triggering reincarnation.
        agent.status = AgentStatus.WORKING
        agent.last_heartbeat_at = datetime.utcnow() - timedelta(minutes=10)
        seeded_db.commit()

        result = await ReincarnationService.execute_reincarnation(
            agent=agent,
            db=seeded_db,
            conversation_context="Agent was mid-task when heartbeat went stale and was flagged as crashed.",
        )

        assert result["terminated"] is True
        assert result["successor_spawned"] is True
        assert result["successor_id"] is not None
        assert result["successor_id"] != original_id

        seeded_db.refresh(agent)
        assert agent.status == AgentStatus.TERMINATED
        assert agent.is_active is False

        successor = seeded_db.query(Agent).filter_by(agentium_id=result["successor_id"]).first()
        assert successor is not None
        assert successor.status == AgentStatus.ACTIVE
        assert successor.is_active is True

        death_audit = seeded_db.query(AuditLog).filter_by(
            action="agent_death", target_id=original_id
        ).first()
        birth_audit = seeded_db.query(AuditLog).filter_by(
            action="agent_birth", target_id=result["successor_id"]
        ).first()
        assert death_audit is not None
        assert birth_audit is not None

    def test_task_executor_crash_detection_delegates_to_self_healing_service(self, seeded_db: Session):
        """
        Wiring test: detect_crashed_agents (the Celery task) must call through
        to SelfHealingService.detect_crashed_agents and SelfHealingService
        .check_degradation_triggers exactly once each, passing the DB session.
        This locks the integration point without assuming undocumented
        internals of SelfHealingService itself (see GAP-ORCH-002).
        """
        from backend.services.tasks import task_executor

        fake_result = {"detected": 1, "recovered": 1}

        with patch(
            "backend.services.self_healing_service.SelfHealingService.detect_crashed_agents",
            return_value=fake_result,
        ) as mock_detect, patch(
            "backend.services.self_healing_service.SelfHealingService.check_degradation_triggers",
            return_value=None,
        ) as mock_degradation:
            result = task_executor.detect_crashed_agents()

        assert result == fake_result
        assert mock_detect.call_count == 1
        assert mock_degradation.call_count == 1


# ===========================================================================
# Group 4 — Predictive scaling pre-spawns agents before a simulated surge
# ===========================================================================

class TestPredictiveScalingPreSpawn:
    """
    PredictiveScalingService.evaluate_scaling() must spawn additional Task
    Agents *before* a predicted surge exhausts current capacity, i.e. when
    next_1h prediction exceeds 80% of current capacity.
    """

    def _surge_predictions(self, current_capacity: int = 4) -> dict:
        """A forecast where next_1h clearly exceeds the 80%-of-capacity trigger."""
        return {
            "next_1h": current_capacity * 0.95,
            "next_6h": current_capacity * 1.2,
            "next_24h": current_capacity * 1.1,
            "current_capacity": current_capacity,
            "recommendation": "spawn",
        }

    def _calm_predictions(self, current_capacity: int = 4) -> dict:
        """A forecast with no surge — spawning must NOT occur."""
        return {
            "next_1h": current_capacity * 0.3,
            "next_6h": current_capacity * 0.5,
            "next_24h": current_capacity * 0.4,
            "current_capacity": current_capacity,
            "recommendation": "neutral",
        }

    def test_predicted_surge_triggers_pre_spawn(self, seeded_db: Session):
        """
        next_1h > 80% of current_capacity, business hours assumed (default
        env config) -> evaluate_scaling must call ReincarnationService
        .spawn_task_agent at least once and write an audit log documenting
        the predictive spawn decision.
        """
        from backend.services.predictive_scaling import predictive_scaling_service

        predictions = self._surge_predictions(current_capacity=4)

        with patch(
            "backend.services.predictive_scaling.ReincarnationService.spawn_task_agent"
        ) as mock_spawn, patch(
            "backend.services.predictive_scaling.AuditLog.log"
        ) as mock_audit_log, patch(
            "backend.services.predictive_scaling.os.getenv",
            side_effect=lambda key, default=None: {
                "BUSINESS_HOURS_TZ": "UTC",
                "BUSINESS_HOURS_START": "0",
                "BUSINESS_HOURS_END": "23",
            }.get(key, default),
        ):
            predictive_scaling_service.evaluate_scaling(seeded_db, predictions)

        assert mock_spawn.call_count >= 1
        # Audit log must record the predictive spawn action with the trigger context.
        assert mock_audit_log.call_count == 1
        _, audit_kwargs = mock_audit_log.call_args
        assert audit_kwargs["action"] == "auto_scale_predictive_spawn"
        assert audit_kwargs["after_state"]["next_1h"] == predictions["next_1h"]
        assert audit_kwargs["after_state"]["spawned"] >= 1

    def test_no_surge_predicted_does_not_spawn(self, seeded_db: Session):
        """Calm forecast (no threshold breach) must not trigger any spawn or audit log."""
        from backend.services.predictive_scaling import predictive_scaling_service

        predictions = self._calm_predictions(current_capacity=4)

        with patch(
            "backend.services.predictive_scaling.ReincarnationService.spawn_task_agent"
        ) as mock_spawn, patch(
            "backend.services.predictive_scaling.AuditLog.log"
        ) as mock_audit_log:
            predictive_scaling_service.evaluate_scaling(seeded_db, predictions)

        mock_spawn.assert_not_called()
        mock_audit_log.assert_not_called()

    def test_pre_spawn_respects_capacity_ceiling(self, seeded_db: Session):
        """
        Per evaluate_scaling's guard (`current_capacity < 50`), a forecast at
        or above the 50-agent ceiling must not trigger further pre-spawning
        even if next_1h nominally exceeds 80% of capacity.
        """
        from backend.services.predictive_scaling import predictive_scaling_service

        predictions = self._surge_predictions(current_capacity=60)
        predictions["current_capacity"] = 60  # above the safety ceiling

        with patch(
            "backend.services.predictive_scaling.ReincarnationService.spawn_task_agent"
        ) as mock_spawn:
            predictive_scaling_service.evaluate_scaling(seeded_db, predictions)

        mock_spawn.assert_not_called()

    def test_outside_business_hours_caps_spawn_when_capacity_already_sufficient(
        self, seeded_db: Session
    ):
        """
        Time-Based Policy: outside configured business hours, if capacity is
        already >= 2 and recommendation is 'spawn', the spawn must be
        suppressed (capped) rather than executed.
        """
        from backend.services.predictive_scaling import predictive_scaling_service

        predictions = self._surge_predictions(current_capacity=4)

        # Force "outside business hours" by making the window zero-width.
        with patch(
            "backend.services.predictive_scaling.ReincarnationService.spawn_task_agent"
        ) as mock_spawn, patch(
            "backend.services.predictive_scaling.os.getenv",
            side_effect=lambda key, default=None: {
                "BUSINESS_HOURS_TZ": "UTC",
                "BUSINESS_HOURS_START": "0",
                "BUSINESS_HOURS_END": "0",  # zero-width window => always "outside hours"
            }.get(key, default),
        ):
            predictive_scaling_service.evaluate_scaling(seeded_db, predictions)

        mock_spawn.assert_not_called()

    def test_pre_spawn_count_scales_with_predicted_deficit(self, seeded_db: Session):
        """
        recommended_spawn = max(1, int((next_1h - current_capacity) / 2));
        a larger predicted deficit must request more spawns than a smaller one.
        """
        from backend.services.predictive_scaling import predictive_scaling_service

        small_deficit = {
            "next_1h": 5.0,   # capacity=4 -> deficit=1 -> max(1, 0) = 1 spawn
            "next_6h": 6.0,
            "next_24h": 5.5,
            "current_capacity": 4,
            "recommendation": "spawn",
        }
        large_deficit = {
            "next_1h": 14.0,  # capacity=4 -> deficit=10 -> max(1, 5) = 5 spawns
            "next_6h": 16.0,
            "next_24h": 15.0,
            "current_capacity": 4,
            "recommendation": "spawn",
        }

        env_patch = patch(
            "backend.services.predictive_scaling.os.getenv",
            side_effect=lambda key, default=None: {
                "BUSINESS_HOURS_TZ": "UTC",
                "BUSINESS_HOURS_START": "0",
                "BUSINESS_HOURS_END": "23",
            }.get(key, default),
        )

        with env_patch, patch(
            "backend.services.predictive_scaling.ReincarnationService.spawn_task_agent"
        ) as mock_spawn_small, patch("backend.services.predictive_scaling.AuditLog.log"):
            predictive_scaling_service.evaluate_scaling(seeded_db, small_deficit)
        small_calls = mock_spawn_small.call_count

        with env_patch, patch(
            "backend.services.predictive_scaling.ReincarnationService.spawn_task_agent"
        ) as mock_spawn_large, patch("backend.services.predictive_scaling.AuditLog.log"):
            predictive_scaling_service.evaluate_scaling(seeded_db, large_deficit)
        large_calls = mock_spawn_large.call_count

        assert small_calls == 1
        assert large_calls == 5
        assert large_calls > small_calls

    def test_pre_spawned_agents_are_real_active_task_agents(self, seeded_db: Session):
        """
        End-to-end (no mocking of spawn_task_agent itself): after a surge
        prediction, the spawned agents must actually exist in the DB as
        active Task Agents under the Head of Council, ready to absorb load
        BEFORE the surge materializes (i.e. proactive, not reactive).
        """
        from backend.services.predictive_scaling import predictive_scaling_service

        before_count = seeded_db.query(TaskAgent).filter_by(is_active=True).count()

        predictions = self._surge_predictions(current_capacity=2)

        with patch(
            "backend.services.predictive_scaling.os.getenv",
            side_effect=lambda key, default=None: {
                "BUSINESS_HOURS_TZ": "UTC",
                "BUSINESS_HOURS_START": "0",
                "BUSINESS_HOURS_END": "23",
            }.get(key, default),
        ):
            predictive_scaling_service.evaluate_scaling(seeded_db, predictions)

        after_count = seeded_db.query(TaskAgent).filter_by(is_active=True).count()
        assert after_count > before_count

        newest_agents = (
            seeded_db.query(TaskAgent)
            .filter(TaskAgent.name.like("Predictive-Spawn-%"))
            .all()
        )
        assert len(newest_agents) >= 1
        for a in newest_agents:
            assert a.status == AgentStatus.ACTIVE
            assert a.is_active is True
            assert a.parent_id is not None  # spawned under Head of Council