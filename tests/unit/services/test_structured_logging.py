# tests/unit/services/test_structured_logging.py
import pytest
import logging
import json
from backend.services.structured_logging import StructuredFormatter, set_session_id, get_session_id, structured_log_context


class TestStructuredLogging:
    def test_structured_formatter_redacts_pii(self):
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="User email: john@example.com, API key: sk-1234567890abcdef1234",
            args=(), exc_info=None
        )
        # Set extra fields as attributes on the record (standard logging pattern)
        record.user_email = "jane@example.com"
        record.normal_field = "value"

        formatted = formatter.format(record)
        log_data = json.loads(formatted)

        # Message should be redacted with MASK mode (preserves format)
        assert "j***@example.com" in log_data["message"]
        assert "******" in log_data["message"]  # API key masked
        # Extra fields should be redacted
        assert log_data["user_email"] == "j***@example.com"
        assert log_data["normal_field"] == "value"

    def test_session_id_context_var(self):
        set_session_id("session-123")
        assert get_session_id() == "session-123"

        # Should appear in formatted logs
        formatter = StructuredFormatter()
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="Test message", args=(), exc_info=None
        )
        formatted = formatter.format(record)
        log_data = json.loads(formatted)
        assert log_data["session_id"] == "session-123"

        # Clean up for test isolation
        set_session_id(None)

    def test_structured_log_context_includes_session_id(self):
        # Ensure clean state
        set_session_id(None)

        with structured_log_context(request_id="req-1", session_id="session-abc"):
            assert get_session_id() == "session-abc"
        # Should be restored after context
        assert get_session_id() is None