"""
Integration test for Section 14.6: Structured Logging correlation
Verifies request_id propagates across HTTP -> Celery -> WebSocket
"""
import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.core.correlation_middleware import (
    CorrelationIdMiddleware,
    ws_correlation_manager,
    inject_correlation_into_task_kwargs,
    extract_correlation_from_task_kwargs,
)
from backend.services.structured_logging import (
    get_structured_logger,
    setup_structured_logging,
    structured_log_context,
)


@pytest.fixture(autouse=True)
def setup_logging():
    """Ensure structured logging is configured for tests."""
    setup_structured_logging(logging.INFO)
    yield


class TestStructuredLoggingCorrelation:
    """Test request_id correlation across HTTP, Celery, WebSocket."""

    def test_http_middleware_generates_request_id(self):
        """HTTP request without header gets generated request_id in response."""
        client = TestClient(app)
        response = client.get("/api/health")

        assert response.status_code == 200
        assert "x-request-id" in response.headers
        assert len(response.headers["x-request-id"]) == 12  # uuid4()[:12]

    def test_http_middleware_uses_provided_request_id(self):
        """HTTP request with X-Request-ID header uses that ID."""
        client = TestClient(app)
        response = client.get("/api/health", headers={"X-Request-ID": "test-req-123"})

        assert response.headers["x-request-id"] == "test-req-123"

    def test_http_middleware_falls_back_to_correlation_id(self):
        """HTTP request with X-Correlation-ID uses it when X-Request-ID absent."""
        client = TestClient(app)
        response = client.get("/api/health", headers={"X-Correlation-ID": "corr-456"})

        assert response.headers["x-request-id"] == "corr-456"

    def test_structured_log_includes_request_id(self, capsys):
        """StructuredLogger output includes request_id from context."""
        from backend.services.structured_logging import set_request_id, setup_structured_logging
        import logging

        # Ensure logging is set up
        setup_structured_logging(logging.INFO)

        logger = get_structured_logger("test_correlation")
        set_request_id("req-test-789")

        logger.info("Test message", step="test_step", duration_ms=50, tokens=10, status="ok")

        captured = capsys.readouterr().err  # Structured logging outputs to stderr
        log_entry = json.loads(captured.strip())

        assert log_entry["request_id"] == "req-test-789"
        assert log_entry["step"] == "test_step"
        assert log_entry["duration_ms"] == 50
        assert log_entry["tokens"] == 10
        assert log_entry["status"] == "ok"
        assert "timestamp" in log_entry

    def test_celery_task_correlation_injection_extraction(self):
        """Celery task kwargs properly inject and extract correlation IDs."""
        kwargs = {"task_id": "task-001", "agent_id": "agent-001"}

        inject_correlation_into_task_kwargs(
            kwargs, request_id="req-celery", task_id="task-001", agent_id="agent-001"
        )

        assert kwargs["_request_id"] == "req-celery"
        assert kwargs["_task_id"] == "task-001"
        assert kwargs["_agent_id"] == "agent-001"

        # Extraction
        req_id, task_id, agent_id = extract_correlation_from_task_kwargs(kwargs.copy())
        assert req_id == "req-celery"
        assert task_id == "task-001"
        assert agent_id == "agent-001"

    def test_websocket_correlation_manager(self):
        """WebSocket correlation manager tracks per-connection context."""
        mock_ws = MagicMock()

        ws_correlation_manager.set_connection_context(mock_ws, "ws-req-999")
        ctx = ws_correlation_manager.get_connection_context(mock_ws)

        assert ctx == "ws-req-999"

        # Message context uses connection context as fallback
        with ws_correlation_manager.message_context(mock_ws, message_request_id=None) as req_id:
            assert req_id == "ws-req-999"

        # Message context overrides with message request_id
        with ws_correlation_manager.message_context(mock_ws, "msg-req-111") as req_id:
            assert req_id == "msg-req-111"

    def test_end_to_end_correlation_flow(self, capsys):
        """
        Full HTTP -> Celery -> WebSocket correlation flow.
        Simulates real request propagation through all layers.
        """
        from backend.services.structured_logging import set_request_id, setup_structured_logging
        import logging

        # Ensure logging is set up
        setup_structured_logging(logging.INFO)

        logger = get_structured_logger("test_e2e_correlation")
        http_request_id = "http-req-e2e-001"

        # 1. HTTP layer: request comes in
        set_request_id(http_request_id)
        logger.info("HTTP request received", step="http_received", status="ok")

        # 2. Celery layer: task dispatched with correlation
        task_kwargs = {}
        inject_correlation_into_task_kwargs(
            task_kwargs, request_id=http_request_id, task_id="task-e2e", agent_id="agent-e2e"
        )

        # 3. Celery worker: extracts and sets context
        extracted_req_id, extracted_task_id, extracted_agent_id = extract_correlation_from_task_kwargs(
            task_kwargs.copy()
        )

        with structured_log_context(
            request_id=extracted_req_id,
            task_id=extracted_task_id,
            agent_id=extracted_agent_id
        ):
            logger.info("Celery task started", step="celery_start", status="started")
            logger.info("Celery task processing", step="celery_process", duration_ms=100, tokens=50, status="processing")

            # 4. WebSocket broadcast: includes request_id
            ws_message = {
                "type": "task_update",
                "task_id": extracted_task_id,
                "request_id": extracted_req_id,
                "status": "processing",
            }
            logger.info("WebSocket event sent", step="ws_broadcast", **ws_message)

        # 5. WebSocket client: receives and processes with same request_id
        with structured_log_context(request_id=ws_message["request_id"], task_id=extracted_task_id):
            logger.info("WebSocket message received", step="ws_received", status="ok")

        # Verify all log entries have same request_id
        captured = capsys.readouterr().err  # Structured logging outputs to stderr
        log_entries = [json.loads(line) for line in captured.strip().split("\n") if line.strip()]

        request_ids = [entry.get("request_id") for entry in log_entries if "request_id" in entry]
        assert all(rid == http_request_id for rid in request_ids), f"Request ID mismatch: {request_ids}"
        assert len(request_ids) >= 4  # http, celery_start, celery_process, ws_broadcast, ws_received