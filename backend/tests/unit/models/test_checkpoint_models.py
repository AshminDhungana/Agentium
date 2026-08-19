"""
Unit tests for Checkpoint models.
Tests ExecutionCheckpoint and CheckpointPhase models.
"""
import pytest
import json
from datetime import datetime, timezone
from uuid import uuid4

try:
    from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase
except ImportError:
    from models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase


class TestCheckpointPhase:
    """Tests for CheckpointPhase enum."""

    @pytest.mark.parametrize("phase", [
        CheckpointPhase.PLAN_APPROVED, CheckpointPhase.EXECUTION_COMPLETE,
        CheckpointPhase.CRITIQUE_PASSED, CheckpointPhase.MANUAL,
        CheckpointPhase.WAIT_ENTERED,
    ])
    def test_checkpoint_phase_values(self, phase):
        """All CheckpointPhase values are valid."""
        assert phase in (
            CheckpointPhase.PLAN_APPROVED, CheckpointPhase.EXECUTION_COMPLETE,
            CheckpointPhase.CRITIQUE_PASSED, CheckpointPhase.MANUAL,
            CheckpointPhase.WAIT_ENTERED,
        )
        assert isinstance(phase.value, str)

    def test_checkpoint_phase_string_values(self):
        """CheckpointPhase string values match expected."""
        assert CheckpointPhase.PLAN_APPROVED.value == "plan_approved"
        assert CheckpointPhase.EXECUTION_COMPLETE.value == "execution_complete"
        assert CheckpointPhase.CRITIQUE_PASSED.value == "critique_passed"
        assert CheckpointPhase.MANUAL.value == "manual"
        assert CheckpointPhase.WAIT_ENTERED.value == "wait_entered"


class TestExecutionCheckpoint:
    """Tests for ExecutionCheckpoint model."""

    def test_execution_checkpoint_creation(self, db_session):
        """ExecutionCheckpoint creates with all required fields."""
        checkpoint = ExecutionCheckpoint(
            agentium_id="CP00000001",  # Required for test
            session_id="session_abc",
            task_id="task-uuid-123",
            phase=CheckpointPhase.PLAN_APPROVED,
            agent_states={"agent_1": {"status": "active", "progress": 50}},
            artifacts=["artifact_1", "artifact_2"],
            task_state_snapshot={"status": "planned", "steps": 5},
            parent_checkpoint_id=None,
            branch_name="main",
        )
        db_session.add(checkpoint)
        db_session.commit()
        db_session.refresh(checkpoint)

        assert checkpoint.session_id == "session_abc"
        assert checkpoint.task_id == "task-uuid-123"
        assert checkpoint.phase == CheckpointPhase.PLAN_APPROVED
        assert checkpoint.agent_states == {"agent_1": {"status": "active", "progress": 50}}
        assert checkpoint.artifacts == ["artifact_1", "artifact_2"]
        assert checkpoint.task_state_snapshot == {"status": "planned", "steps": 5}
        assert checkpoint.parent_checkpoint_id is None
        assert checkpoint.branch_name == "main"
        assert checkpoint.agentium_id == "CP00000001"

    def test_execution_checkpoint_defaults(self, db_session):
        """ExecutionCheckpoint defaults are correct."""
        checkpoint = ExecutionCheckpoint(
            agentium_id="CP00000002",
            session_id="session_def",
            task_id="task-uuid-456",
            phase=CheckpointPhase.MANUAL,
        )
        db_session.add(checkpoint)
        db_session.commit()

        assert checkpoint.agent_states == {}
        assert checkpoint.artifacts == []
        assert checkpoint.task_state_snapshot == {}
        assert checkpoint.parent_checkpoint_id is None
        assert checkpoint.branch_name is None

    def test_execution_checkpoint_to_dict(self, db_session):
        """to_dict() includes all relevant fields."""
        checkpoint = ExecutionCheckpoint(
            agentium_id="CP00000003",
            session_id="session_dict",
            task_id="task-uuid-789",
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            agent_states={"agent_1": {"output": "done"}},
            artifacts=["result.json", "log.txt"],
            task_state_snapshot={"completed": True, "duration": 120},
            parent_checkpoint_id="parent-cp-id",
            branch_name="feature-branch",
        )
        db_session.add(checkpoint)
        db_session.commit()

        data = checkpoint.to_dict()
        assert data["session_id"] == "session_dict"
        assert data["task_id"] == "task-uuid-789"
        assert data["phase"] == "execution_complete"
        assert data["agent_states"] == {"agent_1": {"output": "done"}}
        assert data["artifacts"] == ["result.json", "log.txt"]
        assert data["task_state_snapshot"] == {"completed": True, "duration": 120}
        assert data["parent_checkpoint_id"] == "parent-cp-id"
        assert data["branch_name"] == "feature-branch"
        assert "created_at" in data
        assert "updated_at" in data

    @pytest.mark.parametrize("phase", [
        CheckpointPhase.PLAN_APPROVED, CheckpointPhase.EXECUTION_COMPLETE,
        CheckpointPhase.CRITIQUE_PASSED, CheckpointPhase.MANUAL,
        CheckpointPhase.WAIT_ENTERED,
    ])
    def test_execution_checkpoint_all_phases(self, db_session, phase):
        """ExecutionCheckpoint accepts all valid phase values."""
        checkpoint = ExecutionCheckpoint(
            agentium_id=f"CP{phase.value[:10].upper()}",
            session_id="phase_test",
            task_id="task-phase-test",
            phase=phase,
        )
        db_session.add(checkpoint)
        db_session.commit()
        assert checkpoint.phase == phase
        db_session.delete(checkpoint)
        db_session.commit()

    def test_execution_checkpoint_hierarchical_branching(self, db_session):
        """Hierarchical branching: parent -> child checkpoints."""
        # Create parent checkpoint
        parent = ExecutionCheckpoint(
            agentium_id="CP00000004",
            session_id="branch_session",
            task_id="task-branch-1",
            phase=CheckpointPhase.PLAN_APPROVED,
            agent_states={"lead": {"plan": "draft"}},
            branch_name="main",
        )
        db_session.add(parent)
        db_session.commit()
        db_session.refresh(parent)

        # Create child checkpoint branching from parent
        child = ExecutionCheckpoint(
            agentium_id="CP00000005",
            session_id="branch_session",
            task_id="task-branch-1",
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            agent_states={"lead": {"plan": "final"}, "worker": {"result": "done"}},
            artifacts=["output.json"],
            parent_checkpoint_id=parent.id,
            branch_name="experiment",
        )
        db_session.add(child)
        db_session.commit()
        db_session.refresh(child)

        assert child.parent_checkpoint_id == parent.id
        assert child.branch_name == "experiment"
        assert parent.branch_name == "main"

        # Test relationship
        assert child.parent_checkpoint.id == parent.id
        assert len(parent.child_branches) == 1
        assert parent.child_branches[0].id == child.id

    def test_execution_checkpoint_multiple_branches(self, db_session):
        """Multiple child branches from single parent."""
        parent = ExecutionCheckpoint(
            agentium_id="CP00000006",
            session_id="multi_branch",
            task_id="task-multi",
            phase=CheckpointPhase.CRITIQUE_PASSED,
            branch_name="main",
        )
        db_session.add(parent)
        db_session.commit()

        branch1 = ExecutionCheckpoint(
            agentium_id="CP00000007",
            session_id="multi_branch",
            task_id="task-multi",
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            parent_checkpoint_id=parent.id,
            branch_name="branch_a",
        )
        branch2 = ExecutionCheckpoint(
            agentium_id="CP00000008",
            session_id="multi_branch",
            task_id="task-multi",
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            parent_checkpoint_id=parent.id,
            branch_name="branch_b",
        )
        db_session.add_all([branch1, branch2])
        db_session.commit()

        assert len(parent.child_branches) == 2
        branch_names = {b.branch_name for b in parent.child_branches}
        assert branch_names == {"branch_a", "branch_b"}

    def test_execution_checkpoint_complex_agent_states(self, db_session):
        """Complex agent states with nested data."""
        checkpoint = ExecutionCheckpoint(
            agentium_id="CP00000009",
            session_id="complex_session",
            task_id="task-complex",
            phase=CheckpointPhase.WAIT_ENTERED,
            agent_states={
                "head_of_council": {
                    "status": "active",
                    "current_task": "coordination",
                    "subordinates": ["council_1", "lead_1"]
                },
                "council_member": {
                    "status": "deliberating",
                    "votes_cast": 3,
                    "ethos_version": 5
                },
                "task_agent": {
                    "status": "waiting",
                    "waiting_for": "human_input",
                    "progress": 60
                }
            },
            artifacts=[
                "deliberation_log.txt",
                "intermediate_result.json",
                "checkpoint_state.yaml"
            ],
            task_state_snapshot={
                "phase": "deliberation",
                "participants": 5,
                "quorum_met": True
            },
        )
        db_session.add(checkpoint)
        db_session.commit()
        db_session.refresh(checkpoint)

        assert checkpoint.agent_states["head_of_council"]["subordinates"] == ["council_1", "lead_1"]
        assert checkpoint.agent_states["council_member"]["votes_cast"] == 3
        assert checkpoint.agent_states["task_agent"]["waiting_for"] == "human_input"
        assert len(checkpoint.artifacts) == 3
        assert checkpoint.task_state_snapshot["phase"] == "deliberation"


class TestCheckpointIntegration:
    """Integration tests for checkpoint workflows."""

    def test_checkpoint_time_travel_scenario(self, db_session):
        """Full time-travel scenario: create, branch, restore."""
        # Checkpoint 1: Plan approved
        cp1 = ExecutionCheckpoint(
            agentium_id="CP10001",
            session_id="time_travel_session",
            task_id="task-time-travel",
            phase=CheckpointPhase.PLAN_APPROVED,
            agent_states={"planner": {"plan": "initial"}},
            branch_name="main",
        )
        db_session.add(cp1)
        db_session.commit()

        # Checkpoint 2: Execution complete
        cp2 = ExecutionCheckpoint(
            agentium_id="CP10002",
            session_id="time_travel_session",
            task_id="task-time-travel",
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            agent_states={"planner": {"plan": "executed"}, "worker": {"done": True}},
            artifacts=["result_v1.json"],
            parent_checkpoint_id=cp1.id,
            branch_name="main",
        )
        db_session.add(cp2)
        db_session.commit()

        # Checkpoint 3: Critique passed (on main branch)
        cp3 = ExecutionCheckpoint(
            agentium_id="CP10003",
            session_id="time_travel_session",
            task_id="task-time-travel",
            phase=CheckpointPhase.CRITIQUE_PASSED,
            agent_states={"critic": {"approved": True}},
            parent_checkpoint_id=cp2.id,
            branch_name="main",
        )
        db_session.add(cp3)
        db_session.commit()

        # Branch: Manual checkpoint from cp2 to experiment
        cp_branch = ExecutionCheckpoint(
            agentium_id="CP10004",
            session_id="time_travel_session",
            task_id="task-time-travel",
            phase=CheckpointPhase.MANUAL,
            agent_states={"explorer": {"trying": "new_approach"}},
            artifacts=["experimental_result.json"],
            parent_checkpoint_id=cp2.id,
            branch_name="experiment",
        )
        db_session.add(cp_branch)
        db_session.commit()

        # Verify timeline
        assert cp1.phase == CheckpointPhase.PLAN_APPROVED
        assert cp2.parent_checkpoint_id == cp1.id
        assert cp3.parent_checkpoint_id == cp2.id
        assert cp_branch.parent_checkpoint_id == cp2.id
        assert cp_branch.branch_name == "experiment"

        # Simulate restoring to cp2 (time travel)
        restored_states = cp2.agent_states
        assert restored_states["planner"]["plan"] == "executed"
        assert restored_states["worker"]["done"] is True

        # Simulate branching from cp2
        assert cp_branch.agent_states["explorer"]["trying"] == "new_approach"

    def test_checkpoint_session_isolation(self, db_session):
        """Checkpoints from different sessions are independent."""
        cp_session_a = ExecutionCheckpoint(
            agentium_id="CP20001",
            session_id="session_a",
            task_id="task-a",
            phase=CheckpointPhase.PLAN_APPROVED,
        )
        cp_session_b = ExecutionCheckpoint(
            agentium_id="CP20002",
            session_id="session_b",
            task_id="task-b",
            phase=CheckpointPhase.EXECUTION_COMPLETE,
        )
        db_session.add_all([cp_session_a, cp_session_b])
        db_session.commit()

        assert cp_session_a.session_id == "session_a"
        assert cp_session_b.session_id == "session_b"
        assert cp_session_a.session_id != cp_session_b.session_id

    def test_checkpoint_task_linking(self, db_session):
        """Checkpoints link correctly to tasks."""
        task_id = "task-link-test"

        cp1 = ExecutionCheckpoint(
            agentium_id="CP30001",
            session_id="link_session",
            task_id=task_id,
            phase=CheckpointPhase.PLAN_APPROVED,
        )
        cp2 = ExecutionCheckpoint(
            agentium_id="CP30002",
            session_id="link_session",
            task_id=task_id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            parent_checkpoint_id=cp1.id,
        )
        cp3 = ExecutionCheckpoint(
            agentium_id="CP30003",
            session_id="link_session",
            task_id=task_id,
            phase=CheckpointPhase.CRITIQUE_PASSED,
            parent_checkpoint_id=cp2.id,
        )
        db_session.add_all([cp1, cp2, cp3])
        db_session.commit()

        # All checkpoints have same task_id
        assert cp1.task_id == task_id
        assert cp2.task_id == task_id
        assert cp3.task_id == task_id

        # Chain is maintained
        assert cp2.parent_checkpoint_id == cp1.id
        assert cp3.parent_checkpoint_id == cp2.id