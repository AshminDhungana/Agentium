"""
Backend API tests for A/B testing routes.
Verifies experiment CRUD, stats, recommendations, and auth gates.
"""
import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from backend.api.routes.ab_testing import (
    create_experiment,
    list_experiments,
    get_experiment,
    delete_experiment,
    cancel_experiment,
    get_ab_testing_stats,
    get_model_recommendations,
    require_admin,
    ExperimentCreate,
    _serialize_experiment_summary,
    _serialize_experiment_detail,
    _run_counts,
    _experiment_progress,
)
from backend.models.entities.ab_testing import (
    Experiment, ExperimentRun, ExperimentResult,
    ExperimentStatus, RunStatus,
)
from backend.core.exceptions import (
    ForbiddenError, NotFoundError, BadRequestError,
)


class TestABTestingRoutes:
    @pytest.fixture
    def mock_db(self):
        db = MagicMock()
        return db

    @pytest.fixture
    def admin_user(self):
        return {
            "id": "usr-uuid-1",
            "username": "sovereign",
            "is_admin": True,
            "isSovereign": True,
            "role": "primary_sovereign",
        }

    @pytest.fixture
    def non_admin_user(self):
        return {
            "id": "usr-uuid-2",
            "username": "viewer",
            "is_admin": False,
            "isSovereign": False,
            "role": "user",
        }

    @pytest.fixture
    def mock_experiment(self):
        exp = MagicMock(spec=Experiment)
        exp.id = "exp-001"
        exp.name = "GPT-4o vs Claude 3.5"
        exp.description = "Summarisation test"
        exp.task_template = "Summarise this document."
        exp.system_prompt = None
        exp.test_iterations = 1
        exp.status = ExperimentStatus.COMPLETED
        exp.created_by = "sovereign"
        exp.created_at = datetime(2026, 9, 28, 10, 0, 0)
        exp.started_at = datetime(2026, 9, 28, 10, 0, 1)
        exp.completed_at = datetime(2026, 9, 28, 10, 5, 0)

        # Runs
        run1 = MagicMock(spec=ExperimentRun)
        run1.id = "run-001"
        run1.config_id = "cfg-001"
        run1.model_name = "gpt-4o"
        run1.iteration_number = 1
        run1.status = RunStatus.COMPLETED
        run1.tokens_used = 150
        run1.latency_ms = 1200
        run1.cost_usd = 0.0032
        run1.overall_quality_score = 85.0
        run1.critic_plan_score = 80.0
        run1.critic_code_score = 70.0
        run1.critic_output_score = 90.0
        run1.constitutional_violations = 0
        run1.output_text = "Here are the 3 bullet points..."
        run1.error_message = None
        run1.started_at = datetime(2026, 9, 28, 10, 0, 1)
        run1.completed_at = datetime(2026, 9, 28, 10, 0, 3)

        run2 = MagicMock(spec=ExperimentRun)
        run2.id = "run-002"
        run2.config_id = "cfg-002"
        run2.model_name = "claude-3.5-sonnet"
        run2.iteration_number = 1
        run2.status = RunStatus.COMPLETED
        run2.tokens_used = 180
        run2.latency_ms = 950
        run2.cost_usd = 0.0028
        run2.overall_quality_score = 92.0
        run2.critic_plan_score = 88.0
        run2.critic_code_score = 75.0
        run2.critic_output_score = 95.0
        run2.constitutional_violations = 0
        run2.output_text = "Summary: 1) First point..."
        run2.error_message = None
        run2.started_at = datetime(2026, 9, 28, 10, 0, 1)
        run2.completed_at = datetime(2026, 9, 28, 10, 0, 2)

        exp.runs = [run1, run2]

        # Result
        result = MagicMock(spec=ExperimentResult)
        result.winner_config_id = "cfg-002"
        result.winner_model_name = "claude-3.5-sonnet"
        result.selection_reason = "Higher quality with lower cost"
        result.confidence_score = 87.5
        result.model_comparisons = {"models": []}
        result.created_at = datetime(2026, 9, 28, 10, 5, 0)

        exp.results = [result]

        return exp

    # ── Auth gate ─────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_require_admin_rejects_non_admin(self, non_admin_user):
        """Non-admin users are rejected with ForbiddenError."""
        with pytest.raises(ForbiddenError):
            await require_admin(current_user=non_admin_user)

    @pytest.mark.asyncio
    async def test_require_admin_allows_admin(self, admin_user):
        """Admin users pass the gate."""
        result = await require_admin(current_user=admin_user)
        assert result["username"] == "sovereign"

    # ── POST /experiments ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_experiment_success(self, mock_db, admin_user, mock_experiment):
        """POST /experiments creates experiment and auto-starts it."""
        background_tasks = MagicMock()

        with patch("backend.api.routes.ab_testing.ABTestingService") as MockService:
            instance = MockService.return_value
            from unittest.mock import AsyncMock
            instance.create_experiment = AsyncMock(return_value=mock_experiment)

            data = ExperimentCreate(
                name="Test Experiment",
                task_template="Test this",
                config_ids=["cfg-001", "cfg-002"],
                iterations=1,
            )

            result = await create_experiment(
                data=data,
                background_tasks=background_tasks,
                db=mock_db,
                current_user=admin_user,
            )

            assert result["id"] == "exp-001"
            assert result["name"] == "GPT-4o vs Claude 3.5"
            # Background task should be scheduled
            background_tasks.add_task.assert_called_once()

    # ── GET /experiments ──────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_experiments_with_pagination(self, mock_db, admin_user, mock_experiment):
        """GET /experiments returns paginated list."""
        # Build a mock query chain
        query = mock_db.query.return_value.options.return_value
        query.count.return_value = 1
        query.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            mock_experiment
        ]

        result = await list_experiments(
            status=None,
            limit=50,
            offset=0,
            db=mock_db,
            current_user=admin_user,
        )

        assert result["total"] == 1
        assert result["limit"] == 50
        assert result["offset"] == 0
        assert len(result["items"]) == 1
        assert result["items"][0]["id"] == "exp-001"

    @pytest.mark.asyncio
    async def test_list_experiments_with_status_filter(self, mock_db, admin_user, mock_experiment):
        """GET /experiments?status=completed filters correctly."""
        query = mock_db.query.return_value.options.return_value
        filtered = query.filter.return_value
        filtered.count.return_value = 1
        filtered.order_by.return_value.offset.return_value.limit.return_value.all.return_value = [
            mock_experiment
        ]

        result = await list_experiments(
            status="completed",
            limit=50,
            offset=0,
            db=mock_db,
            current_user=admin_user,
        )

        assert result["total"] == 1
        assert result["items"][0]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_list_experiments_invalid_status(self, mock_db, admin_user):
        """GET /experiments?status=invalid raises BadRequestError."""
        query = mock_db.query.return_value.options.return_value
        # filter() will be called with invalid status causing ValueError
        with pytest.raises(BadRequestError):
            await list_experiments(
                status="invalid_status",
                limit=50,
                offset=0,
                db=mock_db,
                current_user=admin_user,
            )

    # ── GET /experiments/{id} ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_experiment_returns_detail(self, mock_db, admin_user, mock_experiment):
        """GET /experiments/{id} returns full detail with runs and comparison."""
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = mock_experiment

        result = await get_experiment(
            experiment_id="exp-001",
            db=mock_db,
            current_user=admin_user,
        )

        assert result["id"] == "exp-001"
        assert result["task_template"] == "Summarise this document."
        assert len(result["runs"]) == 2
        assert result["runs"][0]["model"] == "gpt-4o"
        assert result["comparison"]["winner"]["model"] == "claude-3.5-sonnet"

    @pytest.mark.asyncio
    async def test_get_experiment_not_found(self, mock_db, admin_user):
        """GET /experiments/{id} for non-existent ID raises NotFoundError."""
        mock_db.query.return_value.options.return_value.filter.return_value.first.return_value = None

        with pytest.raises(NotFoundError):
            await get_experiment(
                experiment_id="nonexistent",
                db=mock_db,
                current_user=admin_user,
            )

    # ── DELETE /experiments/{id} ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_delete_experiment_success(self, mock_db, admin_user, mock_experiment):
        """DELETE /experiments/{id} deletes completed experiments."""
        mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment

        result = await delete_experiment(
            experiment_id="exp-001",
            db=mock_db,
            current_user=admin_user,
        )

        assert result["message"] == "Experiment deleted"
        mock_db.delete.assert_called_once_with(mock_experiment)
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_delete_running_experiment_rejected(self, mock_db, admin_user, mock_experiment):
        """DELETE /experiments/{id} rejects running experiments."""
        mock_experiment.status = ExperimentStatus.RUNNING
        mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment

        with pytest.raises(BadRequestError):
            await delete_experiment(
                experiment_id="exp-001",
                db=mock_db,
                current_user=admin_user,
            )

    # ── POST /experiments/{id}/cancel ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_cancel_experiment_success(self, mock_db, admin_user, mock_experiment):
        """POST /experiments/{id}/cancel cancels running experiments."""
        mock_experiment.status = ExperimentStatus.RUNNING
        mock_db.query.return_value.filter.return_value.first.return_value = mock_experiment

        result = await cancel_experiment(
            experiment_id="exp-001",
            db=mock_db,
            current_user=admin_user,
        )

        assert result["message"] == "Experiment cancelled"
        assert mock_experiment.status == ExperimentStatus.CANCELLED
        mock_db.commit.assert_called_once()

    # ── Serialization helpers ─────────────────────────────────────────────

    def test_run_counts(self, mock_experiment):
        """_run_counts correctly counts completed and failed runs."""
        counts = _run_counts(mock_experiment)
        assert counts["total"] == 2
        assert counts["completed"] == 2
        assert counts["failed"] == 0

    def test_experiment_progress(self, mock_experiment):
        """_experiment_progress computes percentage correctly."""
        progress = _experiment_progress(mock_experiment)
        assert progress == 100.0

    def test_serialize_summary(self, mock_experiment):
        """_serialize_experiment_summary produces correct shape."""
        result = _serialize_experiment_summary(mock_experiment)
        assert result["id"] == "exp-001"
        assert result["name"] == "GPT-4o vs Claude 3.5"
        assert result["status"] == "completed"
        assert result["models_tested"] == 2
        assert result["progress"] == 100.0

    def test_serialize_detail_includes_comparison(self, mock_experiment):
        """_serialize_experiment_detail includes comparison and runs."""
        result = _serialize_experiment_detail(mock_experiment)
        assert result["task_template"] == "Summarise this document."
        assert len(result["runs"]) == 2
        assert result["comparison"]["winner"]["model"] == "claude-3.5-sonnet"
        assert result["comparison"]["winner"]["confidence"] == 87.5
