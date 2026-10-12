"""
Integration Tests — Workflow CRUD  (Phase 18.1)
===============================================

Covers:
  18.1.1 — POST /api/v1/workflows  creates a new workflow definition
  18.1.2 — GET  /api/v1/workflows  lists workflows
  18.1.3 — GET  /api/v1/workflows/{id}  returns workflow details
  18.1.4 — Workflow DAG structure validates correctly

All API tests use the standard ``client`` fixture (FastAPI TestClient with
dependency overrides wired to the integration-test PostgreSQL + Redis stack).
DAG-validation unit tests exercise ``WorkflowEngine.validate_dag`` directly
and therefore do *not* need a DB connection.
"""

import uuid
import pytest
from unittest.mock import patch, MagicMock

from backend.services.workflow_engine import WorkflowEngine
from backend.models.entities.workflow import Workflow, WorkflowStep, WorkflowStepType

pytestmark = pytest.mark.integration


# ── Helpers ──────────────────────────────────────────────────────────────────

def _unique(prefix: str = "wf") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


def _minimal_template(*, step_type: str = "task") -> dict:
    """Single-step template — the simplest valid DAG."""
    return {
        "steps": [
            {
                "step_index": 0,
                "type": step_type,
                "config": {"task_title": "Only step", "prompt": "Do something"},
                "on_success_step": None,
                "on_failure_step": None,
            }
        ]
    }


def _linear_template(n: int = 3) -> dict:
    """Chain of *n* task-steps with no branches."""
    return {
        "steps": [
            {
                "step_index": i,
                "type": "task",
                "config": {"task_title": f"Step {i}", "prompt": f"Prompt {i}"},
                "on_success_step": i + 1 if i < n - 1 else None,
                "on_failure_step": None,
            }
            for i in range(n)
        ]
    }


# ── 18.1.1 — POST /api/v1/workflows ──────────────────────────────────────────

class TestCreateWorkflow:
    """18.1.1 — POST /api/v1/workflows creates a new workflow definition."""

    @pytest.fixture(autouse=True)
    def _mock_celery(self):
        """Prevent Celery dispatch in all tests in this class."""
        with patch("backend.services.workflow_engine.workflow_step_runner") as mock:
            mock.delay = MagicMock()
            mock.apply_async = MagicMock()
            yield

    def test_creates_workflow_returns_200(self, client):
        """POST with valid name + template_json returns 200 and the new workflow dict."""
        resp = client.post(
            "/api/v1/workflows/",
            json={"name": _unique("wf"), "template_json": _minimal_template()},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "id" in body
        assert body["name"].startswith("wf_")
        assert "template_json" in body
        assert body["version"] == 1

    def test_creates_workflow_persists_to_db(self, client, db_session):
        """The created workflow must be visible in the DB."""
        name = _unique("persist")
        resp = client.post(
            "/api/v1/workflows/",
            json={"name": name, "template_json": _minimal_template()},
        )
        assert resp.status_code == 200, resp.text
        wf_id = resp.json()["id"]

        wf = db_session.query(Workflow).filter(Workflow.id == wf_id).first()
        assert wf is not None
        assert wf.name == name

    def test_creates_workflow_stores_steps(self, client, db_session):
        """Steps from template_json must be written to workflow_steps table."""
        name = _unique("steps")
        resp = client.post(
            "/api/v1/workflows/",
            json={"name": name, "template_json": _linear_template(3)},
        )
        assert resp.status_code == 200, resp.text
        wf_id = resp.json()["id"]

        steps = (
            db_session.query(WorkflowStep)
            .filter(WorkflowStep.workflow_id == wf_id)
            .order_by(WorkflowStep.step_index)
            .all()
        )
        assert len(steps) == 3
        assert [s.step_index for s in steps] == [0, 1, 2]

    def test_creates_workflow_with_cron(self, client):
        """schedule_cron field is stored when provided."""
        resp = client.post(
            "/api/v1/workflows/",
            json={
                "name": _unique("cron"),
                "template_json": _minimal_template(),
                "schedule_cron": "0 6 * * *",
            },
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["schedule_cron"] == "0 6 * * *"

    def test_missing_name_returns_400(self, client):
        """Omitting 'name' returns 400."""
        resp = client.post(
            "/api/v1/workflows/",
            json={"template_json": _minimal_template()},
        )
        assert resp.status_code == 400

    def test_missing_template_json_returns_400(self, client):
        """Omitting 'template_json' returns 400."""
        resp = client.post(
            "/api/v1/workflows/",
            json={"name": _unique("notemplate")},
        )
        assert resp.status_code == 400

    def test_cyclic_dag_returns_400(self, client):
        """A cyclic template is rejected with 400 INVALID_WORKFLOW_DAG."""
        cyclic = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 1, "on_failure_step": None},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": 0, "on_failure_step": None},
            ]
        }
        resp = client.post(
            "/api/v1/workflows/",
            json={"name": _unique("cyclic"), "template_json": cyclic},
        )
        assert resp.status_code == 400
        assert "cycle" in resp.text.lower() or "INVALID_WORKFLOW_DAG" in resp.text


# ── 18.1.2 — GET /api/v1/workflows ───────────────────────────────────────────

class TestListWorkflows:
    """18.1.2 — GET /api/v1/workflows lists workflows."""

    @pytest.fixture(autouse=True)
    def _mock_celery(self):
        with patch("backend.services.workflow_engine.workflow_step_runner") as mock:
            mock.delay = MagicMock()
            mock.apply_async = MagicMock()
            yield

    def test_list_returns_200(self, client):
        """GET /api/v1/workflows returns 200 with a list."""
        resp = client.get("/api/v1/workflows/")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_includes_created_workflow(self, client):
        """A freshly created workflow appears in the list."""
        name = _unique("listed")
        client.post(
            "/api/v1/workflows/",
            json={"name": name, "template_json": _minimal_template()},
        )
        resp = client.get("/api/v1/workflows/")
        assert resp.status_code == 200
        names = [w["name"] for w in resp.json()]
        assert name in names

    def test_list_omits_inactive_workflows(self, client, db_session):
        """is_active=False workflows must not appear in the list."""
        name = _unique("inactive")
        post_resp = client.post(
            "/api/v1/workflows/",
            json={"name": name, "template_json": _minimal_template()},
        )
        assert post_resp.status_code == 200
        wf_id = post_resp.json()["id"]

        # Deactivate directly in DB
        wf = db_session.query(Workflow).filter(Workflow.id == wf_id).first()
        wf.is_active = False
        db_session.commit()

        resp = client.get("/api/v1/workflows/")
        ids = [w["id"] for w in resp.json()]
        assert wf_id not in ids

    def test_list_returns_list_shape(self, client):
        """Each entry in the list must contain at least id, name, version."""
        # Create at least one so the list is non-empty
        client.post(
            "/api/v1/workflows/",
            json={"name": _unique("shape"), "template_json": _minimal_template()},
        )
        resp = client.get("/api/v1/workflows/")
        assert resp.status_code == 200
        for wf in resp.json():
            assert "id" in wf
            assert "name" in wf
            assert "version" in wf


# ── 18.1.3 — GET /api/v1/workflows/{id} ──────────────────────────────────────

class TestGetWorkflow:
    """18.1.3 — GET /api/v1/workflows/{id} returns workflow details."""

    @pytest.fixture(autouse=True)
    def _mock_celery(self):
        with patch("backend.services.workflow_engine.workflow_step_runner") as mock:
            mock.delay = MagicMock()
            mock.apply_async = MagicMock()
            yield

    def test_get_existing_workflow_returns_200(self, client):
        """GET by valid ID returns 200 with correct data."""
        name = _unique("detail")
        post = client.post(
            "/api/v1/workflows/",
            json={"name": name, "template_json": _minimal_template()},
        )
        assert post.status_code == 200
        wf_id = post.json()["id"]

        resp = client.get(f"/api/v1/workflows/{wf_id}")
        assert resp.status_code == 200
        body = resp.json()
        assert body["id"] == wf_id
        assert body["name"] == name

    def test_get_workflow_returns_template_json(self, client):
        """The response includes the full template_json."""
        template = _linear_template(2)
        post = client.post(
            "/api/v1/workflows/",
            json={"name": _unique("tmpl"), "template_json": template},
        )
        wf_id = post.json()["id"]

        resp = client.get(f"/api/v1/workflows/{wf_id}")
        assert resp.status_code == 200
        assert resp.json()["template_json"] == template

    def test_get_nonexistent_workflow_returns_404(self, client):
        """GET with an unknown ID returns 404."""
        resp = client.get(f"/api/v1/workflows/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_get_workflow_returns_version(self, client):
        """Version field starts at 1."""
        post = client.post(
            "/api/v1/workflows/",
            json={"name": _unique("ver"), "template_json": _minimal_template()},
        )
        wf_id = post.json()["id"]
        resp = client.get(f"/api/v1/workflows/{wf_id}")
        assert resp.json()["version"] == 1


# ── 18.1.4 — Workflow DAG structure validates correctly ───────────────────────

class TestDAGValidation:
    """
    18.1.4 — Validate DAG structure directly via WorkflowEngine.validate_dag.
    These tests are pure unit tests (no DB required) so they run fast and
    without infrastructure.
    """

    # ── Valid cases ─────────────────────────────────────────────────────────

    def test_valid_single_step(self):
        """A single task step with no transitions is valid."""
        assert WorkflowEngine.validate_dag(_minimal_template()) == []

    def test_valid_linear_chain(self):
        """A straight chain of 5 steps with no branches is valid."""
        assert WorkflowEngine.validate_dag(_linear_template(5)) == []

    def test_valid_all_step_types(self):
        """Every WorkflowStepType value must be accepted."""
        for stype in WorkflowStepType:
            tmpl = _minimal_template(step_type=stype.value)
            errors = WorkflowEngine.validate_dag(tmpl)
            assert errors == [], f"Step type {stype.value!r} should be valid but got: {errors}"

    def test_valid_fork_no_cycle(self):
        """A template where on_success and on_failure diverge to different leaf steps is valid."""
        template = {
            "steps": [
                {"step_index": 0, "type": "condition", "config": {}, "on_success_step": 1, "on_failure_step": 2},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": None, "on_failure_step": None},
                {"step_index": 2, "type": "task", "config": {}, "on_success_step": None, "on_failure_step": None},
            ]
        }
        assert WorkflowEngine.validate_dag(template) == []

    def test_valid_diamond_shape(self):
        """A diamond-shaped DAG (0->1, 0->2, 1->3, 2->3) is valid."""
        template = {
            "steps": [
                {"step_index": 0, "type": "condition", "config": {}, "on_success_step": 1, "on_failure_step": 2},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": 3, "on_failure_step": None},
                {"step_index": 2, "type": "task", "config": {}, "on_success_step": 3, "on_failure_step": None},
                {"step_index": 3, "type": "task", "config": {}, "on_success_step": None, "on_failure_step": None},
            ]
        }
        assert WorkflowEngine.validate_dag(template) == []

    def test_valid_null_references(self):
        """on_success_step and on_failure_step may be null / absent."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}},  # no on_* keys at all
            ]
        }
        assert WorkflowEngine.validate_dag(template) == []

    # ── Missing required fields ──────────────────────────────────────────────

    def test_missing_steps_key(self):
        """template_json without 'steps' key is invalid."""
        errors = WorkflowEngine.validate_dag({"name": "bad"})
        assert any("steps" in e for e in errors)

    def test_empty_steps_list(self):
        """An empty steps list is invalid."""
        errors = WorkflowEngine.validate_dag({"steps": []})
        assert errors  # at least one error

    def test_step_missing_step_index(self):
        """A step without 'step_index' produces an error."""
        template = {"steps": [{"type": "task", "config": {}}]}
        errors = WorkflowEngine.validate_dag(template)
        assert any("step_index" in e for e in errors)

    def test_step_missing_type(self):
        """A step without 'type' produces an error."""
        template = {"steps": [{"step_index": 0, "config": {}}]}
        errors = WorkflowEngine.validate_dag(template)
        assert any("type" in e for e in errors)

    def test_step_invalid_type(self):
        """An unrecognised step type produces an error."""
        template = {"steps": [{"step_index": 0, "type": "teleport", "config": {}}]}
        errors = WorkflowEngine.validate_dag(template)
        assert any("invalid type" in e.lower() for e in errors)

    # ── Duplicate step_index ─────────────────────────────────────────────────

    def test_duplicate_step_index(self):
        """Two steps sharing the same step_index produce an error."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}},
                {"step_index": 0, "type": "task", "config": {}},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("duplicate" in e.lower() for e in errors)

    # ── Dangling references ──────────────────────────────────────────────────

    def test_on_success_step_points_to_nonexistent_index(self):
        """on_success_step referencing a missing step_index is invalid."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 99},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("non-existent" in e.lower() or "99" in e for e in errors)

    def test_on_failure_step_points_to_nonexistent_index(self):
        """on_failure_step referencing a missing step_index is invalid."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_failure_step": 42},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("non-existent" in e.lower() or "42" in e for e in errors)

    # ── Cycle detection ──────────────────────────────────────────────────────

    def test_self_loop_is_cyclic(self):
        """A step that references itself via on_success_step is a cycle."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 0},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("cycle" in e.lower() for e in errors)

    def test_two_step_cycle(self):
        """Step 0 -> 1 -> 0 is a cycle."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 1, "on_failure_step": None},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": 0, "on_failure_step": None},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("cycle" in e.lower() for e in errors)

    def test_three_step_cycle(self):
        """Step 0 -> 1 -> 2 -> 0 is a cycle."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 1},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": 2},
                {"step_index": 2, "type": "task", "config": {}, "on_success_step": 0},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("cycle" in e.lower() for e in errors)

    def test_cycle_in_failure_branch(self):
        """A cycle through on_failure_step is also detected."""
        template = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 1, "on_failure_step": None},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": None, "on_failure_step": 0},
            ]
        }
        errors = WorkflowEngine.validate_dag(template)
        assert any("cycle" in e.lower() for e in errors)

    def test_non_cyclic_with_branching_is_valid(self):
        """A multi-branch DAG with no cycles is valid (regression guard)."""
        template = {
            "steps": [
                {"step_index": 0, "type": "condition", "config": {}, "on_success_step": 1, "on_failure_step": 2},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": 3, "on_failure_step": None},
                {"step_index": 2, "type": "task", "config": {}, "on_success_step": 3, "on_failure_step": None},
                {"step_index": 3, "type": "task", "config": {}, "on_success_step": None, "on_failure_step": None},
            ]
        }
        assert WorkflowEngine.validate_dag(template) == []

    # ── PUT /api/v1/workflows/{id} also validates ────────────────────────────

    def test_update_route_rejects_cyclic_dag(self, client):
        """PUT /api/v1/workflows/{id} also runs DAG validation and returns 400 for cycles."""
        with patch("backend.services.workflow_engine.workflow_step_runner") as mock:
            mock.delay = MagicMock()
            mock.apply_async = MagicMock()

            # First create a valid workflow
            post = client.post(
                "/api/v1/workflows/",
                json={"name": _unique("update_cyclic"), "template_json": _minimal_template()},
            )
            assert post.status_code == 200
            wf_id = post.json()["id"]

        # Now try to update it with a cyclic template
        cyclic = {
            "steps": [
                {"step_index": 0, "type": "task", "config": {}, "on_success_step": 1},
                {"step_index": 1, "type": "task", "config": {}, "on_success_step": 0},
            ]
        }
        resp = client.put(
            f"/api/v1/workflows/{wf_id}",
            json={"template_json": cyclic},
        )
        assert resp.status_code == 400
        assert "cycle" in resp.text.lower() or "INVALID_WORKFLOW_DAG" in resp.text
