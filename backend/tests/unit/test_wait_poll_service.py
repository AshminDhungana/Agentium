"""Unit tests for WaitPollService — EXECUTION strategy extends Phase 16 wait & poll."""
import pytest
from unittest.mock import MagicMock, patch
from backend.models.entities.wait_condition import WaitCondition, WaitConditionStatus, WaitStrategy
from backend.models.entities.remote_execution import RemoteExecutionRecord, ExecutionStatus
from backend.services.wait_poll_service import WaitPollService
from sqlalchemy.orm import Session


class TestWaitStrategyExecution:
    def test_execution_strategy_exists(self):
        """EXECUTION strategy is available in WaitStrategy enum."""
        assert WaitStrategy.EXECUTION.value == "execution"
        assert "execution" in [s.value for s in WaitStrategy]


class TestCheckExecution:
    @pytest.fixture
    def mock_db_session(self):
        """Create a mock database session."""
        return MagicMock(spec=Session)

    def test_check_execution_completed(self, mock_db_session):
        """_check_execution returns resolved when execution is COMPLETED."""
        # Setup mock DB returning completed record
        mock_record = MagicMock(spec=RemoteExecutionRecord)
        mock_record.status = ExecutionStatus.COMPLETED
        mock_record.execution_id = "exec_abc123"
        mock_record.summary = {"schema": {"col": "int"}, "row_count": 5}
        mock_record.execution_time_ms = 1500

        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_record

        cfg = {"execution_id": "exec_abc123"}
        result = WaitPollService._check_execution(mock_db_session, cfg)

        assert result[0] is True  # resolved
        assert result[1]["status"] == "completed"
        assert result[1]["execution_id"] == "exec_abc123"

    def test_check_execution_failed(self, mock_db_session):
        """_check_execution returns resolved when execution is FAILED."""
        mock_record = MagicMock(spec=RemoteExecutionRecord)
        mock_record.status = ExecutionStatus.FAILED
        mock_record.execution_id = "exec_abc123"
        mock_record.error_message = "Container crashed"

        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_record

        cfg = {"execution_id": "exec_abc123"}
        result = WaitPollService._check_execution(mock_db_session, cfg)

        assert result[0] is True  # resolved (but with failed status)
        assert result[1]["status"] == "failed"
        assert "Container crashed" in result[1]["error"]

    def test_check_execution_still_running(self, mock_db_session):
        """_check_execution returns pending when execution is RUNNING."""
        mock_record = MagicMock(spec=RemoteExecutionRecord)
        mock_record.status = ExecutionStatus.RUNNING

        mock_db_session.query.return_value.filter.return_value.first.return_value = mock_record

        cfg = {"execution_id": "exec_abc123"}
        result = WaitPollService._check_execution(mock_db_session, cfg)

        assert result[0] is False  # still pending
        assert result[1] is None

    def test_check_execution_not_found(self, mock_db_session):
        """_check_execution returns pending when execution record doesn't exist yet."""
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        cfg = {"execution_id": "exec_notfound"}
        result = WaitPollService._check_execution(mock_db_session, cfg)

        assert result[0] is False
        assert result[1] is None

    def test_check_execution_missing_config(self, mock_db_session):
        """_check_execution returns pending when execution_id missing from config."""
        cfg = {}
        result = WaitPollService._check_execution(mock_db_session, cfg)
        assert result[0] is False
        assert result[1] is None


class TestPollExecutionConditions:
    @patch("backend.services.tasks.task_executor.get_task_db")
    def test_poll_execution_conditions_only_executions(self, mock_get_db):
        """poll_execution_conditions only evaluates EXECUTION strategy conditions."""
        from backend.services.tasks.task_executor import poll_execution_conditions

        # Setup mock
        mock_db = MagicMock()
        mock_get_db.return_value.__enter__.return_value = mock_db

        # Create mock conditions - only EXECUTION should be queried
        mock_exec_cond = MagicMock(spec=WaitCondition)
        mock_exec_cond.agentium_id = "WC00001"
        mock_exec_cond.strategy = WaitStrategy.EXECUTION

        mock_db.query.return_value.filter.return_value.all.return_value = [mock_exec_cond]

        # Call the task
        result = poll_execution_conditions()

        # Verify result structure
        assert "resolved" in result
        assert "expired" in result
        assert "errors" in result
        assert "skipped" in result