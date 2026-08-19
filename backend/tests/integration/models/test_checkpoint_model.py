"""
Integration tests for ExecutionCheckpoint model (3.3.6).
Verifies save/restore functionality, phases, snapshot data integrity, and branching hierarchy.
"""
import pytest
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase


def test_checkpoint_save_and_restore(db_session, sample_task):
    """Verify ExecutionCheckpoint saves snapshots and restores exact JSON dictionary structures."""
    agent_states = {
        "30001": {"status": "working", "tasks_completed": 10},
        "20001": {"status": "active", "subordinates": ["30001"]},
    }
    artifacts = ["http://storage/output1.json", "http://storage/report.pdf"]
    task_snapshot = {
        "id": sample_task.id,
        "title": sample_task.title,
        "status": "in_progress",
        "completion_percentage": 75,
    }

    checkpoint = ExecutionCheckpoint(
        agentium_id="CK10001",
        session_id="session-xyz-123",
        task_id=sample_task.id,
        phase=CheckpointPhase.EXECUTION_COMPLETE,
        agent_states=agent_states,
        artifacts=artifacts,
        task_state_snapshot=task_snapshot,
        branch_name="main",
    )
    db_session.add(checkpoint)
    db_session.commit()

    fetched = db_session.query(ExecutionCheckpoint).filter_by(agentium_id="CK10001").first()
    assert fetched is not None
    assert fetched.session_id == "session-xyz-123"
    assert fetched.task_id == sample_task.id
    assert fetched.phase == CheckpointPhase.EXECUTION_COMPLETE
    assert fetched.agent_states["30001"]["tasks_completed"] == 10
    assert fetched.artifacts == artifacts
    assert fetched.task_state_snapshot["completion_percentage"] == 75

    d = fetched.to_dict()
    assert d["phase"] == "execution_complete"
    assert d["branch_name"] == "main"


def test_checkpoint_branching(db_session, sample_task):
    """Verify parent_checkpoint_id FK builds a branching tree history."""
    parent_ck = ExecutionCheckpoint(
        agentium_id="CK20001",
        session_id="session-xyz-123",
        task_id=sample_task.id,
        phase=CheckpointPhase.PLAN_APPROVED,
        agent_states={"30001": "plan_v1"},
        artifacts=[],
        task_state_snapshot={"plan_version": 1},
        branch_name="main",
    )
    db_session.add(parent_ck)
    db_session.commit()

    branch_ck1 = ExecutionCheckpoint(
        agentium_id="CK20002",
        session_id="session-xyz-123",
        task_id=sample_task.id,
        phase=CheckpointPhase.MANUAL,
        parent_checkpoint_id=parent_ck.id,
        agent_states={"30001": "branch_A"},
        artifacts=["A.out"],
        task_state_snapshot={"plan_version": 2},
        branch_name="feature-branch-A",
    )
    branch_ck2 = ExecutionCheckpoint(
        agentium_id="CK20003",
        session_id="session-xyz-123",
        task_id=sample_task.id,
        phase=CheckpointPhase.MANUAL,
        parent_checkpoint_id=parent_ck.id,
        agent_states={"30001": "branch_B"},
        artifacts=["B.out"],
        task_state_snapshot={"plan_version": 2},
        branch_name="feature-branch-B",
    )
    db_session.add_all([branch_ck1, branch_ck2])
    db_session.commit()

    db_session.refresh(parent_ck)
    assert len(parent_ck.child_branches) == 2
    assert branch_ck1.parent_checkpoint.id == parent_ck.id
    assert branch_ck2.parent_checkpoint.id == parent_ck.id


def test_checkpoint_all_phases(db_session, sample_task):
    """Verify all CheckpointPhase enum values round-trip."""
    for idx, phase in enumerate(CheckpointPhase):
        ck = ExecutionCheckpoint(
            agentium_id=f"CK300{idx:02d}",
            session_id="session-phases",
            task_id=sample_task.id,
            phase=phase,
            agent_states={},
            artifacts=[],
            task_state_snapshot={},
        )
        db_session.add(ck)
    db_session.commit()

    for idx, phase in enumerate(CheckpointPhase):
        fetched = db_session.query(ExecutionCheckpoint).filter_by(agentium_id=f"CK300{idx:02d}").first()
        assert fetched is not None
        assert fetched.phase == phase
