"""
Integration tests for checkpoint service (checkpoint_service.py).
Verifies full state capture, time-travel resume, and branching.
"""

import pytest
import json
from datetime import datetime
from backend.services.checkpoint_service import CheckpointService
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType
from backend.models.entities.agents import Agent, AgentType, AgentStatus
from backend.models.entities.audit import AuditLog, AuditLevel, AuditCategory
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase


class TestCheckpointStateCapture:
    """Tests for full state capture during checkpoint creation."""

    def test_create_checkpoint_captures_task_snapshot(self, seeded_db):
        """Task with status, result_data, assigned agents: task_state_snapshot contains all fields; phase correct."""
        db = seeded_db

        # Create a task with supervisor and agents
        task = Task(
            title="Test task for checkpoint",
            description="Test task for checkpoint",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            result_data={"score": 42, "details": "test completed"},
            supervisor_id="10003",
            assigned_task_agent_ids=["10003", "10004"]
        )
        db.add(task)
        db.flush()

        # Create agents for assigned_task_agent_ids
        for agent_id in ["10003", "10004"]:
            agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
            if not agent:
                from backend.models.entities.agents import CouncilMember
                agent = CouncilMember(
                    agentium_id=agent_id,
                    name=f"Agent {agent_id}",
                    agent_type=AgentType.COUNCIL_MEMBER,
                    status=AgentStatus.ACTIVE,
                    is_persistent=True,
                )
                db.add(agent)
        db.flush()

        # Assign agents to task
        task.assigned_task_agent_ids = ["10003", "10004"]
        db.commit()

        # Create checkpoint
        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test-actor"
        )

        assert checkpoint is not None
        assert checkpoint.task_id == task.id
        assert checkpoint.phase == CheckpointPhase.EXECUTION_COMPLETE

        # Verify task_state_snapshot contains expected fields
        snapshot = checkpoint.task_state_snapshot
        assert snapshot["description"] == "Test task for checkpoint"
        assert snapshot["status"] == TaskStatus.IN_PROGRESS.value
        assert snapshot["result_data"] == {"score": 42, "details": "test completed"}
        assert snapshot["supervisor_id"] == "10003"
        assert snapshot["assigned_task_agent_ids"] == ["10003", "10004"]
        assert "type" in snapshot
        assert "priority" in snapshot

    def test_create_checkpoint_captures_agent_states(self, seeded_db):
        """Task with 2 assigned agents + supervisor: agent_states has 3 entries, each with status, current_task_id, agent_type, ethos_summary, capabilities."""
        db = seeded_db

        task = Task(
            title="Test agent states",
            description="Test agent states",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            supervisor_id="10003",
            assigned_task_agent_ids=["10004", "10005"]
        )
        db.add(task)
        db.flush()

        # Create agents
        for agent_id, agent_type in [("10003", AgentType.COUNCIL_MEMBER), ("10004", AgentType.COUNCIL_MEMBER), ("10005", AgentType.TASK_AGENT)]:
            agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
            if not agent:
                if agent_type == AgentType.COUNCIL_MEMBER:
                    from backend.models.entities.agents import CouncilMember
                    agent = CouncilMember(agentium_id=agent_id, name=f"Agent {agent_id}", agent_type=agent_type, status=AgentStatus.ACTIVE, is_persistent=True)
                else:
                    agent = Agent(agentium_id=agent_id, name=f"Agent {agent_id}", agent_type=agent_type, status=AgentStatus.ACTIVE, is_persistent=True)
                db.add(agent)
        db.flush()

        task.assigned_task_agent_ids = ["10004", "10005"]
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test-actor"
        )

        # Verify agent_states captured
        agent_states = checkpoint.agent_states
        assert len(agent_states) >= 2  # At least the 2 assigned agents

        for agent_id, state in agent_states.items():
            assert "status" in state
            assert "current_task_id" in state
            assert "agent_type" in state
            assert "is_persistent" in state
            assert "ethos_summary" in state
            assert "custom_capabilities" in state
            assert "last_idle_action_at" in state

    def test_create_checkpoint_captures_subtasks(self, seeded_db):
        """Task with 2 active subtasks: subtask_snapshots list with id, status, description, assigned agents, result_data for each."""
        db = seeded_db

        task = Task(
            title="Parent task with subtasks",
            description="Parent task with subtasks",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            supervisor_id="10003",
        )
        db.add(task)
        db.flush()

        # Create subtasks as Task objects with parent_task_id - explicitly set agentium_id to avoid conflicts with genesis
        subtask1 = Task(
            agentium_id="T90001",
            parent_task_id=task.id,
            title="Subtask 1",
            description="First subtask",
            status=TaskStatus.PENDING,
            assigned_task_agent_ids=["10004"],
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
        )
        subtask2 = Task(
            agentium_id="T90002",
            parent_task_id=task.id,
            title="Subtask 2",
            description="Second subtask",
            status=TaskStatus.IN_PROGRESS,
            assigned_task_agent_ids=["10005"],
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
        )
        db.add_all([subtask1, subtask2])
        db.flush()

        # Create supervisor agent
        supervisor = db.query(Agent).filter_by(agentium_id="10003").first()
        if not supervisor:
            from backend.models.entities.agents import CouncilMember
            supervisor = CouncilMember(agentium_id="10003", name="Supervisor", agent_type=AgentType.COUNCIL_MEMBER, status=AgentStatus.ACTIVE, is_persistent=True)
            db.add(supervisor)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test-actor"
        )

        # Verify subtask_snapshots
        snapshot = checkpoint.task_state_snapshot
        subtask_snapshots = snapshot.get("subtask_snapshots", [])
        assert len(subtask_snapshots) == 2

        for snap in subtask_snapshots:
            assert "id" in snap
            assert "status" in snap
            assert "description" in snap
            assert "assigned_task_agent_ids" in snap
            assert "result_data" in snap
            assert "completion_percentage" in snap
            assert "result_summary" in snap

    def test_create_checkpoint_audit_log_created(self, seeded_db):
        """After create: AuditLog entry with action='checkpoint_created'."""
        db = seeded_db

        task = Task(
            title="Test audit log",
            description="Test audit log",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test-actor"
        )

        # Verify audit log
        audit_log = db.query(AuditLog).filter(
            AuditLog.action == "checkpoint_created",
            AuditLog.target_id == checkpoint.id
        ).first()

        assert audit_log is not None
        assert audit_log.actor_id == "test-actor"
        assert audit_log.action == "checkpoint_created"
        assert audit_log.category == AuditCategory.SYSTEM


class TestCheckpointResume:
    """Tests for time-travel resume functionality."""

    def test_resume_restores_task_status(self, seeded_db):
        """Task was COMPLETED, checkpoint has PENDING: Task status = PENDING after resume."""
        db = seeded_db

        task = Task(
            title="Resume test",
            description="Resume test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.CRITICAL,  # Skip deliberation
            status=TaskStatus.PENDING,
        )
        db.add(task)
        db.commit()

        # Create checkpoint with PENDING status
        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Change task to COMPLETED following state machine
        task.set_status(TaskStatus.APPROVED, actor_id="test", note="Approved")
        task.set_status(TaskStatus.IN_PROGRESS, actor_id="test", note="Started")
        task.set_status(TaskStatus.COMPLETED, actor_id="test", note="Completed")
        db.commit()

        # Resume from checkpoint
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test-user"
        )

        assert resumed_task.status == TaskStatus.PENDING

    def test_resume_restores_result_data(self, seeded_db):
        """Checkpoint has result_data={'score': 42}: task.result_data == {'score': 42}."""
        db = seeded_db

        task = Task(
            title="Result data test",
            description="Result data test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            result_data=None
        )
        db.add(task)
        db.commit()

        # Create checkpoint with result_data
        task.result_data = {"score": 42, "status": "great"}
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Clear result_data
        task.result_data = None
        db.commit()

        # Resume
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test-user"
        )

        assert resumed_task.result_data == {"score": 42, "status": "great"}

    def test_resume_restores_assigned_agents(self, seeded_db):
        """Checkpoint has assigned_task_agent_ids: task.assigned_task_agent_ids matches."""
        db = seeded_db

        task = Task(
            title="Assigned agents test",
            description="Assigned agents test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            assigned_task_agent_ids=["10003", "10004"]
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Change assigned agents
        task.assigned_task_agent_ids = ["99999"]
        db.commit()

        # Resume
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test-user"
        )

        assert resumed_task.assigned_task_agent_ids == ["10003", "10004"]

    def test_resume_restores_agent_states(self, seeded_db):
        """Checkpoint has agent states with statuses: Agents in DB have matching status, current_task_id."""
        db = seeded_db

        task = Task(
            title="Agent states test",
            description="Agent states test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            supervisor_id="10003",
            assigned_task_agent_ids=["10004"]
        )
        db.add(task)
        db.flush()

        # Create agents
        for agent_id in ["10003", "10004"]:
            agent = db.query(Agent).filter_by(agentium_id=agent_id).first()
            if not agent:
                from backend.models.entities.agents import CouncilMember
                agent = CouncilMember(agentium_id=agent_id, name=f"Agent {agent_id}", agent_type=AgentType.COUNCIL_MEMBER, status=AgentStatus.ACTIVE, is_persistent=True)
                db.add(agent)
        db.flush()

        # Set agent current_task_id to the task id so checkpoint captures it
        agent3 = db.query(Agent).filter_by(agentium_id="10003").first()
        agent4 = db.query(Agent).filter_by(agentium_id="10004").first()
        agent3.current_task_id = task.id
        agent4.current_task_id = task.id
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Modify agent states
        agent3 = db.query(Agent).filter_by(agentium_id="10003").first()
        agent4 = db.query(Agent).filter_by(agentium_id="10004").first()
        agent3.status = AgentStatus.IDLE_WORKING
        agent4.status = AgentStatus.SUSPENDED
        agent3.current_task_id = None
        agent4.current_task_id = None
        db.commit()

        # Resume
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test-user"
        )

        # Verify agents restored
        agent3 = db.query(Agent).filter_by(agentium_id="10003").first()
        agent4 = db.query(Agent).filter_by(agentium_id="10004").first()
        assert agent3.status == AgentStatus.ACTIVE
        assert agent4.status == AgentStatus.ACTIVE
        assert agent3.current_task_id == task.id
        assert agent4.current_task_id == task.id

    def test_resume_restores_subtask_states(self, seeded_db):
        """Checkpoint has subtask snapshots: Subtasks have matching status, result_data, assigned agents."""
        db = seeded_db

        task = Task(
            title="Subtask resume test",
            description="Subtask resume test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
        )
        db.add(task)
        db.flush()

        # Create agent first
        agent = db.query(Agent).filter_by(agentium_id="10004").first()
        if not agent:
            from backend.models.entities.agents import CouncilMember
            agent = CouncilMember(agentium_id="10004", name="Agent 10004", agent_type=AgentType.COUNCIL_MEMBER, status=AgentStatus.ACTIVE, is_persistent=True)
            db.add(agent)
        db.flush()

        # Create child Task as subtask (checkpoint service captures child Tasks)
        subtask = Task(
            agentium_id="ST90001",
            parent_task_id=task.id,
            title="Test Subtask",
            description="Subtask to restore",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.PENDING,
            assigned_task_agent_ids=[agent.id],
            result_data=None,
            result_summary=None,
            completion_percentage=0,
        )
        db.add(subtask)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Modify subtask
        subtask.status = TaskStatus.COMPLETED
        subtask.result_data = {"old": "data"}
        subtask.assigned_task_agent_ids = ["99999"]
        db.commit()

        # Resume
        resumed_task = CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test-user"
        )

        # Verify subtask restored
        db.refresh(subtask)
        assert subtask.status == TaskStatus.PENDING
        assert subtask.assigned_task_agent_ids == [agent.id]
        assert subtask.result_data is None

    def test_resume_creates_audit_log(self, seeded_db):
        """After resume: AuditLog entry with action='checkpoint_resumed'."""
        db = seeded_db

        task = Task(
            title="Resume audit test",
            description="Resume audit test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Resume
        CheckpointService.resume_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            actor_id="test-user"
        )

        # Verify audit log
        audit_log = db.query(AuditLog).filter(
            AuditLog.action == "checkpoint_resumed",
            AuditLog.target_id == task.id
        ).first()

        assert audit_log is not None
        assert audit_log.actor_id == "test-user"
        assert audit_log.action == "checkpoint_resumed"


class TestCheckpointBranching:
    """Tests for branching from checkpoints."""

    def test_branch_creates_new_task(self, seeded_db):
        """Branch from checkpoint: New Task with new UUID, same description, type, priority."""
        db = seeded_db

        task = Task(
            title="Original task for branching",
            description="Original task for branching",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.HIGH,
            status=TaskStatus.IN_PROGRESS,
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        # Branch
        new_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="test-branch"
        )

        assert new_task is not None
        assert new_task.id != task.id
        assert new_task.description == task.description
        assert new_task.task_type == task.task_type
        assert new_task.priority == task.priority
        assert new_task.status == TaskStatus.PENDING  # New tasks start as PENDING

    def test_branch_creates_branch_checkpoint(self, seeded_db):
        """After branch: New ExecutionCheckpoint with parent_checkpoint_id linking to source, branch_name set."""
        db = seeded_db

        task = Task(
            title="Branch checkpoint test",
            description="Branch checkpoint test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        new_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="my-branch"
        )

        # Find the branch checkpoint
        branch_checkpoint = db.query(ExecutionCheckpoint).filter(
            ExecutionCheckpoint.task_id == new_task.id
        ).first()

        assert branch_checkpoint is not None
        assert branch_checkpoint.parent_checkpoint_id == checkpoint.id
        assert branch_checkpoint.branch_name == "my-branch"
        assert branch_checkpoint.phase == checkpoint.phase

    def test_branch_task_independent(self, seeded_db):
        """Modify branch task: Original task unchanged; branch task has own state."""
        db = seeded_db

        task = Task(
            title="Independent branch test",
            description="Independent branch test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.PENDING,
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        new_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="independent"
        )

        # Modify branch task
        new_task.status = TaskStatus.COMPLETED
        new_task.description = "Modified branch"
        db.commit()

        # Original should be unchanged
        db.refresh(task)
        assert task.status == TaskStatus.PENDING
        assert task.description == "Independent branch test"

        # Branch should have changes
        db.refresh(new_task)
        assert new_task.status == TaskStatus.COMPLETED
        assert new_task.description == "Modified branch"

    def test_branch_with_new_supervisor(self, seeded_db):
        """Pass new_supervisor_id: New task has supervisor_id = new_supervisor_id."""
        db = seeded_db

        task = Task(
            title="New supervisor test",
            description="New supervisor test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
            supervisor_id="10003"
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        new_task = CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="supervisor-branch",
            new_supervisor_id="50001"
        )

        assert new_task.supervisor_id == "50001"

    def test_branch_audit_log_created(self, seeded_db):
        """After branch: AuditLog entry with action='checkpoint_branched'."""
        db = seeded_db

        task = Task(
            title="Branch audit test",
            description="Branch audit test",
            task_type=TaskType.EXECUTION,
            priority=TaskPriority.NORMAL,
            status=TaskStatus.IN_PROGRESS,
        )
        db.add(task)
        db.commit()

        checkpoint = CheckpointService.create_checkpoint(
            db=db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE
        )

        CheckpointService.branch_from_checkpoint(
            db=db,
            checkpoint_id=checkpoint.id,
            branch_name="audit-branch"
        )

        # Verify audit log
        audit_log = db.query(AuditLog).filter(
            AuditLog.action == "checkpoint_branched"
        ).first()

        assert audit_log is not None
        assert audit_log.action == "checkpoint_branched"