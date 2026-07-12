"""
Integration tests for the Checkpoint Diff (Unified Diff) endpoint.

Covers:
  Group 1 — Happy path: unified diff, JSON formatting, metadata
  Group 2 — Error cases: 400 self-compare, 404 missing checkpoint
"""

import uuid
import pytest
from sqlalchemy.orm import Session

from backend.services.checkpoint_service import CheckpointService
from backend.models.entities.checkpoint import ExecutionCheckpoint, CheckpointPhase
from backend.models.entities.task import Task, TaskStatus, TaskPriority, TaskType

pytestmark = pytest.mark.integration


# ===========================================================================
# Helpers
# ===========================================================================

def _create_task(db: Session, title: str) -> Task:
    """Create a minimal test task."""
    task = Task(
        agentium_id=f"T{uuid.uuid4().hex[:8].upper()}",
        title=title,
        description="Test task for checkpoint diff",
        task_type=TaskType.EXECUTION,
        status=TaskStatus.PENDING,
        priority=TaskPriority.NORMAL,
        created_by="system",
        is_active=True,
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


# ===========================================================================
# Group 1 — Happy path
# ===========================================================================

class TestCheckpointDiffEndpoint:
    """
    Unified diff between two checkpoints via
    GET /api/v1/checkpoints/{id}/diff?compare_to={id2}
    """

    def test_unified_diff_returns_json_and_metadata(self, client, seeded_db: Session):
        """
        Comparing two snapshots with different task_state_snapshot values
        should produce: pretty-printed JSON for both sides, a unified diff
        string, and both checkpoint IDs + metadata.
        """
        task_a = _create_task(seeded_db, "Checkpoint Diff A")
        task_b = _create_task(seeded_db, "Checkpoint Diff B")

        # Create checkpoint A with a known snapshot
        cp_a = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task_a.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        cp_a.task_state_snapshot = {
            "status": "pending",
            "score": 42,
            "nested": {"key": "value_a"},
        }
        seeded_db.commit()

        # Create checkpoint B with a different snapshot
        cp_b = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task_b.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        cp_b.task_state_snapshot = {
            "status": "in_progress",
            "score": 99,
            "nested": {"key": "value_b"},
        }
        seeded_db.commit()

        response = client.get(f"/api/v1/checkpoints/{cp_a.id}/diff", params={"compare_to": cp_b.id})
        assert response.status_code == 200, response.text

        body = response.json()

        # Metadata assertions
        assert body["left_checkpoint_id"] == str(cp_a.id)
        assert body["right_checkpoint_id"] == str(cp_b.id)
        assert body["left_branch"] == cp_a.branch_name
        assert body["right_branch"] == cp_b.branch_name
        assert body["left_agentium_id"] == cp_a.agentium_id
        assert body["right_agentium_id"] == cp_b.agentium_id

        # JSON should be pretty-printed
        assert "\n" in body["left_json"]
        assert "\n" in body["right_json"]
        assert '"score": 42' in body["left_json"]
        assert '"score": 99' in body["right_json"]

        # Unified diff should contain metadata filenames and changes
        assert "@@" in body["unified_diff"] or "---" in body["unified_diff"]

    def test_identical_snapshots_produces_no_diff_lines(self, client, seeded_db: Session):
        """
        When both snapshots are identical the unified diff should still be
        returned but contain no change markers.
        """
        task = _create_task(seeded_db, "Same Snapshot")

        cp_a = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        cp_b = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        # Identical snapshots
        cp_a.task_state_snapshot = {"status": "done"}
        cp_b.task_state_snapshot = {"status": "done"}
        seeded_db.commit()

        response = client.get(f"/api/v1/checkpoints/{cp_a.id}/diff", params={"compare_to": cp_b.id})
        assert response.status_code == 200

        body = response.json()
        # No change markers in identical diff
        assert "@@" not in body["unified_diff"]
        assert body["left_json"] == body["right_json"]


# ===========================================================================
# Group 2 — Error cases
# ===========================================================================

    def test_self_compare_returns_400(self, client, seeded_db: Session):
        """Comparing a checkpoint to itself is not allowed."""
        task = _create_task(seeded_db, "Self Compare")
        cp = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        seeded_db.commit()

        response = client.get(f"/api/v1/checkpoints/{cp.id}/diff", params={"compare_to": cp.id})
        assert response.status_code == 400
        assert "itself" in response.json()["error"].lower() or "cannot" in response.json()["error"].lower()

    def test_missing_checkpoint_returns_404(self, client, seeded_db: Session):
        """When either checkpoint does not exist, 404 is returned."""
        fake_id = str(uuid.uuid4())
        task = _create_task(seeded_db, "Missing Check")
        cp = CheckpointService.create_checkpoint(
            db=seeded_db,
            task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE,
            actor_id="test",
        )
        seeded_db.commit()

        response = client.get(f"/api/v1/checkpoints/{cp.id}/diff", params={"compare_to": fake_id})
        assert response.status_code == 404


# ===========================================================================
# Branch Compare Endpoint
# ===========================================================================

class TestBranchCompareEndpoint:
    """
    GET /api/v1/checkpoints/compare?left_branch=L&right_branch=R
    Structured, field-level diff of two branches' latest checkpoints.
    """

    def test_compare_branches_returns_structured_diff(self, client, seeded_db: Session):
        task = _create_task(seeded_db, "Branch Compare")
        cp_a = CheckpointService.create_checkpoint(
            db=seeded_db, task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE, actor_id="test",
        )
        cp_a.branch_name = "main"
        cp_a.task_state_snapshot = {"status": "done", "score": 1}
        seeded_db.commit()

        cp_b = CheckpointService.create_checkpoint(
            db=seeded_db, task_id=task.id,
            phase=CheckpointPhase.EXECUTION_COMPLETE, actor_id="test",
        )
        cp_b.branch_name = "feature"
        cp_b.task_state_snapshot = {"status": "done", "score": 2}
        seeded_db.commit()

        response = client.get(
            "/api/v1/checkpoints/compare",
            params={"left_branch": "main", "right_branch": "feature"},
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["left_branch"] == "main"
        assert body["right_branch"] == "feature"
        assert body["summary"]["changed"] >= 1
        score = next(d for d in body["task_state_diffs"] if d["key"] == "score")
        assert score["status"] == "changed"
        assert score["left"] == 1 and score["right"] == 2
