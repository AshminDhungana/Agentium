"""Unit tests for WaitPollService — EXECUTION strategy extends Phase 16 wait & poll."""
import pytest
from unittest.mock import MagicMock, patch
from backend.models.entities.wait_condition import WaitStrategy, WaitConditionStatus
from backend.models.entities.remote_execution import RemoteExecutionRecord, ExecutionStatus
from backend.services.wait_poll_service import WaitPollService


class TestWaitStrategyExecution:
    def test_execution_strategy_exists(self):
        """EXECUTION strategy is available in WaitStrategy enum."""
        assert WaitStrategy.EXECUTION.value == "execution"
        assert "execution" in [s.value for s in WaitStrategy]


class TestCheckExecution:
    @pytest.fixture
    def mock_db(self):
        with patch("backend.models.database.get_db_context") as mock:
            yield mock

    def test_check_execution_completed(self, mock_db):
        """_check_execution returns resolved when execution is COMPLETED."""
        # Setup mock DB returning completed record
        mock_record = MagicMock(spec=RemoteExecutionRecord)
        mock_record.status = ExecutionStatus.COMPLETED
        mock_record.execution_id = "exec_abc123"
        mock_record.summary = {"schema": {"col": "int"}, "row_count": 5}
        mock_record.execution_time_ms = 1500

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_record
        mock_db.return_value.__enter__.return_value = mock_session

        cfg = {"execution_id": "exec_abc123"}
        result = WaitPollService._check_execution(cfg)

        assert result[0] is True  # resolved
        assert result[1]["status"] == "completed"
        assert result[1]["execution_id"] == "exec_abc123"

    def test_check_execution_failed(self, mock_db):
        """_check_execution returns resolved when execution is FAILED."""
        mock_record = MagicMock(spec=RemoteExecutionRecord)
        mock_record.status = ExecutionStatus.FAILED
        mock_record.execution_id = "exec_abc123"
        mock_record.error_message = "Container crashed"

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_record
        mock_db.return_value.__enter__.return_value = mock_session

        cfg = {"execution_id": "exec_abc123"}
        result = WaitPollService._check_execution(cfg)

        assert result[0] is True  # resolved (but with failed status)
        assert result[1]["status"] == "failed"
        assert "Container crashed" in result[1]["error"]

    def test_check_execution_still_running(self, mock_db):
        """_check_execution returns pending when execution is RUNNING."""
        mock_record = MagicMock(spec=RemoteExecutionRecord)
        mock_record.status = ExecutionStatus.RUNNING

        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = mock_record
        mock_db.return_value.__enter__.return_value = mock_session

        cfg = {"execution_id": "exec_abc123"}
        result = WaitPollService._check_execution(cfg)

        assert result[0] is False  # still pending
        assert result[1] is None

    def test_check_execution_not_found(self, mock_db):
        """_check_execution returns pending when execution record doesn't exist yet."""
        mock_session = MagicMock()
        mock_session.query.return_value.filter.return_value.first.return_value = None
        mock_db.return_value.__enter__.return_value = mock_session

        cfg = {"execution_id": "exec_notfound"}
        result = WaitPollService._check_execution(cfg)

        assert result[0] is False
        assert result[1] is None

    def test_check_execution_missing_config(self):
        """_check_execution returns pending when execution_id missing from config."""
        cfg = {}
        result = WaitPollService._check_execution(cfg)
        assert result[0] is False
        assert result[1] is None