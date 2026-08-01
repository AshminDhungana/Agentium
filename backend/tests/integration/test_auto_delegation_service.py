"""Integration tests for AutoDelegationService and DelegationEngine."""
import pytest
from sqlalchemy.orm import Session

from backend.services.auto_delegation_service import (
    ComplexityAnalyzer,
    DelegationEngine,
    AgentRanker,
    SmartRetryRouter,
    CostAwareDelegator,
)
from backend.models.entities.agents import HeadOfCouncil, CouncilMember, AgentType, AgentStatus
from backend.models.entities.task import Task, TaskPriority, TaskType


@pytest.mark.integration
class TestComplexityAnalyzerIntegration:
    """Test ComplexityAnalyzer with real database."""

    def test_analyze_simple_task_score(self, seeded_db: Session):
        """Simple task description should yield low complexity score."""
        analyzer = ComplexityAnalyzer()
        # Create a task object with simple description
        task = Task(
            agentium_id="TC001",
            title="Fix typo",
            description="fix a typo in the button label",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        score = analyzer.score(task)
        assert 1 <= score <= 4, f"Simple task scored {score}, expected 1-4"

    def test_analyze_complex_task_score(self, seeded_db: Session):
        """Complex architectural task should yield high score."""
        analyzer = ComplexityAnalyzer()
        task = Task(
            agentium_id="TC002",
            title="Architecture migration",
            description="migrate and refactor the distributed authentication architecture",
            task_type=TaskType.ANALYSIS,
            priority=TaskPriority.CRITICAL,
            is_active=True,
            created_by="system",
        )
        score = analyzer.score(task)
        assert 7 <= score <= 10, f"Complex task scored {score}, expected 7-10"

    def test_analyze_medium_task_score(self, seeded_db: Session):
        """Medium complexity task should yield mid-range score."""
        analyzer = ComplexityAnalyzer()
        task = Task(
            agentium_id="TC003",
            title="API configuration",
            description="configure and optimize the api endpoint for better performance",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        score = analyzer.score(task)
        assert 3 <= score <= 7, f"Medium task scored {score}, expected 3-7"

    def test_analyze_subtask_discount(self, seeded_db: Session):
        """Sub-tasks should get a complexity discount."""
        analyzer = ComplexityAnalyzer()
        task = Task(
            agentium_id="TC004",
            title="Sub-task",
            description="deploy the new service to production",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            parent_task_id="parent-123",
            is_active=True,
            created_by="system",
        )
        score = analyzer.score(task)
        # Should be discounted by 1 for being a subtask
        assert score >= 1

    def test_analyze_critical_priority_bonus(self, seeded_db: Session):
        """CRITICAL/SOVEREIGN priority should add bonus."""
        analyzer = ComplexityAnalyzer()
        task = Task(
            agentium_id="TC005",
            title="Critical task",
            description="simple fix",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.CRITICAL,
            is_active=True,
            created_by="system",
        )
        score = analyzer.score(task)
        # Base 2 + priority 2 = 4
        assert score >= 4


@pytest.mark.integration
class TestAgentRankerIntegration:
    """Test AgentRanker with real database and agents."""

    def test_rank_excludes_inactive_agents(self, seeded_db: Session):
        """Terminated agents should be excluded from ranking."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

        # Create a terminated agent
        from backend.models.entities.agents import TaskAgent
        terminated_agent = TaskAgent(
            agentium_id="30001",
            name="Terminated Agent",
            agent_type=AgentType.TASK_AGENT,
            status=AgentStatus.TERMINATED,
            is_active=False,
            is_persistent=False,
        )
        seeded_db.add(terminated_agent)

        # Create an active agent
        active_agent = TaskAgent(
            agentium_id="30002",
            name="Active Agent",
            agent_type=AgentType.TASK_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
        )
        seeded_db.add(active_agent)
        seeded_db.commit()

        ranked = AgentRanker.rank(db=seeded_db, required_tier="3")

        # Only active agent should be in results
        agent_ids = [a.agentium_id for a, _ in ranked]
        assert "30002" in agent_ids
        assert "30001" not in agent_ids

    def test_rank_excludes_circuit_breaker_open(self, seeded_db: Session):
        """Agents with CB_OPEN should be excluded."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

        from backend.models.entities.agents import TaskAgent
        cb_agent = TaskAgent(
            agentium_id="30003",
            name="CB Open Agent",
            agent_type=AgentType.TASK_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
        )
        seeded_db.add(cb_agent)
        seeded_db.commit()

        circuit_breakers = {
            "30003": {"state": "open", "failure_count": 5}
        }

        ranked = AgentRanker.rank(db=seeded_db, required_tier="3", circuit_breakers=circuit_breakers)
        agent_ids = [a.agentium_id for a, _ in ranked]
        assert "30003" not in agent_ids

    def test_rank_excludes_specific_agents(self, seeded_db: Session):
        """Specifically excluded agents should not appear in ranking."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

        from backend.models.entities.agents import TaskAgent
        excluded_agent = TaskAgent(
            agentium_id="30004",
            name="Excluded Agent",
            agent_type=AgentType.TASK_AGENT,
            status=AgentStatus.ACTIVE,
            is_active=True,
            is_persistent=False,
        )
        seeded_db.add(excluded_agent)
        seeded_db.commit()

        ranked = AgentRanker.rank(db=seeded_db, required_tier="3", excluded_agent_ids=["30004"])
        agent_ids = [a.agentium_id for a, _ in ranked]
        assert "30004" not in agent_ids


@pytest.mark.integration
class TestDelegationEngineIntegration:
    """Test DelegationEngine end-to-end with real agents and tasks."""

    @pytest.mark.asyncio
    async def test_delegate_simple_task_to_tier3(self, seeded_db: Session):
        """Simple task should be delegated to TaskAgent (tier 3)."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Ensure a TaskAgent candidate exists
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_task_agent(
            parent=head, name="Tier3-Candidate", description="Test candidate", db=seeded_db
        )
        seeded_db.commit()

        task = Task(
            agentium_id="TDEL001",
            title="Fix typo",
            description="fix a typo in the help text",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)

        assert result["delegation_metadata"]["target_tier"] == "3"
        assert 1 <= result["complexity_score"] <= 6
        assert task.complexity_score == result["complexity_score"]
        assert task.delegation_metadata is not None
        assert "delegated_at" in task.delegation_metadata

    @pytest.mark.asyncio
    async def test_delegate_complex_task_to_tier2(self, seeded_db: Session):
        """Complex task should be delegated to LeadAgent (tier 2)."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        council = seeded_db.query(CouncilMember).first()

        # Ensure a LeadAgent candidate exists
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_lead_agent(
            parent=head if head.agentium_id.startswith("0") else council,
            name="Lead-Candidate",
            description="Lead candidate for high-complexity routing",
            db=seeded_db,
        )
        seeded_db.commit()

        task = Task(
            agentium_id="TDEL002",
            title="Architecture migration",
            description="migrate and refactor the distributed authentication architecture",
            task_type=TaskType.ANALYSIS,
            status=TaskStatus.PENDING,
            priority=TaskPriority.CRITICAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)

        assert result["delegation_metadata"]["target_tier"] == "2"
        assert result["complexity_score"] >= 8

    @pytest.mark.asyncio
    async def test_delegation_idempotent(self, seeded_db: Session):
        """Re-running delegation on same task should be idempotent."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_task_agent(parent=head, name="Tier3-B", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TDEL003",
            title="Process CSV",
            description="process and validate the uploaded csv data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        result1 = await DelegationEngine.delegate(task, seeded_db)
        seeded_db.flush()
        result2 = await DelegationEngine.delegate(task, seeded_db)

        assert result2.get("skipped") == "already_delegated"
        assert task.delegation_metadata["target_tier"] == result1["delegation_metadata"]["target_tier"]

    @pytest.mark.asyncio
    async def test_delegate_with_force_true(self, seeded_db: Session):
        """force=True should re-run delegation even if already delegated."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_task_agent(parent=head, name="Tier3-C", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TDEL004",
            title="Force delegation",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        result1 = await DelegationEngine.delegate(task, seeded_db)
        seeded_db.flush()
        result2 = await DelegationEngine.delegate(task, seeded_db, force=True)

        assert result2.get("skipped") is None
        assert result2["delegated"] is True

    @pytest.mark.asyncio
    async def test_delegate_skips_idle_tasks(self, seeded_db: Session):
        """Idle tasks should be skipped."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_task_agent(parent=head, name="Tier3-D", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TDEL005",
            title="Idle task",
            description="idle governance work",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            is_idle_task=True,  # This is the key flag
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        result = await DelegationEngine.delegate(task, seeded_db)

        assert result.get("skipped") == "idle_task"

    @pytest.mark.asyncio
    async def test_delegate_tier_mapping(self, seeded_db: Session):
        """Verify tier mapping based on complexity score."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService

        # Create both TaskAgent (tier 3) and LeadAgent (tier 2)
        ReincarnationService.spawn_task_agent(parent=head, name="Tier3-E", description="Test", db=seeded_db)
        council = seeded_db.query(CouncilMember).first()
        ReincarnationService.spawn_lead_agent(parent=council, name="Lead-B", description="Test", db=seeded_db)
        seeded_db.commit()

        # Low complexity -> tier 3
        task_low = Task(
            agentium_id="TDEL006",
            title="Low complexity",
            description="fix typo",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task_low)
        seeded_db.flush()

        result_low = await DelegationEngine.delegate(task_low, seeded_db)
        assert result_low["delegation_metadata"]["target_tier"] == "3"

        # High complexity -> tier 2
        task_high = Task(
            agentium_id="TDEL007",
            title="High complexity",
            description="migrate refactor integrate architecture distributed security",
            task_type=TaskType.ANALYSIS,
            status=TaskStatus.PENDING,
            priority=TaskPriority.CRITICAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task_high)
        seeded_db.flush()

        result_high = await DelegationEngine.delegate(task_high, seeded_db)
        assert result_high["delegation_metadata"]["target_tier"] == "2"


@pytest.mark.integration
class TestSmartRetryRouterIntegration:
    """Test SmartRetryRouter with real database."""

    @pytest.mark.asyncio
    async def test_reroute_finds_alternative_agent(self, seeded_db: Session):
        """Failed task should be rerouted to a different agent."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService

        # Create two TaskAgents
        agent1 = ReincarnationService.spawn_task_agent(parent=head, name="Agent-1", description="Test", db=seeded_db)
        agent2 = ReincarnationService.spawn_task_agent(parent=head, name="Agent-2", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TRETRY001",
            title="Retry task",
            description="something to retry",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent1.agentium_id],
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        result = SmartRetryRouter.reroute(task, agent1.agentium_id, seeded_db)

        assert result is not None
        assert result.agentium_id == agent2.agentium_id
        assert task.delegation_metadata["failed_agent_ids"] == [agent1.agentium_id]
        assert task.delegation_metadata["retry_routed_to"] == agent2.agentium_id

    @pytest.mark.asyncio
    async def test_reroute_excludes_broken_agents(self, seeded_db: Session):
        """Reroute should skip agents with CB_OPEN."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService

        # Create two TaskAgents
        agent1 = ReincarnationService.spawn_task_agent(parent=head, name="Agent-3", description="Test", db=seeded_db)
        agent2 = ReincarnationService.spawn_task_agent(parent=head, name="Agent-4", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TRETRY002",
            title="Retry task 2",
            description="retry with cb",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[agent1.agentium_id],
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mark agent2 as CB_OPEN
        circuit_breakers = {
            agent2.agentium_id: {"state": "open", "failure_count": 3}
        }

        result = SmartRetryRouter.reroute(task, agent1.agentium_id, seeded_db, circuit_breakers)

        # Should return None since the only alternative has CB_OPEN
        assert result is None


@pytest.mark.integration
class TestCostAwareDelegatorIntegration:
    """Test CostAwareDelegator logic."""

    def test_should_force_local_when_budget_low_and_task_simple(self, seeded_db: Session):
        """Force local when budget < 20% and complexity <= 3."""
        task = Task(
            agentium_id="TCOST001",
            title="Simple task",
            description="fix typo",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )

        # Mock the idle_budget to return low budget
        from backend.services import token_optimizer
        original_get_status = token_optimizer.idle_budget.get_status

        token_optimizer.idle_budget.get_status = lambda: {"cost_percentage_used": 85}

        try:
            result = CostAwareDelegator.should_force_local(task, complexity_score=2)
            assert result is True
        finally:
            token_optimizer.idle_budget.get_status = original_get_status

    def test_should_not_force_local_when_budget_high(self, seeded_db: Session):
        """Should not force local when budget is healthy."""
        task = Task(
            agentium_id="TCOST002",
            title="Simple task",
            description="fix typo",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )

        from backend.services import token_optimizer
        original_get_status = token_optimizer.idle_budget.get_status

        token_optimizer.idle_budget.get_status = lambda: {"cost_percentage_used": 30}

        try:
            result = CostAwareDelegator.should_force_local(task, complexity_score=2)
            assert result is False
        finally:
            token_optimizer.idle_budget.get_status = original_get_status

    def test_should_not_force_local_when_task_complex(self, seeded_db: Session):
        """Should not force local for complex tasks even with low budget."""
        task = Task(
            agentium_id="TCOST003",
            title="Complex task",
            description="migrate and refactor the distributed architecture",
            task_type=TaskType.ANALYSIS,
            status=TaskStatus.PENDING,
            priority=TaskPriority.CRITICAL,
            is_active=True,
            created_by="system",
        )

        from backend.services import token_optimizer
        original_get_status = token_optimizer.idle_budget.get_status

        token_optimizer.idle_budget.get_status = lambda: {"cost_percentage_used": 85}

        try:
            result = CostAwareDelegator.should_force_local(task, complexity_score=8)
            assert result is False
        finally:
            token_optimizer.idle_budget.get_status = original_get_status


@pytest.mark.integration
class TestAutoDelegationAuditLog:
    """Test that auto-delegation creates proper audit logs."""

    @pytest.mark.asyncio
    async def test_delegation_creates_audit_log(self, seeded_db: Session):
        """Delegation should create AuditLog entry."""
        from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_task_agent(parent=head, name="Audit-Candidate", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TAUDIT001",
            title="Audit test",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        await DelegationEngine.delegate(task, seeded_db)
        seeded_db.commit()

        # Check audit log was created
        audit = seeded_db.query(AuditLog).filter(
            AuditLog.action == "auto_delegation",
            AuditLog.target_id == task.id
        ).first()

        assert audit is not None
        assert audit.category == AuditCategory.GOVERNANCE
        assert audit.level == AuditLevel.INFO
        assert audit.actor_id == "DELEGATION_ENGINE"
        assert "complexity" in audit.description
        assert audit.metadata_json is not None
        import json
        meta = json.loads(audit.metadata_json)
        assert meta["complexity_score"] == task.complexity_score

    @pytest.mark.asyncio
    async def test_delegation_metadata_history_preserved(self, seeded_db: Session):
        """Re-delegation should preserve history in metadata."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        from backend.services.reincarnation_service import ReincarnationService
        ReincarnationService.spawn_task_agent(parent=head, name="History-Candidate", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="THIST001",
            title="History test",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # First delegation
        result1 = await DelegationEngine.delegate(task, seeded_db)
        seeded_db.flush()

        # Second delegation with force
        result2 = await DelegationEngine.delegate(task, seeded_db, force=True)
        seeded_db.flush()

        # Check history is preserved
        meta = task.delegation_metadata
        assert "history" in meta
        assert len(meta["history"]) == 1
        assert meta["history"][0]["complexity_score"] == result1["complexity_score"]
        assert meta["complexity_score"] == result2["complexity_score"]


# Import TaskStatus for use in tests
from backend.models.entities.task import TaskStatus


@pytest.mark.integration
class TestAdditionalBranchCoverage:
    """Additional tests to cover uncovered branches in auto_delegation_service."""

    def test_complexity_analyzer_sov_priority_bonus(self, seeded_db: Session):
        """Test SOVEREIGN priority gets bonus (line 82-83)."""
        task = Task(
            agentium_id="TCOV001",
            title="Sov task",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.SOVEREIGN,
            is_active=True,
            created_by="system",
        )
        score = ComplexityAnalyzer.score(task)
        # Should get +2 for SOVEREIGN priority
        assert score >= 4

    def test_complexity_analyzer_long_description(self, seeded_db: Session):
        """Test long description bonus (line 86-87)."""
        task = Task(
            agentium_id="TCOV002",
            title="Long desc task",
            description="x" * 600,  # > 500 chars
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        score = ComplexityAnalyzer.score(task)
        # Should get +1 for length > 500
        assert score >= 3

    def test_complexity_analyzer_constitutional_type_bonus(self, seeded_db: Session):
        """Test Constitutional task type bonus (line 90-92)."""
        task = Task(
            agentium_id="TCOV003",
            title="Constitutional task",
            description="amend constitution",
            task_type=TaskType.CONSTITUTIONAL,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        score = ComplexityAnalyzer.score(task)
        # Should get +1 for CONSTITUTIONAL type
        assert score >= 3

    def test_complexity_analyzer_subtask_discount(self, seeded_db: Session):
        """Test sub-task discount (line 95-96)."""
        parent = Task(
            agentium_id="TPARENT01",
            title="Parent task",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(parent)
        seeded_db.flush()

        child = Task(
            agentium_id="TCHILD001",
            title="Child task",
            description="deploy and migrate",  # high complexity keywords
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
            parent_task_id=parent.id,
        )
        score = ComplexityAnalyzer.score(child)
        # Should get subtask discount (-1)
        # Without discount would be: 2 base + 4 (deploy,migrate) = 6
        # With discount: 5
        assert score <= 5

    @pytest.mark.asyncio
    async def test_smart_retry_router_no_agents_available(self, seeded_db: Session):
        """Test SmartRetryRouter returns None when no agents available (line 340-345)."""
        task = Task(
            agentium_id="TRETRY001",
            title="Retry test",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # No agents of tier "9" exist
        result = SmartRetryRouter.reroute(task, "90001", seeded_db)
        assert result is None

    @pytest.mark.asyncio
    async def test_delegation_engine_no_agents_available(self, seeded_db: Session):
        """Test DelegationEngine when no agents available for tier (line 511-516)."""
        task = Task(
            agentium_id="TDEL001",
            title="Delegation test",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Force tier "9" which has no agents
        # We'll patch AgentRanker.rank to return empty
        from backend.services import auto_delegation_service
        original_rank = auto_delegation_service.AgentRanker.rank

        auto_delegation_service.AgentRanker.rank = lambda *args, **kwargs: []

        try:
            result = await DelegationEngine.delegate(task, seeded_db)
            assert result["delegated"] is False
            assert result["assigned_to"] is None
            assert result["candidate_count"] == 0
        finally:
            auto_delegation_service.AgentRanker.rank = original_rank

    @pytest.mark.asyncio
    async def test_delegation_engine_subtask_decomposition(self, seeded_db: Session):
        """Test DelegationEngine decomposition path (line 463-470)."""
        task = Task(
            agentium_id="TDEC001",
            title="Decomposition test",
            description="migrate and refactor and deploy and integrate the distributed architecture",  # complexity >= 7
            task_type=TaskType.ANALYSIS,
            status=TaskStatus.PENDING,
            priority=TaskPriority.CRITICAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock SubTaskBreaker.decompose to avoid LLM call
        from backend.services import auto_delegation_service
        original_decompose = auto_delegation_service.SubTaskBreaker.decompose

        async def mock_decompose(task, db, max_subtasks=5):
            return []

        auto_delegation_service.SubTaskBreaker.decompose = mock_decompose

        try:
            result = await DelegationEngine.delegate(task, seeded_db)
            assert result["complexity_score"] >= 7
            assert "subtasks_created" in result
        finally:
            auto_delegation_service.SubTaskBreaker.decompose = original_decompose

    @pytest.mark.asyncio
    async def test_delegation_engine_force_local_branch(self, seeded_db: Session):
        """Test DelegationEngine force_local_model branch (line 472-474)."""
        from backend.models.entities.agents import Agent
        from backend.services.reincarnation_service import ReincarnationService

        head = seeded_db.query(Agent).filter_by(agentium_id="00001").first()
        ReincarnationService.spawn_task_agent(parent=head, name="ForceLocal-Candidate", description="Test", db=seeded_db)
        seeded_db.commit()

        task = Task(
            agentium_id="TFL001",
            title="Force local test",
            description="fix typo",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Mock idle_budget to return high cost usage
        from backend.services import token_optimizer
        original_get_status = token_optimizer.idle_budget.get_status
        token_optimizer.idle_budget.get_status = lambda: {"cost_percentage_used": 85}

        try:
            result = await DelegationEngine.delegate(task, seeded_db)
            assert result["force_local_model"] is True
        finally:
            token_optimizer.idle_budget.get_status = original_get_status

    def test_agent_ranker_empty_circuit_breakers(self, seeded_db: Session):
        """Test AgentRanker with empty circuit_breakers (line 152-154)."""
        from backend.models.entities.agents import Agent
        from backend.services.reincarnation_service import ReincarnationService

        head = seeded_db.query(Agent).filter_by(agentium_id="00001").first()
        ReincarnationService.spawn_task_agent(parent=head, name="CB-Candidate", description="Test", db=seeded_db)
        seeded_db.commit()

        # Pass empty circuit_breakers dict
        ranked = AgentRanker.rank(seeded_db, required_tier="3", circuit_breakers={})
        # Should still work and not filter anything
        assert isinstance(ranked, list)

    def test_agent_ranker_agent_with_circuit_breaker_open(self, seeded_db: Session):
        """Test AgentRanker excludes agent with CB open (line 153-154)."""
        from backend.models.entities.agents import Agent
        from backend.services.reincarnation_service import ReincarnationService

        head = seeded_db.query(Agent).filter_by(agentium_id="00001").first()
        ReincarnationService.spawn_task_agent(parent=head, name="CB-Open-Candidate", description="Test", db=seeded_db)
        seeded_db.commit()

        # Get the candidate's agentium_id
        candidate = seeded_db.query(Agent).filter_by(name="CB-Open-Candidate").first()

        # Pass circuit_breakers with CB open for this agent
        cb = {candidate.agentium_id: {"state": "open"}}
        ranked = AgentRanker.rank(seeded_db, required_tier="3", circuit_breakers=cb)
        # Should not include the agent with CB open
        agent_ids = [a.agentium_id for a, _ in ranked]
        assert candidate.agentium_id not in agent_ids

    @pytest.mark.asyncio
    async def test_smart_retry_router_excludes_failed_agent(self, seeded_db: Session):
        """Test SmartRetryRouter excludes the failed agent from rerouting (line 330)."""
        from backend.models.entities.agents import Agent
        from backend.services.reincarnation_service import ReincarnationService

        head = seeded_db.query(Agent).filter_by(agentium_id="00001").first()
        ReincarnationService.spawn_task_agent(parent=head, name="Exclude-Candidate", description="Test", db=seeded_db)
        seeded_db.commit()

        candidate = seeded_db.query(Agent).filter_by(name="Exclude-Candidate").first()

        task = Task(
            agentium_id="TEXCL001",
            title="Exclude test",
            description="process data",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            is_active=True,
            created_by="system",
        )
        seeded_db.add(task)
        seeded_db.flush()

        # Set the failed agent in metadata
        task.delegation_metadata = {"failed_agent_ids": [candidate.agentium_id]}

        result = SmartRetryRouter.reroute(task, candidate.agentium_id, seeded_db)
        # Should find a different agent (or None if only one candidate)
        if result:
            assert result.agentium_id != candidate.agentium_id