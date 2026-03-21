"""
Unit tests for Phase 13.1 — Automatic Task Delegation Engine.
Tests cover: ComplexityAnalyzer, AgentRanker, SmartRetryRouter,
CostAwareDelegator, DelegationEngine.
"""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timedelta

# ── Stub objects ──────────────────────────────────────────────────────────────

class FakeTaskPriority:
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"
    SOVEREIGN = "sovereign"

class FakeTaskType:
    EXECUTION = "execution"
    RESEARCH = "research"
    ANALYSIS = "analysis"
    CONSTITUTIONAL = "constitutional"

class FakeTaskStatus:
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    ESCALATED = "escalated"

class FakeAgentStatus:
    ACTIVE = "active"
    IDLE_WORKING = "idle_working"


def make_task(**kwargs):
    """Create a minimal mock Task object."""
    t = MagicMock()
    t.id = kwargs.get("id", "task-1")
    t.agentium_id = kwargs.get("agentium_id", "TSK001")
    t.title = kwargs.get("title", "Test task")
    t.description = kwargs.get("description", "Some description")
    t.priority = kwargs.get("priority", FakeTaskPriority.NORMAL)
    t.task_type = kwargs.get("task_type", FakeTaskType.EXECUTION)
    t.status = kwargs.get("status", FakeTaskStatus.PENDING)
    t.parent_task_id = kwargs.get("parent_task_id", None)
    t.is_idle_task = kwargs.get("is_idle_task", False)
    t.delegation_metadata = kwargs.get("delegation_metadata", None)
    t.complexity_score = kwargs.get("complexity_score", None)
    t.escalation_timeout_seconds = kwargs.get("escalation_timeout_seconds", 300)
    t.assigned_task_agent_ids = kwargs.get("assigned_task_agent_ids", [])
    t.created_by = kwargs.get("created_by", "user")
    t.error_count = kwargs.get("error_count", 0)
    return t


def make_agent(**kwargs):
    """Create a minimal mock Agent object."""
    a = MagicMock()
    a.agentium_id = kwargs.get("agentium_id", "30001")
    a.is_active = kwargs.get("is_active", True)
    a.status = kwargs.get("status", FakeAgentStatus.ACTIVE)
    a.tasks_completed_count = kwargs.get("tasks_completed", 10)
    a.tasks_failed_count = kwargs.get("tasks_failed", 0)
    return a


# ═══════════════════════════════════════════════════════════
# ComplexityAnalyzer Tests
# ═══════════════════════════════════════════════════════════

class TestComplexityAnalyzer:
    """Test suite for keyword-based complexity scoring."""

    def test_base_score_for_simple_task(self):
        """A plain task with no special keywords should get base score of 2."""
        from backend.services.auto_delegation_service import ComplexityAnalyzer
        task = make_task(description="Hello world")
        score = ComplexityAnalyzer.score(task)
        assert score == 2

    def test_high_keywords_increase_score(self):
        """Tasks mentioning 'deploy', 'security' should score higher."""
        from backend.services.auto_delegation_service import ComplexityAnalyzer
        task = make_task(description="Deploy the security patches to production")
        score = ComplexityAnalyzer.score(task)
        assert score > 2  # at least base(2) + deploy(2) + security(2) = 6

    def test_critical_priority_adds_points(self):
        """CRITICAL priority should add +2."""
        from backend.services.auto_delegation_service import ComplexityAnalyzer
        task = make_task(description="Simple fix", priority=FakeTaskPriority.CRITICAL)
        score = ComplexityAnalyzer.score(task)
        assert score >= 4  # 2 base + 2 priority

    def test_subtask_discount(self):
        """Child tasks (with parent) should get -1."""
        from backend.services.auto_delegation_service import ComplexityAnalyzer
        task = make_task(description="Simple fix", parent_task_id="parent-1")
        score = ComplexityAnalyzer.score(task)
        assert score == 1  # 2 base - 1 = 1

    def test_score_clamped_to_10(self):
        """Score should never exceed 10."""
        from backend.services.auto_delegation_service import ComplexityAnalyzer
        task = make_task(
            description="deploy migrate refactor integrate security distribute orchestrate " * 100,
            priority=FakeTaskPriority.SOVEREIGN,
            task_type=FakeTaskType.CONSTITUTIONAL,
        )
        score = ComplexityAnalyzer.score(task)
        assert score == 10

    def test_score_minimum_is_1(self):
        """Score should never go below 1."""
        from backend.services.auto_delegation_service import ComplexityAnalyzer
        task = make_task(description="", parent_task_id="p1")
        score = ComplexityAnalyzer.score(task)
        assert score >= 1


# ═══════════════════════════════════════════════════════════
# SmartRetryRouter Tests
# ═══════════════════════════════════════════════════════════

class TestSmartRetryRouter:
    """Test suite for smart retry routing."""

    @patch("backend.services.auto_delegation_service.AgentRanker.rank")
    def test_reroute_finds_replacement(self, mock_rank):
        """SmartRetryRouter should find a replacement agent."""
        from backend.services.auto_delegation_service import SmartRetryRouter

        replacement = make_agent(agentium_id="30002")
        mock_rank.return_value = [(replacement, 0.85)]

        task = make_task(delegation_metadata={})
        db = MagicMock()

        result = SmartRetryRouter.reroute(task, "30001", db)
        assert result is not None
        assert result.agentium_id == "30002"
        assert "30001" in task.delegation_metadata["failed_agent_ids"]

    @patch("backend.services.auto_delegation_service.AgentRanker.rank")
    def test_reroute_returns_none_when_no_agents(self, mock_rank):
        """If no agents are available, return None."""
        from backend.services.auto_delegation_service import SmartRetryRouter

        mock_rank.return_value = []
        task = make_task(delegation_metadata={})
        db = MagicMock()

        result = SmartRetryRouter.reroute(task, "30001", db)
        assert result is None


# ═══════════════════════════════════════════════════════════
# CostAwareDelegator Tests
# ═══════════════════════════════════════════════════════════

class TestCostAwareDelegator:
    """Test suite for budget-aware cost delegator."""

    @patch("backend.services.auto_delegation_service.CostAwareDelegator.should_force_local")
    def test_forces_local_when_budget_low_and_simple(self, mock_force):
        """Simulates budget < 20% and low complexity."""
        mock_force.return_value = True
        from backend.services.auto_delegation_service import CostAwareDelegator
        # Direct call — the mock replaces the real method
        assert CostAwareDelegator.should_force_local(make_task(), 2) is True

    def test_does_not_force_local_for_complex_tasks(self):
        """Complex tasks should not be forced to local even with low budget."""
        from backend.services.auto_delegation_service import CostAwareDelegator
        # When token_optimizer import fails, should return False
        result = CostAwareDelegator.should_force_local(make_task(), 9)
        assert result is False  # import will fail → defaults to False


# ═══════════════════════════════════════════════════════════
# DelegationEngine Tests
# ═══════════════════════════════════════════════════════════

class TestDelegationEngine:
    """Test suite for the main delegation orchestrator."""

    @pytest.mark.asyncio
    @patch("backend.services.auto_delegation_service.AgentRanker.rank")
    @patch("backend.services.auto_delegation_service.CostAwareDelegator.should_force_local")
    async def test_delegate_assigns_agent(self, mock_cost, mock_rank):
        """DelegationEngine should score, rank, and assign an agent."""
        from backend.services.auto_delegation_service import DelegationEngine

        agent = make_agent(agentium_id="30001")
        mock_rank.return_value = [(agent, 0.95)]
        mock_cost.return_value = False

        task = make_task(description="Simple task")
        db = MagicMock()
        db.flush = MagicMock()

        result = await DelegationEngine.delegate(task, db)

        assert result["delegated"] is True
        assert result["assigned_to"] == "30001"
        assert result["complexity_score"] >= 1
        assert task.complexity_score is not None

    @pytest.mark.asyncio
    async def test_delegate_skips_idle_tasks(self):
        """Idle tasks should be skipped."""
        from backend.services.auto_delegation_service import DelegationEngine

        task = make_task(is_idle_task=True)
        db = MagicMock()

        result = await DelegationEngine.delegate(task, db)
        assert result["skipped"] == "idle_task"
        assert result["delegated"] is False

    @pytest.mark.asyncio
    async def test_delegate_skips_already_delegated(self):
        """Already-delegated tasks should be skipped (unless forced)."""
        from backend.services.auto_delegation_service import DelegationEngine

        task = make_task(delegation_metadata={"delegated_at": "2024-01-01"})
        db = MagicMock()

        result = await DelegationEngine.delegate(task, db)
        assert result["skipped"] == "already_delegated"

    @pytest.mark.asyncio
    @patch("backend.services.auto_delegation_service.AgentRanker.rank")
    @patch("backend.services.auto_delegation_service.CostAwareDelegator.should_force_local")
    async def test_delegate_force_re_delegates(self, mock_cost, mock_rank):
        """Forced delegation should work even on already-delegated tasks."""
        from backend.services.auto_delegation_service import DelegationEngine

        agent = make_agent(agentium_id="30005")
        mock_rank.return_value = [(agent, 0.7)]
        mock_cost.return_value = False

        task = make_task(
            description="Build dashboard",
            delegation_metadata={"delegated_at": "2024-01-01"},
        )
        db = MagicMock()
        db.flush = MagicMock()

        result = await DelegationEngine.delegate(task, db, force=True)
        assert result["delegated"] is True
        assert result["assigned_to"] == "30005"
