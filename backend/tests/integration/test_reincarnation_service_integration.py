"""Integration tests for ReincarnationService."""
import pytest
from sqlalchemy.orm import Session
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from backend.services.reincarnation_service import ReincarnationService
from backend.services.context_manager import context_manager
from backend.models.entities.agents import (
    HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent,
    AgentType, AgentStatus
)
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.services.capability_registry import CapabilityRegistry, Capability
from backend.services.overflow_recovery import OverflowRecoveryService


@pytest.fixture(autouse=True)
def reset_context_manager():
    """Reset context manager state before each test to prevent state leaks."""
    context_manager.agent_contexts.clear()
    yield
    context_manager.agent_contexts.clear()


@pytest.mark.integration
class TestReincarnationServiceIDGeneration:
    """Test ID generation with real database and concurrency control."""

    def test_generate_task_agent_id_sequential(self, seeded_db: Session):
        """Task agent IDs should be sequential from current state."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Ensure head has SPAWN_TASK_AGENT capability
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        # Spawn first task agent - ID is consumed on creation
        task_agent1 = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Test Task Agent 1",
            description="First test task agent",
            db=seeded_db
        )
        id1 = task_agent1.agentium_id
        assert id1.startswith("3")
        assert len(id1) == 5

        # Spawn second task agent - should get next sequential ID
        task_agent2 = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Test Task Agent 2",
            description="Second test task agent",
            db=seeded_db
        )
        id2 = task_agent2.agentium_id
        assert id2.startswith("3")
        # IDs should be sequential from the generated ones, not from pool start
        assert int(id2) == int(id1) + 1

    def test_generate_lead_agent_id_sequential(self, seeded_db: Session):
        """Lead agent IDs should be sequential from current state."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Ensure head has SPAWN_LEAD capability
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_LEAD, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        # Spawn first lead agent - ID is consumed on creation
        lead1 = ReincarnationService.spawn_lead_agent(
            parent=head,
            name="Test Lead 1",
            description="First test lead agent",
            db=seeded_db
        )
        id1 = lead1.agentium_id
        assert id1.startswith("2")
        assert len(id1) == 5

        # Spawn second lead agent - should get next sequential ID
        lead2 = ReincarnationService.spawn_lead_agent(
            parent=head,
            name="Test Lead 2",
            description="Second test lead agent",
            db=seeded_db
        )
        id2 = lead2.agentium_id
        assert id2.startswith("2")
        assert int(id2) == int(id1) + 1

    def test_generate_id_invalid_tier_raises(self, seeded_db: Session):
        """Invalid tier should raise ValueError."""
        with pytest.raises(ValueError, match="Invalid tier"):
            ReincarnationService.generate_id_with_retry("invalid", seeded_db)


@pytest.mark.integration
class TestReincarnationServiceSpawn:
    """Test agent spawning with real database."""

    @pytest.mark.asyncio
    async def test_spawn_task_agent_success(self, seeded_db: Session):
        """Task agent spawn should succeed with valid parent."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Ensure head has SPAWN_TASK_AGENT capability
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        task_agent = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Test Task Agent",
            description="Integration test task agent",
            db=seeded_db
        )

        assert task_agent.agentium_id.startswith("3")
        assert task_agent.name == "Test Task Agent"
        assert task_agent.agent_type == AgentType.TASK_AGENT
        assert task_agent.status == AgentStatus.ACTIVE
        assert task_agent.parent_id == head.id
        assert task_agent.is_persistent is False

        # Verify ethos was created
        assert task_agent.ethos_id is not None

        # Verify audit log created
        audit = seeded_db.query(AuditLog).filter_by(
            action="agent_spawned",
            target_id=task_agent.agentium_id
        ).first()
        assert audit is not None

    @pytest.mark.asyncio
    async def test_spawn_task_agent_with_custom_capabilities(self, seeded_db: Session):
        """Task agent spawn should grant custom capabilities."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        task_agent = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Capable Agent",
            description="Test with capabilities",
            capabilities=["use_tools", "execute_task"],
            db=seeded_db
        )

        caps = CapabilityRegistry.get_agent_capabilities(task_agent)
        granted = caps["effective_capabilities"]
        assert "use_tools" in granted
        assert "execute_task" in granted

    @pytest.mark.asyncio
    async def test_spawn_task_agent_permission_denied(self, seeded_db: Session):
        """Task agent spawn should fail without SPAWN_TASK_AGENT capability."""
        # Create a LeadAgent without spawn capability (Lead has it by tier, so we need to test a TaskAgent)
        # Or create a TaskAgent to test - TaskAgents cannot spawn
        task_agent = seeded_db.query(TaskAgent).first()
        if not task_agent:
            # Spawn one to test
            head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
            CapabilityRegistry.grant_capability(
                head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
            )
            seeded_db.commit()
            task_agent = ReincarnationService.spawn_task_agent(
                parent=head, name="Test Parent", description="Test", db=seeded_db
            )
            seeded_db.commit()

        # TaskAgents cannot spawn Task Agents
        with pytest.raises(PermissionError, match="cannot spawn Task Agents"):
            ReincarnationService.spawn_task_agent(
                parent=task_agent,
                name="Unauthorized",
                description="Should fail",
                db=seeded_db
            )

    @pytest.mark.asyncio
    async def test_spawn_lead_agent_success(self, seeded_db: Session):
        """Lead agent spawn should succeed with valid parent."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Grant SPAWN_LEAD capability
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_LEAD, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        lead_agent = ReincarnationService.spawn_lead_agent(
            parent=head,
            name="Test Lead Agent",
            description="Integration test lead agent",
            db=seeded_db
        )

        assert lead_agent.agentium_id.startswith("2")
        assert lead_agent.name == "Test Lead Agent"
        assert lead_agent.agent_type == AgentType.LEAD_AGENT
        assert lead_agent.status == AgentStatus.ACTIVE
        assert lead_agent.parent_id == head.id

        # Verify ethos created
        assert lead_agent.ethos_id is not None

        # Verify audit log
        audit = seeded_db.query(AuditLog).filter_by(
            action="lead_spawned",
            target_id=lead_agent.agentium_id
        ).first()
        assert audit is not None

    @pytest.mark.asyncio
    async def test_spawn_lead_agent_council_parent(self, seeded_db: Session):
        """Council member should be able to spawn lead agent."""
        council = seeded_db.query(CouncilMember).first()
        assert council is not None

        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            council, Capability.SPAWN_LEAD, head, "Test grant", db=seeded_db
        )
        seeded_db.commit()

        lead_agent = ReincarnationService.spawn_lead_agent(
            parent=council,
            name="Lead from Council",
            description="Spawned by council member",
            db=seeded_db
        )

        assert lead_agent.agentium_id.startswith("2")
        assert lead_agent.parent_id == council.id


@pytest.mark.integration
class TestReincarnationServicePromotion:
    """Test Task Agent to Lead Agent promotion."""

    @pytest.mark.asyncio
    async def test_promote_task_agent_to_lead(self, seeded_db: Session):
        """Task agent promotion should create Lead Agent and transfer tasks."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Grant capabilities to head
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_LEAD, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        # Spawn a Task Agent
        task_agent = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Promotable Task Agent",
            description="Will be promoted",
            db=seeded_db
        )
        seeded_db.commit()

        # Create an active task assigned to the task agent
        task = Task(
            agentium_id="TPROMO001",
            title="Promotion Test Task",
            description="Task to be transferred on promotion",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[task_agent.agentium_id],  # List of IDs
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.commit()

        # Promote the task agent
        lead_agent = ReincarnationService.promote_to_lead(
            agent_id=task_agent.agentium_id,
            promoted_by=head,
            reason="Exceptional performance demonstrated",
            db=seeded_db
        )

        # Verify new Lead Agent created
        assert lead_agent.agentium_id.startswith("2")
        assert lead_agent.name == f"{task_agent.name} (Promoted)"
        assert lead_agent.ethos_id == task_agent.ethos_id  # Inherits ethos

        # Verify old task agent is terminated
        seeded_db.refresh(task_agent)
        assert task_agent.status == AgentStatus.TERMINATED
        assert task_agent.is_active is False
        assert "Promoted to Lead Agent" in task_agent.termination_reason

        # Verify task was reassigned to new lead
        seeded_db.refresh(task)
        assert task_agent.agentium_id not in task.assigned_task_agent_ids
        assert lead_agent.agentium_id in task.assigned_task_agent_ids

        # Verify audit logs
        promotion_audit = seeded_db.query(AuditLog).filter_by(
            action="agent_promoted",
            target_id=lead_agent.agentium_id
        ).first()
        assert promotion_audit is not None

    @pytest.mark.asyncio
    async def test_promote_invalid_agent_type_raises(self, seeded_db: Session):
        """Promoting non-Task-Agent should raise ValueError."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        council = seeded_db.query(CouncilMember).first()
        assert council is not None

        with pytest.raises(ValueError, match="Only Task Agents.*can be promoted to Lead"):
            ReincarnationService.promote_to_lead(
                agent_id=council.agentium_id,  # Council member, not task
                promoted_by=head,
                reason="Invalid promotion",
                db=seeded_db
            )

    @pytest.mark.asyncio
    async def test_promote_insufficient_permission_raises(self, seeded_db: Session):
        """Promotion by Lead Agent should fail."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        lead = seeded_db.query(LeadAgent).first()

        if lead:
            CapabilityRegistry.grant_capability(
                head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
            )
            seeded_db.commit()

            task_agent = ReincarnationService.spawn_task_agent(
                parent=head, name="Test", description="Test", db=seeded_db
            )
            seeded_db.commit()

            with pytest.raises(PermissionError, match="cannot promote agents"):
                ReincarnationService.promote_to_lead(
                    agent_id=task_agent.agentium_id,
                    promoted_by=lead,  # Lead cannot promote
                    reason="Unauthorized",
                    db=seeded_db
                )


@pytest.mark.integration
class TestReincarnationServiceLiquidation:
    """Test agent liquidation with cleanup."""

    @pytest.mark.asyncio
    async def test_liquidate_task_agent_by_head(self, seeded_db: Session):
        """Head should be able to liquidate Task Agent with task reassignment."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        # Grant spawn capability
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        # Spawn a Task Agent
        task_agent = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Liquidation Target",
            description="Will be liquidated",
            db=seeded_db
        )
        seeded_db.commit()

        # Create an active task
        task = Task(
            agentium_id="TLIQ001",
            title="Task to Reassign",
            description="Should be reassigned to parent",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.PENDING,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[task_agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.commit()

        # Liquidate the agent
        summary = ReincarnationService.liquidate_agent(
            agent_id=task_agent.agentium_id,
            liquidated_by=head,
            reason="Performance below threshold",
            db=seeded_db
        )

        # Verify summary
        assert summary["agent_id"] == task_agent.agentium_id
        assert summary["liquidated_by"] == head.agentium_id
        assert summary["tasks_reassigned"] == 1
        assert summary["tasks_cancelled"] == 0
        assert summary["capabilities_revoked"] >= 0

        # Verify task was reassigned to parent (head)
        seeded_db.refresh(task)
        assert task.assigned_task_agent_ids == [head.agentium_id]
        assert task.status == TaskStatus.PENDING

        # Verify agent is terminated
        seeded_db.refresh(task_agent)
        assert task_agent.status == AgentStatus.TERMINATED
        assert task_agent.is_active is False
        assert task_agent.ethos_id is None  # Ethos deleted

        # Verify audit log
        audit = seeded_db.query(AuditLog).filter_by(
            action="agent_liquidated",
            target_id=task_agent.agentium_id
        ).first()
        assert audit is not None

    @pytest.mark.asyncio
    async def test_liquidate_lead_agent_by_head(self, seeded_db: Session):
        """Head should be able to liquidate Lead Agent."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        lead = seeded_db.query(LeadAgent).first()
        assert lead is not None
        assert lead.parent == head

        summary = ReincarnationService.liquidate_agent(
            agent_id=lead.agentium_id,
            liquidated_by=head,
            reason="Department restructure",
            db=seeded_db
        )

        assert summary["agent_id"] == lead.agentium_id
        seeded_db.refresh(lead)
        assert lead.status == AgentStatus.TERMINATED

    @pytest.mark.asyncio
    async def test_liquidate_protects_head_agent(self, seeded_db: Session):
        """Head agent (00001) should be protected from liquidation."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

        with pytest.raises(ValueError, match="Cannot liquidate Head of Council"):
            ReincarnationService.liquidate_agent(
                agent_id="00001",
                liquidated_by=head,
                reason="Should fail",
                db=seeded_db
            )

    @pytest.mark.asyncio
    async def test_liquidate_with_force_bypasses_head_protection(self, seeded_db: Session):
        """Force liquidation should work on Head (emergency use only)."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()

        summary = ReincarnationService.liquidate_agent(
            agent_id="00001",
            liquidated_by=head,
            reason="Emergency system shutdown",
            db=seeded_db,
            force=True
        )

        assert summary["agent_id"] == "00001"


@pytest.mark.integration
class TestReincarnationServiceCapacity:
    """Test capacity checking across tiers."""

    def test_get_available_capacity_structure(self, seeded_db: Session):
        """Capacity should return structured dict for all tiers."""
        capacity = ReincarnationService.get_available_capacity(seeded_db)

        assert isinstance(capacity, dict)
        expected_tiers = ["head", "council", "lead", "task", "critic"]
        for tier in expected_tiers:
            assert tier in capacity
            tier_data = capacity[tier]
            assert "used" in tier_data
            assert "available" in tier_data
            assert "max" in tier_data
            assert "percentage" in tier_data
            assert "warning" in tier_data
            assert "critical" in tier_data
            assert tier_data["used"] >= 0
            assert tier_data["available"] >= 0

    def test_get_available_capacity_head_low_usage(self, seeded_db: Session):
        """Head tier should have very low usage (only 00001)."""
        capacity = ReincarnationService.get_available_capacity(seeded_db)
        head_cap = capacity["head"]
        assert head_cap["used"] == 1  # Only 00001 exists
        assert head_cap["max"] == 9999
        assert head_cap["percentage"] < 1.0
        assert head_cap["warning"] is False
        assert head_cap["critical"] is False

    def test_get_available_capacity_task_increases_on_spawn(self, seeded_db: Session):
        """Task tier usage should increase when spawning agents."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        cap_before = ReincarnationService.get_available_capacity(seeded_db)
        used_before = cap_before["task"]["used"]

        ReincarnationService.spawn_task_agent(
            parent=head, name="Test1", description="Test", db=seeded_db
        )
        seeded_db.commit()

        cap_after = ReincarnationService.get_available_capacity(seeded_db)
        used_after = cap_after["task"]["used"]
        assert used_after == used_before + 1


@pytest.mark.integration
class TestReincarnationServiceReincarnation:
    """Test reincarnation cycle (context limit → death → successor)."""

    @pytest.mark.asyncio
    @patch("backend.services.reincarnation_service.LLMClient")
    async def test_execute_reincarnation_task_agent(self, mock_llm_client, seeded_db: Session):
        """Full reincarnation cycle for Task Agent."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        # Spawn a Task Agent
        task_agent = ReincarnationService.spawn_task_agent(
            parent=head,
            name="Reincarnating Agent",
            description="Will hit context limit",
            db=seeded_db
        )
        seeded_db.commit()

        # Mock LLM response for wisdom summarization
        mock_client = MagicMock()
        mock_llm_client.return_value = mock_client
        mock_client.generate = AsyncMock(return_value={
            "content": "Key lesson: Always validate inputs before processing. Validation is critical for defensive programming patterns.",
            "tokens_used": 50,
            "prompt_tokens": 30,
            "completion_tokens": 20,
            "latency_ms": 100,
            "model": "mock",
            "cost_usd": 0.001,
            "finish_reason": "stop"
        })

        # Create active task
        task = Task(
            agentium_id="TREINC001",
            title="Long Running Task",
            description="Task that triggers reincarnation",
            task_type=TaskType.EXECUTION,
            status=TaskStatus.IN_PROGRESS,
            priority=TaskPriority.NORMAL,
            assigned_task_agent_ids=[task_agent.agentium_id],
            supervisor_id=head.agentium_id,
            is_active=True,
            created_by=head.agentium_id,
        )
        seeded_db.add(task)
        seeded_db.commit()

        # Execute reincarnation
        result = await ReincarnationService.execute_reincarnation(
            agent=task_agent,
            db=seeded_db,
            conversation_context="Processed many tasks. Learned that validation is critical. Found bugs in edge cases.",
            current_task_id=task.id
        )

        # Verify result structure
        assert result["old_agent"] == task_agent.agentium_id
        assert result["incarnation_number"] == 1
        assert result["summarized"] is True
        assert result["ethos_updated"] is True
        assert result["terminated"] is True
        assert result["successor_spawned"] is True
        assert result["successor_id"] is not None
        assert result["successor_id"].startswith("3")  # Same tier
        assert result["task_transferred"] == task.id
        assert result["wisdom_added"] is not None
        assert "validation" in result["wisdom_added"].lower()

        # Verify old agent terminated
        seeded_db.refresh(task_agent)
        assert task_agent.status == AgentStatus.TERMINATED
        assert task_agent.is_active is False

        # Verify successor exists
        successor = seeded_db.query(TaskAgent).filter_by(agentium_id=result["successor_id"]).first()
        assert successor is not None
        assert successor.status == AgentStatus.ACTIVE
        assert successor.parent_id == task_agent.parent_id
        assert "Incarnation" in successor.name

        # Verify task transferred
        seeded_db.refresh(task)
        assert task.assigned_task_agent_ids == [result["successor_id"]]

        # Verify audit logs
        death_audit = seeded_db.query(AuditLog).filter_by(
            action="agent_death",
            target_id=task_agent.agentium_id
        ).first()
        assert death_audit is not None

        birth_audit = seeded_db.query(AuditLog).filter_by(
            action="agent_birth",
            target_id=result["successor_id"]
        ).first()
        assert birth_audit is not None

    @pytest.mark.asyncio
    @patch("backend.services.reincarnation_service.LLMClient")
    async def test_execute_reincarnation_head_agent_in_place(self, mock_llm_client, seeded_db: Session):
        """Head agent reincarnation should be in-place (same ID 00001)."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None
        assert head.incarnation_number == 1

        mock_client = MagicMock()
        mock_llm_client.return_value = mock_client
        mock_client.generate = AsyncMock(return_value={
            "content": "Head wisdom: Leadership requires balance.",
            "tokens_used": 30,
            "prompt_tokens": 20,
            "completion_tokens": 10,
            "latency_ms": 50,
            "model": "mock",
            "cost_usd": 0.0005,
            "finish_reason": "stop"
        })

        result = await ReincarnationService.execute_reincarnation(
            agent=head,
            db=seeded_db,
            conversation_context="Led council through many sessions.",
            current_task_id=None
        )

        assert result["old_agent"] == "00001"
        assert result["successor_id"] == "00001"  # Same ID!
        assert result["successor_spawned"] is True

        # Head should still exist and be ACTIVE
        seeded_db.refresh(head)
        assert head.agentium_id == "00001"
        assert head.status == AgentStatus.ACTIVE
        assert head.is_active is True
        assert head.incarnation_number == 2  # Incremented

    @pytest.mark.asyncio
    async def test_check_and_trigger_reincarnation_context_full(self, seeded_db: Session):
        """Context manager should trigger reincarnation when limit reached."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        task_agent = ReincarnationService.spawn_task_agent(
            parent=head, name="Context Test", description="Test", db=seeded_db
        )
        seeded_db.commit()

        # Register context tracking for the agent
        from backend.services.context_manager import context_manager
        context_manager.register_agent(task_agent.agentium_id, "gpt-4")

        # Fill context to trigger reincarnation - gpt-4 limit is 8192, 90% = 7373
        for i in range(30):
            context_manager.update_usage(
                agent_id=task_agent.agentium_id,
                tokens_used=8000  # Total tokens in context window - exceeds 90% threshold
            )

        # Should trigger
        with patch("backend.services.reincarnation_service.ReincarnationService.execute_reincarnation",
                   new_callable=AsyncMock) as mock_execute:
            mock_execute.return_value = {"successor_id": task_agent.agentium_id}

            result = await ReincarnationService.check_and_trigger_reincarnation(
                agent=task_agent,
                db=seeded_db,
                conversation_context="Full context here"
            )

            assert result is not None
            mock_execute.assert_called_once()

    @pytest.mark.asyncio
    async def test_check_and_trigger_reincarnation_not_triggered(self, seeded_db: Session):
        """Context below threshold should not trigger reincarnation."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        task_agent = ReincarnationService.spawn_task_agent(
            parent=head, name="Low Context", description="Test", db=seeded_db
        )
        seeded_db.commit()

        # Don't fill context - should be well below limit
        result = await ReincarnationService.check_and_trigger_reincarnation(
            agent=task_agent,
            db=seeded_db,
            conversation_context="Short context"
        )

        assert result is None


@pytest.mark.integration
class TestReincarnationServicePredecessorContext:
    """Test retrieving predecessor context for active agents."""

    @pytest.mark.asyncio
    @patch("backend.services.reincarnation_service.LLMClient")
    async def test_get_predecessor_context_after_reincarnation(self, mock_llm_client, seeded_db: Session):
        """Successor should be able to retrieve predecessor wisdom."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        CapabilityRegistry.grant_capability(
            head, Capability.SPAWN_TASK_AGENT, head, "Test grant", seeded_db
        )
        seeded_db.commit()

        task_agent = ReincarnationService.spawn_task_agent(
            parent=head, name="Original", description="Test", db=seeded_db
        )
        seeded_db.commit()

        mock_client = MagicMock()
        mock_llm_client.return_value = mock_client
        mock_client.generate = AsyncMock(return_value={
            "content": "Critical insight: Always test edge cases thoroughly.",
            "tokens_used": 25,
            "prompt_tokens": 15,
            "completion_tokens": 10,
            "latency_ms": 60,
            "model": "mock",
            "cost_usd": 0.0005,
            "finish_reason": "stop"
        })

        await ReincarnationService.execute_reincarnation(
            agent=task_agent,
            db=seeded_db,
            conversation_context="Learned that edge cases break systems",
            current_task_id=None
        )

        # Get successor from database using reincarnation result
        # Query for the successor agent (name pattern: "Original (Incarnation 2)")
        successors = seeded_db.query(TaskAgent).filter(
            TaskAgent.name.like("Original (Incarnation 2)%")
        ).all()

        assert len(successors) == 1, f"Expected 1 successor, found {len(successors)}"
        successor = successors[0]
        successor_id = successor.agentium_id
        assert successor is not None

        # Retrieve predecessor context
        context = ReincarnationService.get_predecessor_context(successor, seeded_db)

        assert context["has_predecessor"] is True
        assert context["predecessor_id"] == task_agent.agentium_id
        assert context["incarnation_number"] == 2
        assert context["wisdom_count"] == 1
        assert "edge cases" in context["wisdom_summary"].lower()

    def test_get_predecessor_context_no_predecessor(self, seeded_db: Session):
        """New agent without reincarnation should have no predecessor."""
        head = seeded_db.query(HeadOfCouncil).filter_by(agentium_id="00001").first()
        assert head is not None

        context = ReincarnationService.get_predecessor_context(head, seeded_db)
        # Head at incarnation 1 has no predecessor
        assert context["has_predecessor"] is False


@pytest.mark.integration
class TestReincarnationServiceOverflowRecovery:
    """Test overflow recovery integration."""

    def test_available_capacity_warning_threshold(self, seeded_db: Session):
        """Capacity percentage should warn at >80%."""
        # We can't easily fill the pool in tests, but we can check the logic
        capacity = ReincarnationService.get_available_capacity(seeded_db)

        for tier, data in capacity.items():
            used = data["used"]
            max_cap = data["max"]
            pct = (used / max_cap) * 100 if max_cap > 0 else 0

            if pct > 80:
                assert data["warning"] is True
            else:
                assert data["warning"] is False

            if pct > 95:
                assert data["critical"] is True
            else:
                assert data["critical"] is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])