# tests/unit/test_structured_logging.py
import logging
import pytest
from backend.services.structured_logging import (
    get_structured_logger, log_exception, structured_log_context, set_request_id
)


def test_log_exception_includes_full_context(caplog):
    """log_exception should include error_type, error_message, traceback, and context."""
    logger = get_structured_logger("test")
    set_request_id("test-req-123")

    try:
        raise ValueError("test error message")
    except ValueError as e:
        with structured_log_context(step="test_step", agent_id="agent-1"):
            log_exception(logger, "Operation failed", e, context={"input_param": "value", "retry_count": 2})

    # Find the error log
    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    record = error_records[0]

    # Check structured fields are present
    assert hasattr(record, "error_type") and record.error_type == "ValueError"
    assert hasattr(record, "error_message") and record.error_message == "test error message"
    assert hasattr(record, "traceback") and "ValueError: test error message" in record.traceback
    assert hasattr(record, "context") and record.context == {"input_param": "value", "retry_count": 2}
    assert hasattr(record, "request_id") and record.request_id == "test-req-123"
    assert hasattr(record, "step") and record.step == "test_step"
    assert hasattr(record, "agent_id") and record.agent_id == "agent-1"


def test_log_exception_without_context(caplog):
    """log_exception should work without optional context dict."""
    logger = get_structured_logger("test")

    try:
        raise RuntimeError("runtime error")
    except RuntimeError as e:
        log_exception(logger, "Failed", e)

    error_records = [r for r in caplog.records if r.levelname == "ERROR"]
    assert len(error_records) == 1
    record = error_records[0]
    assert record.error_type == "RuntimeError"
    assert record.error_message == "runtime error"
    assert record.context == {}