# backend/tests/unit/test_uncertainty_detector.py
import pytest
from backend.core.uncertainty_detector import UncertaintySignal


def test_uncertainty_signal_creation():
    signal = UncertaintySignal(
        reason="tool_error",
        affected_tools=["read_file"],
        details={"error": "File not found"},
        suggested_question="My tool 'read_file' returned an error: File not found. What should I do?",
        severity="high"
    )
    assert signal.reason == "tool_error"
    assert signal.affected_tools == ["read_file"]
    assert signal.severity == "high"


from unittest.mock import MagicMock
from sqlalchemy.orm import Session
from backend.core.uncertainty_detector import UncertaintyDetector, UncertaintySignal


@pytest.fixture
def mock_agent():
    agent = MagicMock()
    agent.agentium_id = "30001"
    return agent


@pytest.fixture
def mock_db():
    return MagicMock(spec=Session)


def test_tool_error_triggers_signal(mock_agent, mock_db):
    results = [{"status": "error", "tool_name": "read_file", "error": "File not found", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "tool_error"
    assert signal.severity == "high"
    assert "read_file" in signal.affected_tools


def test_timeout_triggers_signal(mock_agent, mock_db):
    results = [{"status": "timeout", "tool_name": "execute_command", "error": "Timed out after 30s", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "tool_error"
    assert signal.severity == "high"


def test_cancelled_triggers_signal(mock_agent, mock_db):
    results = [{"status": "cancelled", "tool_name": "browser_control", "error": "Cancelled by user", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "tool_error"


def test_empty_result_triggers_signal(mock_agent, mock_db):
    results = [{"status": "success", "tool_name": "read_file", "result": {}}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "empty_result"
    assert signal.severity == "medium"


def test_empty_result_none_triggers_signal(mock_agent, mock_db):
    results = [{"status": "success", "tool_name": "read_file", "result": None}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "empty_result"


def test_missing_expected_fields_triggers_signal(mock_agent, mock_db):
    # read_file expects "content" key
    results = [{"status": "success", "tool_name": "read_file", "result": {"size": 100}}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "missing_expected_fields"
    assert "content" in signal.details["missing_fields"]


def test_hallucinated_tool_no_expected_keys(mock_agent, mock_db):
    # Tool not in TOOL_EXPECTED_KEYS - no missing field check
    results = [{"status": "success", "tool_name": "unknown_tool", "result": {"data": "x"}}]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is None  # Unknown tools don't trigger missing field check


def test_conflicting_results_triggers_signal(mock_agent, mock_db):
    results = [
        {"status": "success", "tool_name": "tool_a", "result": {"value": "first"}},
        {"status": "success", "tool_name": "tool_b", "result": {"value": "second"}},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "conflicting_results"
    assert signal.severity == "low"
    assert set(signal.affected_tools) == {"tool_a", "tool_b"}


def test_no_conflict_when_same_value(mock_agent, mock_db):
    results = [
        {"status": "success", "tool_name": "tool_a", "result": {"value": "same"}},
        {"status": "success", "tool_name": "tool_b", "result": {"value": "same"}},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is None


def test_all_tools_failed_triggers_signal(mock_agent, mock_db):
    results = [
        {"status": "error", "tool_name": "tool_a", "error": "Error A"},
        {"status": "error", "tool_name": "tool_b", "error": "Error B"},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is not None
    assert signal.reason == "all_tools_failed"
    assert signal.severity == "high"


def test_clean_results_no_signal(mock_agent, mock_db):
    results = [
        {"status": "success", "tool_name": "read_file", "result": {"content": "file data"}},
        {"status": "success", "tool_name": "execute_command", "result": {"stdout": "output", "stderr": "", "exit_code": 0}},
    ]
    signal = UncertaintyDetector.analyze(results, mock_agent, mock_db)
    assert signal is None


def test_empty_results_list_no_signal(mock_agent, mock_db):
    signal = UncertaintyDetector.analyze([], mock_agent, mock_db)
    assert signal is None