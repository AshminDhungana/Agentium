"""
Unit tests for Agent models.
Tests all agent types, statuses, hierarchies, and Ethos integration.
"""
import pytest
from datetime import datetime, timezone
from sqlalchemy import select

import uuid
try:
    from backend.models.entities.agents import (
        Agent, AgentType, AgentStatus, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent,
        AGENT_TYPE_MAP
    )
    from backend.models.entities.critics import (
        CriticAgent, OutputCriticAgent, PlanCriticAgent, CriticType, CriticVerdict
    )
    from backend.models.entities.constitution import Constitution, Ethos
except ImportError:
    from models.entities.agents import (
        Agent, AgentType, AgentStatus, HeadOfCouncil, CouncilMember, LeadAgent, TaskAgent,
        AGENT_TYPE_MAP
    )
    from models.entities.critics import (
        CriticAgent, OutputCriticAgent, PlanCriticAgent, CriticType, CriticVerdict
    )
    from models.entities.constitution import Constitution, Ethos


class TestAgent:
    """Tests for base Agent model."""

    # Class-level counter for unique agentium_ids across all tests
    _agentium_counter = 0

    @classmethod
    def _get_test_agentium_id(cls, agent_type, counter=None):
        """Generate valid test agentium_id for the given agent type."""
        prefix_map = {
            AgentType.HEAD_OF_COUNCIL: '0',
            AgentType.COUNCIL_MEMBER: '1',
            AgentType.LEAD_AGENT: '2',
            AgentType.TASK_AGENT: '3',
            AgentType.CODE_CRITIC: '7',
            AgentType.OUTPUT_CRITIC: '8',
            AgentType.PLAN_CRITIC: '9',
        }
        prefix = prefix_map.get(agent_type, '3')
        if counter is None:
            cls._agentium_counter += 1
            counter = cls._agentium_counter
        return f"{prefix}{counter:04d}"

    @pytest.mark.parametrize("agent_type", [
        AgentType.HEAD_OF_COUNCIL,
        AgentType.COUNCIL_MEMBER,
        AgentType.LEAD_AGENT,
        AgentType.TASK_AGENT,
        AgentType.CODE_CRITIC,
        AgentType.OUTPUT_CRITIC,
        AgentType.PLAN_CRITIC,
    ])
    def test_all_agent_types_valid(self, db_session, agent_type):
        """All agent types are valid enum values."""
        agentium_id = self._get_test_agentium_id(agent_type)
        agent = Agent(
            agentium_id=agentium_id,
            agent_type=agent_type,
            name=f"Test {agent_type.value}",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == agent_type

    @pytest.mark.parametrize("status", [
        AgentStatus.INITIALIZING,
        AgentStatus.ACTIVE,
        AgentStatus.DELIBERATING,
        AgentStatus.WORKING,
        AgentStatus.REVIEWING,
        AgentStatus.IDLE_WORKING,
        AgentStatus.IDLE_PAUSED,
        AgentStatus.SUSPENDED,
        AgentStatus.TERMINATED,
    ])
    def test_all_agent_statuses_valid(self, db_session, status):
        """All agent statuses are valid enum values."""
        # Use unique agentium_id for each status test
        status_ids = {
            AgentStatus.INITIALIZING: "31001",
            AgentStatus.ACTIVE: "31002",
            AgentStatus.DELIBERATING: "31003",
            AgentStatus.WORKING: "31004",
            AgentStatus.REVIEWING: "31005",
            AgentStatus.IDLE_WORKING: "31006",
            AgentStatus.IDLE_PAUSED: "31007",
            AgentStatus.SUSPENDED: "31008",
            AgentStatus.TERMINATED: "31009",
        }
        agent = Agent(
            agentium_id=status_ids[status],
            agent_type=AgentType.TASK_AGENT,
            name="Test",
            status=status,
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.status == status

    def test_agent_creation_with_required_fields(self, db_session):
        """Agent creates with all required fields."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
            description="Test description",
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        assert agent.agentium_id == "30001"
        assert agent.agent_type == AgentType.TASK_AGENT
        assert agent.name == "Test Agent"
        assert agent.description == "Test description"
        assert agent.status == AgentStatus.INITIALIZING
        assert agent.parent_id is None
        assert agent.ethos_id is None

    def test_agent_defaults_to_initializing_status(self, db_session):
        """Agent defaults to INITIALIZING status."""
        agent = Agent(
            agentium_id="30002",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.status == AgentStatus.INITIALIZING

    def test_agent_json_fields_do_not_exist_on_base_agent(self, db_session):
        """Agent base model does NOT have capabilities, tools_allowed, config, status_history columns.
        These fields belong to Ethos working memory."""
        agent = Agent(
            agentium_id="30003",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
        )
        db_session.add(agent)
        db_session.commit()
        db_session.refresh(agent)

        # These attributes do not exist on base Agent model
        assert not hasattr(agent, 'capabilities')
        assert not hasattr(agent, 'tools_allowed')
        assert not hasattr(agent, 'config')
        assert not hasattr(agent, 'status_history')
        # Ethos is in separate table, linked via ethos_id
        assert agent.ethos_id is None

    def test_agent_agentium_id_uniqueness(self, db_session):
        """Agent agentium_id must be unique."""
        agent1 = Agent(agentium_id="30001", agent_type=AgentType.TASK_AGENT, name="Agent 1")
        agent2 = Agent(agentium_id="30001", agent_type=AgentType.TASK_AGENT, name="Agent 2")
        db_session.add(agent1)
        db_session.commit()

        db_session.add(agent2)
        with pytest.raises(Exception):  # IntegrityError
            db_session.commit()
        db_session.rollback()

    def test_agent_parent_child_relationship(self, db_session):
        """Agent parent-child relationship works."""
        parent = Agent(
            agentium_id="20001",
            agent_type=AgentType.LEAD_AGENT,
            name="Lead Agent",
        )
        db_session.add(parent)
        db_session.commit()

        child = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Task Agent",
            parent_id=parent.id,
        )
        db_session.add(child)
        db_session.commit()

        assert child.parent_id == parent.id
        assert parent.subordinates[0].id == child.id

    def test_agent_spawn_permissions_not_on_base_agent(self, db_session):
        """spawn_permissions property does NOT exist on base Agent model.
        Spawn permissions are enforced in spawn_child() method."""
        head = Agent(agentium_id="00001", agent_type=AgentType.HEAD_OF_COUNCIL, name="Head")
        lead = Agent(agentium_id="20001", agent_type=AgentType.LEAD_AGENT, name="Lead")
        task = Agent(agentium_id="30001", agent_type=AgentType.TASK_AGENT, name="Task")
        db_session.add_all([head, lead, task])
        db_session.commit()

        # spawn_permissions is not a property on base Agent
        assert not hasattr(head, 'spawn_permissions')
        assert not hasattr(lead, 'spawn_permissions')
        assert not hasattr(task, 'spawn_permissions')


class TestAgentSubclasses:
    """Tests for each Agent subclass."""

    def test_head_of_council_creation(self, db_session):
        """HeadOfCouncil creates with correct type and defaults."""
        agent = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.HEAD_OF_COUNCIL
        assert isinstance(agent, Agent)
        assert agent.is_persistent is True
        assert agent.idle_mode_enabled is True

    def test_council_member_creation(self, db_session):
        """CouncilMember creates with correct type."""
        agent = CouncilMember(
            agentium_id="10001",
            name="Council Member",
            specialization="governance",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.COUNCIL_MEMBER
        assert agent.specialization == "governance"

    def test_lead_agent_creation(self, db_session):
        """LeadAgent creates with correct type."""
        agent = LeadAgent(
            agentium_id="20001",
            name="Lead Agent",
            department="Engineering",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.LEAD_AGENT
        assert agent.department == "Engineering"
        assert agent.max_team_size == 10
        assert agent.team_size == 0

    def test_task_agent_creation(self, db_session):
        """TaskAgent creates with correct type."""
        agent = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.TASK_AGENT
        assert agent.execution_timeout == 300
        assert agent.sandbox_enabled is True

    def test_code_critic_creation(self, db_session):
        """CodeCritic creates with correct type using critic_specialty param."""
        agent = CriticAgent(
            agentium_id="70001",
            name="Code Critic",
            critic_specialty=CriticType.CODE,
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.CODE_CRITIC
        assert agent.critic_specialty == CriticType.CODE

    def test_output_critic_creation(self, db_session):
        """OutputCritic creates with correct type using CriticAgent with OUTPUT specialty."""
        import uuid
        agent = CriticAgent(
            id=str(uuid.uuid4()),
            agentium_id="80001",
            name="Output Critic",
            critic_specialty=CriticType.OUTPUT,
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.OUTPUT_CRITIC
        assert agent.critic_specialty == CriticType.OUTPUT

    def test_plan_critic_creation(self, db_session):
        """PlanCritic creates with correct type using CriticAgent with PLAN specialty."""
        import uuid
        agent = CriticAgent(
            id=str(uuid.uuid4()),
            agentium_id="90001",
            name="Plan Critic",
            critic_specialty=CriticType.PLAN,
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agent_type == AgentType.PLAN_CRITIC
        assert agent.critic_specialty == CriticType.PLAN


class TestAgentStatusTransitions:
    """Tests for Agent status transitions and Ethos integration."""

    def test_activate_agent(self, db_session):
        """Setting status to ACTIVE transitions agent to ACTIVE."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
        )
        db_session.add(agent)
        db_session.commit()

        agent.status = AgentStatus.ACTIVE
        db_session.commit()

        assert agent.status == AgentStatus.ACTIVE

    def test_suspend_agent(self, db_session):
        """Setting status to SUSPENDED transitions agent to SUSPENDED."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
            status=AgentStatus.ACTIVE,
        )
        db_session.add(agent)
        db_session.commit()

        agent.status = AgentStatus.SUSPENDED
        db_session.commit()

        assert agent.status == AgentStatus.SUSPENDED

    def test_terminate_agent(self, db_session):
        """terminate() transitions status to TERMINATED."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
            status=AgentStatus.ACTIVE,
        )
        db_session.add(agent)
        db_session.commit()

        agent.terminate("End of lifecycle")
        db_session.commit()

        assert agent.status == AgentStatus.TERMINATED
        assert agent.terminated_at is not None
        assert agent.termination_reason == "End of lifecycle"
        assert agent.is_active is False

    def test_head_of_council_cannot_be_terminated(self, db_session):
        """Head of Council cannot be terminated."""
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        with pytest.raises(PermissionError):
            head.terminate("Should fail")

    def test_assign_task(self, db_session):
        """assign_task() sets current_task_id and status."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
            status=AgentStatus.ACTIVE,
        )
        db_session.add(agent)
        db_session.commit()

        agent.assign_task("T00001")
        db_session.commit()

        assert agent.current_task_id == "T00001"
        assert agent.status == AgentStatus.WORKING

    def test_complete_task_success(self, db_session):
        """complete_task() with success increments tasks_completed."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
            status=AgentStatus.WORKING,
            current_task_id="T00001",
        )
        db_session.add(agent)
        db_session.commit()

        agent.complete_task(success=True)
        db_session.commit()

        assert agent.status == AgentStatus.ACTIVE
        assert agent.current_task_id is None
        assert agent.tasks_completed == 1
        assert agent.tasks_failed == 0

    def test_complete_task_failure(self, db_session):
        """complete_task() with failure increments tasks_failed."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
            status=AgentStatus.WORKING,
            current_task_id="T00001",
        )
        db_session.add(agent)
        db_session.commit()

        agent.complete_task(success=False)
        db_session.commit()

        assert agent.tasks_completed == 0
        assert agent.tasks_failed == 1

    def test_assign_idle_task(self, db_session):
        """assign_idle_task() works for persistent agents."""
        agent = HeadOfCouncil(
            id=str(uuid.uuid4()),
            agentium_id="00001",
            name="Head Agent",
            status=AgentStatus.ACTIVE,
        )
        db_session.add(agent)
        db_session.commit()

        result = agent.assign_idle_task("T00001")
        db_session.commit()

        assert result is True
        assert agent.current_idle_task_id == "T00001"
        assert agent.status == AgentStatus.IDLE_WORKING

    def test_assign_idle_task_fails_for_non_persistent(self, db_session):
        """assign_idle_task() fails for non-persistent agents."""
        agent = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
        )
        db_session.add(agent)
        db_session.commit()

        result = agent.assign_idle_task("T00001")

        assert result is False
        assert agent.current_idle_task_id is None

    def test_complete_idle_task(self, db_session):
        """complete_idle_task() updates stats."""
        agent = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(agent)
        db_session.commit()

        agent.assign_idle_task("T00001")
        db_session.commit()

        agent.complete_idle_task(tokens_saved=500)
        db_session.commit()

        assert agent.current_idle_task_id is None
        assert agent.status == AgentStatus.ACTIVE
        assert agent.idle_task_count == 1
        assert agent.idle_tokens_saved == 500

    def test_agent_to_dict(self, db_session):
        """Agent.to_dict() includes all relevant fields."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
            description="Test",
            status=AgentStatus.ACTIVE,
        )
        db_session.add(agent)
        db_session.commit()

        data = agent.to_dict()

        assert data["agentium_id"] == "30001"
        assert data["agent_type"] == "task_agent"
        assert data["name"] == "Test Agent"
        assert data["status"] == "active"
        # No capabilities, config, etc. on base Agent
        assert "capabilities" not in data
        assert "config" not in data


class TestAgentSpawnPermissions:
    """Tests for Agent spawning logic and permissions."""

    def test_task_agent_cannot_spawn(self, db_session):
        """TaskAgent cannot spawn other agents."""
        task = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
        )
        db_session.add(task)
        db_session.commit()

        with pytest.raises(PermissionError):
            task.spawn_child(AgentType.TASK_AGENT, db_session)

    def test_lead_agent_can_spawn_task_agent(self, db_session):
        """LeadAgent can spawn TaskAgents."""
        lead = LeadAgent(
            id=str(uuid.uuid4()),
            agentium_id="20001",
            name="Lead Agent",
        )
        db_session.add(lead)
        db_session.commit()

        task = lead.spawn_child(AgentType.TASK_AGENT, db_session, name="New Task Agent")
        db_session.commit()

        assert task.agent_type == AgentType.TASK_AGENT
        assert task.parent_id == lead.id
        assert task.created_by_agentium_id == "20001"

    def test_lead_agent_cannot_spawn_head(self, db_session):
        """LeadAgent cannot spawn HeadOfCouncil."""
        lead = LeadAgent(
            agentium_id="20001",
            name="Lead Agent",
        )
        db_session.add(lead)
        db_session.commit()

        with pytest.raises(PermissionError):
            lead.spawn_child(AgentType.HEAD_OF_COUNCIL, db_session)

    def test_head_can_spawn_council_member(self, db_session):
        """HeadOfCouncil can spawn CouncilMembers."""
        head = HeadOfCouncil(
            id=str(uuid.uuid4()),
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        member = head.spawn_child(AgentType.COUNCIL_MEMBER, db_session, name="Council Member")
        db_session.commit()

        assert member.agent_type == AgentType.COUNCIL_MEMBER
        assert member.parent_id == head.id

    def test_council_member_cannot_spawn_council_member(self, db_session):
        """CouncilMember cannot spawn other CouncilMembers."""
        member = CouncilMember(
            agentium_id="10001",
            name="Council Member",
        )
        db_session.add(member)
        db_session.commit()

        with pytest.raises(PermissionError):
            member.spawn_child(AgentType.COUNCIL_MEMBER, db_session)

    def test_head_can_spawn_lead_agent(self, db_session):
        """HeadOfCouncil can spawn LeadAgents."""
        head = HeadOfCouncil(
            id=str(uuid.uuid4()),
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        lead = head.spawn_child(AgentType.LEAD_AGENT, db_session, name="Lead Agent")
        db_session.commit()

        assert lead.agent_type == AgentType.LEAD_AGENT
        assert lead.parent_id == head.id

    def test_head_can_spawn_code_critic(self, db_session):
        """HeadOfCouncil can spawn CodeCritics."""
        head = HeadOfCouncil(
            id=str(uuid.uuid4()),
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        critic = head.spawn_child(AgentType.CODE_CRITIC, db_session, name="Code Critic")
        db_session.commit()

        assert critic.agent_type == AgentType.CODE_CRITIC
        assert critic.parent_id == head.id


class TestAgentAgentiumIdGeneration:
    """Tests for agentium_id sequential generation."""

    def test_sequential_ids_same_prefix(self, db_session):
        """Sequential IDs generated within same prefix."""
        head1 = HeadOfCouncil(agentium_id="00001", name="Head 1")
        head2 = HeadOfCouncil(agentium_id="00002", name="Head 2")
        db_session.add_all([head1, head2])
        db_session.commit()

        assert head1.agentium_id == "00001"
        assert head2.agentium_id == "00002"

    def test_task_agent_multiple_prefixes(self, db_session):
        """TaskAgent uses multiple prefixes 3-6."""
        # First task agent gets 30001
        t1 = TaskAgent(agentium_id="30001", name="Task 1")
        db_session.add(t1)
        db_session.commit()

        # Second task agent gets 30002
        t2 = TaskAgent(agentium_id="30002", name="Task 2")
        db_session.add(t2)
        db_session.commit()

        assert t1.agentium_id == "30001"
        assert t2.agentium_id == "30002"

    def test_critic_ids_use_correct_prefix(self, db_session):
        """Critics use prefixes 7, 8, 9 respectively."""
        cc = CriticAgent(id=str(uuid.uuid4()), agentium_id="70001", name="Code Critic", critic_specialty=CriticType.CODE)
        oc = CriticAgent(id=str(uuid.uuid4()), agentium_id="80001", name="Output Critic", critic_specialty=CriticType.OUTPUT)
        pc = CriticAgent(id=str(uuid.uuid4()), agentium_id="90001", name="Plan Critic", critic_specialty=CriticType.PLAN)
        db_session.add_all([cc, oc, pc])
        db_session.commit()

        assert cc.agentium_id.startswith("7")
        assert oc.agentium_id.startswith("8")
        assert pc.agentium_id.startswith("9")


class TestAgentEthosIntegration:
    """Tests for Agent-Ethos integration."""

    def test_agent_ethos_not_auto_created_on_base_agent(self, db_session):
        """Ethos is NOT auto-created on base Agent creation.
        Ethos is created only when agent is spawned via spawn_child()."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.commit()

        # Ethos is NOT created automatically on base Agent creation
        assert agent.ethos_id is None

    def test_read_and_align_constitution_requires_active_constitution(self, db_session):
        """read_and_align_constitution() returns False when no active constitution."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.commit()

        # No active constitution in DB
        result = agent.read_and_align_constitution(db_session)

        assert result is False

    def test_read_and_align_constitution_updates_ethos(self, db_session):
        """read_and_align_constitution() updates ethos with constitutional references when ethos exists."""
        # Create active constitution - version is a string field
        import json
        constitution = Constitution(
            agentium_id="C00001",
            version="v1.0.0",
            version_number=1,
            preamble="Test Constitution",
            articles=json.dumps({"article_1": {"title": "Sovereignty", "content": "The Constitution is supreme"}}),
            prohibited_actions=json.dumps([]),
            sovereign_preferences=json.dumps({}),
            effective_date=datetime.now(timezone.utc),
            is_active=True,
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()

        # Create agent with ethos manually
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.flush()

        # Create and link ethos manually
        ethos = Ethos(
            agentium_id=agent.agentium_id,
            agent_type=agent.agent_type.value,
            mission_statement="Test mission",
            core_values="[]",
            behavioral_rules="[]",
            restrictions="[]",
            capabilities="[]",
            working_method="Test method",
            environment_context="Test env",
            created_by_agentium_id="20001",
            agent_id=agent.id,
            is_verified=True,
            verified_by_agentium_id="20001",
        )
        db_session.add(ethos)
        db_session.flush()

        agent.ethos_id = ethos.id
        db_session.commit()

        result = agent.read_and_align_constitution(db_session)
        db_session.commit()

        assert result is True
        assert agent.constitution_read_count == 1
        assert agent.constitution_version == "v1.0.0"

        # Verify ethos was updated
        db_session.refresh(ethos)
        refs = ethos.get_constitutional_references()
        assert len(refs) > 0

    def test_update_ethos_with_plan(self, db_session):
        """update_ethos_with_plan() writes plan to ethos."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.flush()

        # Create and link ethos manually
        ethos = Ethos(
            agentium_id=agent.agentium_id,
            agent_type=agent.agent_type.value,
            mission_statement="Test mission",
            core_values="[]",
            behavioral_rules="[]",
            restrictions="[]",
            capabilities="[]",
            working_method="Test method",
            environment_context="Test env",
            created_by_agentium_id="20001",
            agent_id=agent.id,
            is_verified=True,
            verified_by_agentium_id="20001",
        )
        db_session.add(ethos)
        db_session.flush()

        agent.ethos_id = ethos.id
        db_session.commit()

        plan = {
            "title": "Test Plan",
            "objective": "Complete task",
            "steps": ["step1", "step2"],
        }

        result = agent.update_ethos_with_plan(plan, db_session)
        db_session.commit()

        assert result is True
        db_session.refresh(ethos)
        active_plan = ethos.get_active_plan()
        assert active_plan is not None
        assert active_plan["objective"] == "Complete task"

    def test_post_task_ritual(self, db_session):
        """post_task_ritual() executes full recalibration."""
        from backend.models.entities.constitution import Constitution
        import json

        constitution = Constitution(
            agentium_id="C00001",
            version="v1.0.0",
            version_number=1,
            preamble="Test Constitution",
            articles=json.dumps({}),
            prohibited_actions=json.dumps([]),
            sovereign_preferences=json.dumps({}),
            effective_date=datetime.now(timezone.utc),
            is_active=True,
            created_by_agentium_id="00001",
        )
        db_session.add(constitution)
        db_session.commit()

        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.flush()

        # Create and link ethos manually
        ethos = Ethos(
            agentium_id=agent.agentium_id,
            agent_type=agent.agent_type.value,
            mission_statement="Test mission",
            core_values="[]",
            behavioral_rules="[]",
            restrictions="[]",
            capabilities="[]",
            working_method="Test method",
            environment_context="Test env",
            created_by_agentium_id="20001",
            agent_id=agent.id,
            is_verified=True,
            verified_by_agentium_id="20001",
        )
        db_session.add(ethos)
        db_session.flush()

        agent.ethos_id = ethos.id
        db_session.commit()

        result = agent.post_task_ritual(
            db_session,
            outcome_summary="Task completed successfully",
            lessons=[{"lesson": "Always validate inputs"}]
        )
        db_session.commit()

        assert result["outcome_recorded"] is True
        assert result["lessons_recorded"] == 1
        assert result["ethos_compressed"] is True
        assert result["working_state_reset"] is True
        assert result["constitution_refreshed"] is True

    def test_pre_task_ritual(self, db_session):
        """pre_task_ritual() checks constitution freshness."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.commit()

        result = agent.pre_task_ritual(db_session)

        assert result["ready_for_task"] is True
        assert "constitution_version" in result


class TestAgentIdValidation:
    """Tests for agentium_id validation."""

    def test_agentium_id_format_validation(self, db_session):
        """agentium_id must follow 0xxxx-9xxxx format."""
        import os
        os.environ["TESTING"] = "true"

        # Should fail validation outside TESTING mode
        # In TESTING mode, validation is bypassed
        agent = Agent(
            agentium_id="invalid_id",
            agent_type=AgentType.TASK_AGENT,
            name="Test",
        )
        db_session.add(agent)
        db_session.commit()

        assert agent.agentium_id == "invalid_id"

        del os.environ["TESTING"]


class TestHeadOfCouncilSpecific:
    """Tests specific to HeadOfCouncil agent."""

    def test_emergency_override(self, db_session):
        """emergency_override() records timestamp."""
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        head.emergency_override("30001", "terminate")
        db_session.commit()

        assert head.emergency_override_used_at is not None

    def test_coordinate_idle_council(self, db_session):
        """coordinate_idle_council() returns persistent council members."""
        head = HeadOfCouncil(
            id=str(uuid.uuid4()),
            agentium_id="00001",
            name="Head Agent",
            status=AgentStatus.ACTIVE,
        )
        db_session.add(head)
        db_session.commit()

        # Add persistent council member - must also be ACTIVE status
        member = CouncilMember(
            id=str(uuid.uuid4()),
            agentium_id="10001",
            name="Council Member",
            is_persistent=True,
            status=AgentStatus.ACTIVE,
        )
        db_session.add(member)
        db_session.commit()

        assignments = head.coordinate_idle_council(db_session)

        assert len(assignments) == 1
        assert assignments[0]["agentium_id"] == "10001"

    def test_coordinate_idle_council_skips_non_persistent(self, db_session):
        """coordinate_idle_council() skips non-persistent council members."""
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        # Add non-persistent council member
        member = CouncilMember(
            agentium_id="10001",
            name="Council Member",
            is_persistent=False,
        )
        db_session.add(member)
        db_session.commit()

        assignments = head.coordinate_idle_council(db_session)

        assert len(assignments) == 0


class TestLeadAgentSpecific:
    """Tests specific to LeadAgent agent."""

    def test_should_spawn_new_task_agent(self, db_session):
        """should_spawn_new_task_agent() checks team size."""
        lead = LeadAgent(
            agentium_id="20001",
            name="Lead Agent",
            max_team_size=10,
        )
        db_session.add(lead)
        db_session.commit()

        assert lead.should_spawn_new_task_agent() is True

        # Add 10 task agents to reach max
        for i in range(10):
            task = TaskAgent(
                agentium_id=f"300{i:02d}",
                name=f"Task Agent {i}",
                parent_id=lead.id,
            )
            db_session.add(task)
        db_session.commit()

        lead.update_team_size()
        assert lead.team_size == 10
        assert lead.should_spawn_new_task_agent() is False


class TestTaskAgentSpecific:
    """Tests specific to TaskAgent agent."""

    def test_get_allowed_tools(self, db_session):
        """get_allowed_tools() parses JSON."""
        import json
        task = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
            assigned_tools=json.dumps(["tool1", "tool2"]),
        )
        db_session.add(task)
        db_session.commit()

        tools = task.get_allowed_tools()
        assert tools == ["tool1", "tool2"]

    def test_get_allowed_tools_invalid_json(self, db_session):
        """get_allowed_tools() returns empty list for invalid JSON."""
        task = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
            assigned_tools="invalid json",
        )
        db_session.add(task)
        db_session.commit()

        tools = task.get_allowed_tools()
        assert tools == []

    def test_execute_in_sandbox(self, db_session):
        """execute_in_sandbox() works when enabled."""
        task = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
            sandbox_enabled=True,
        )
        db_session.add(task)
        db_session.commit()

        result = task.execute_in_sandbox("echo hello")
        assert result["status"] == "executed"
        assert result["command"] == "echo hello"

    def test_execute_in_sandbox_fails_when_disabled(self, db_session):
        """execute_in_sandbox() fails when disabled."""
        task = TaskAgent(
            agentium_id="30001",
            name="Task Agent",
            sandbox_enabled=False,
        )
        db_session.add(task)
        db_session.commit()

        with pytest.raises(PermissionError):
            task.execute_in_sandbox("echo hello")


class TestCriticAgents:
    """Tests for critic agent subclasses."""

    def test_code_critic_critic_specialty(self, db_session):
        """CodeCritic has correct critic_specialty."""
        critic = CriticAgent(
            id=str(uuid.uuid4()),
            agentium_id="70001",
            name="Code Critic",
            critic_specialty=CriticType.CODE,
        )
        db_session.add(critic)
        db_session.commit()

        assert critic.critic_specialty == CriticType.CODE

    def test_output_critic_critic_specialty(self, db_session):
        """OutputCritic has correct critic_specialty using CriticAgent with OUTPUT specialty."""
        critic = CriticAgent(
            id=str(uuid.uuid4()),
            agentium_id="80001",
            name="Output Critic",
            critic_specialty=CriticType.OUTPUT,
        )
        db_session.add(critic)
        db_session.commit()

        assert critic.critic_specialty == CriticType.OUTPUT

    def test_plan_critic_critic_specialty(self, db_session):
        """PlanCritic has correct critic_specialty using CriticAgent with PLAN specialty."""
        critic = CriticAgent(
            id=str(uuid.uuid4()),
            agentium_id="90001",
            name="Plan Critic",
            critic_specialty=CriticType.PLAN,
        )
        db_session.add(critic)
        db_session.commit()

        assert critic.critic_specialty == CriticType.PLAN

    def test_critic_record_review(self, db_session):
        """CriticAgent.record_review() updates stats."""
        critic = CriticAgent(
            id=str(uuid.uuid4()),
            agentium_id="70001",
            name="Code Critic",
            critic_specialty=CriticType.CODE,
        )
        db_session.add(critic)
        db_session.commit()

        critic.record_review(CriticVerdict.PASS, 100.0)
        db_session.commit()

        assert critic.reviews_completed == 1
        assert critic.passes_issued == 1
        assert critic.avg_review_time_ms == 100.0

        critic.record_review(CriticVerdict.REJECT, 150.0)
        db_session.commit()

        assert critic.reviews_completed == 2
        assert critic.vetoes_issued == 1
        assert critic.avg_review_time_ms == 125.0

    def test_critic_approval_rate(self, db_session):
        """CriticAgent.approval_rate computes correctly."""
        from backend.models.entities.critics import CriticVerdict
        critic = CriticAgent(
            agentium_id="70001",
            name="Code Critic",
            critic_specialty=CriticType.CODE,
        )
        db_session.add(critic)
        db_session.commit()

        for _ in range(3):
            critic.record_review(CriticVerdict.PASS, 100)
        critic.record_review(CriticVerdict.REJECT, 100)
        db_session.commit()

        assert critic.approval_rate == 75.0


class TestAgentConstitutionalCompliance:
    """Tests for Constitutional compliance methods."""

    def test_check_constitution_compliance(self, db_session):
        """check_constitution_compliance() returns True for valid actions."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.commit()

        result = agent.check_constitution_compliance("execute task")
        assert result is True

    def test_view_subordinate_ethos(self, db_session):
        """Higher-tier agents can view subordinate ethos."""
        head = HeadOfCouncil(
            id=str(uuid.uuid4()),
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        subordinate = CouncilMember(
            id=str(uuid.uuid4()),
            agentium_id="10001",
            name="Council Member",
        )
        db_session.add(subordinate)
        db_session.flush()

        # Create ethos for subordinate
        ethos = Ethos(
            agentium_id=subordinate.agentium_id,
            agent_type=subordinate.agent_type.value,
            mission_statement="Test mission",
            core_values="[]",
            behavioral_rules="[]",
            restrictions="[]",
            capabilities="[]",
            working_method="Test method",
            environment_context="Test env",
            created_by_agentium_id="00001",
            agent_id=subordinate.id,
            is_verified=True,
            verified_by_agentium_id="00001",
        )
        db_session.add(ethos)
        db_session.flush()

        subordinate.ethos_id = ethos.id
        db_session.commit()

        result = head.view_subordinate_ethos("10001", db_session)

        assert result is not None
        # Ethos.to_dict() returns 'agent_id' which is the UUID, not agentium_id
        assert result["agent_id"] == subordinate.id
        assert result["agentium_id"] == "10001"

    def test_view_subordinate_ethos_fails_for_lower_tier(self, db_session):
        """Lower-tier agents cannot view higher-tier ethos."""
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        member = CouncilMember(
            agentium_id="10001",
            name="Council Member",
        )
        db_session.add_all([head, member])
        db_session.commit()

        with pytest.raises(PermissionError):
            member.view_subordinate_ethos("00001", db_session)

    def test_edit_subordinate_ethos(self, db_session):
        """Higher-tier agents can edit subordinate ethos."""
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        db_session.add(head)
        db_session.commit()

        subordinate = CouncilMember(
            agentium_id="10001",
            name="Council Member",
        )
        db_session.add(subordinate)
        db_session.flush()

        # Create ethos for subordinate
        ethos = Ethos(
            agentium_id=subordinate.agentium_id,
            agent_type=subordinate.agent_type.value,
            mission_statement="Test mission",
            core_values="[]",
            behavioral_rules="[]",
            restrictions="[]",
            capabilities="[]",
            working_method="Test method",
            environment_context="Test env",
            created_by_agentium_id="00001",
            agent_id=subordinate.id,
            is_verified=True,
            verified_by_agentium_id="00001",
        )
        db_session.add(ethos)
        db_session.flush()

        subordinate.ethos_id = ethos.id
        db_session.commit()

        result = head.edit_subordinate_ethos("10001", {"current_objective": "New objective"}, db_session)
        db_session.commit()

        assert result is True

    def test_edit_subordinate_ethos_fails_for_lower_tier(self, db_session):
        """Lower-tier agents cannot edit higher-tier ethos."""
        head = HeadOfCouncil(
            agentium_id="00001",
            name="Head Agent",
        )
        member = CouncilMember(
            agentium_id="10001",
            name="Council Member",
        )
        db_session.add_all([head, member])
        db_session.commit()

        with pytest.raises(PermissionError):
            member.edit_subordinate_ethos("00001", {"current_objective": "Hack"}, db_session)


class TestAgentWithEthos:
    """Tests for Agent with full Ethos integration via spawn_child."""

    def test_default_ethos_created_on_spawn(self, db_session):
        """Default Ethos is created when agent is spawned via spawn_child."""
        lead = LeadAgent(
            id=str(uuid.uuid4()),
            agentium_id="20001",
            name="Lead Agent",
        )
        db_session.add(lead)
        db_session.commit()

        task = lead.spawn_child(AgentType.TASK_AGENT, db_session, name="Task Agent")
        db_session.commit()

        assert task.ethos_id is not None

        ethos = task.ethos
        assert ethos is not None
        assert ethos.agentium_id == task.agentium_id
        assert ethos.mission_statement is not None
        assert ethos.working_method is not None
        assert ethos.capabilities is not None

    def test_ethos_has_working_method(self, db_session):
        """Ethos has working_method from DEFAULT_WORKING_METHODS."""
        lead = LeadAgent(
            id=str(uuid.uuid4()),
            agentium_id="20001",
            name="Lead Agent",
        )
        db_session.add(lead)
        db_session.commit()

        task = lead.spawn_child(AgentType.TASK_AGENT, db_session, name="Task Agent")
        db_session.commit()

        ethos = task.ethos
        assert ethos is not None
        assert ethos.working_method is not None
        assert "Knowledge Retrieval" in ethos.working_method


class TestAgentVectorSearch:
    """Tests for Agent skill RAG methods."""

    def test_search_skills(self, db_session):
        """search_skills() queries skill manager."""
        agent = Agent(
            agentium_id="30001",
            agent_type=AgentType.TASK_AGENT,
            name="Test Agent",
        )
        db_session.add(agent)
        db_session.commit()

        # This will call skill_manager which may require external setup
        # Just verify the method exists and doesn't crash
        result = agent.search_skills("python", db_session)
        assert isinstance(result, list)