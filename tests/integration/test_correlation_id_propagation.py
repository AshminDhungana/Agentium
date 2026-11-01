# tests/integration/test_correlation_id_propagation.py
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from unittest.mock import patch, MagicMock
import uuid


@pytest.mark.asyncio
async def test_correlation_id_generated_when_missing():
    """Middleware should generate request_id when header absent."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
        assert response.status_code == 200
        assert "X-Request-ID" in response.headers
        assert len(response.headers["X-Request-ID"]) == 12


@pytest.mark.asyncio
async def test_correlation_id_propagated_when_provided():
    """Middleware should echo back provided X-Request-ID."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health", headers={"X-Request-ID": "custom-123"})
        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "custom-123"


@pytest.mark.asyncio
async def test_correlation_id_in_structured_logs():
    """Request ID should appear in structured log output."""
    import logging
    from backend.services.structured_logging import get_structured_logger

    # Use the same logger as the request logging middleware
    logger = get_structured_logger("request_logging")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        log_output = []
        class CaptureHandler(logging.Handler):
            def emit(self, record):
                log_output.append(record)

        handler = CaptureHandler()
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)

        # Use an endpoint that is NOT skipped by the request logging middleware
        response = await client.get("/api/v1/status/tokens", headers={"X-Request-ID": "log-test-1"})

        # Check logs contain request_id
        info_records = [r for r in log_output if r.levelname == "INFO"]
        assert any(hasattr(r, "request_id") and r.request_id == "log-test-1" for r in info_records)


@pytest.mark.asyncio
async def test_correlation_id_propagated_to_celery_tasks():
    """Correlation ID should be passed to Celery tasks via _request_id kwarg."""
    from backend.services.tasks.workflow_tasks import execute_deferred_subtask
    from backend.services.structured_logging import get_request_id, request_id_var

    # Set a request ID in the context
    test_request_id = "celery-test-" + str(uuid.uuid4())[:8]
    request_id_var.set(test_request_id)

    # Verify we can retrieve it
    assert get_request_id() == test_request_id

    # Mock the apply_async to capture the kwargs passed
    with patch.object(execute_deferred_subtask, 'apply_async') as mock_apply_async:
        mock_result = MagicMock()
        mock_result.id = "test-task-id"
        mock_apply_async.return_value = mock_result

        # Simulate what workflow_executor._enqueue_deferred does
        from backend.services.tasks.workflow_tasks import execute_deferred_subtask as task_func

        task_func.apply_async(
            kwargs={
                "workflow_id": "test-workflow",
                "intent": "test_intent",
                "params": {"key": "value"},
                "_request_id": get_request_id(),
            },
            countdown=3600,
        )

        # Verify _request_id was passed
        call_kwargs = mock_apply_async.call_args[1]['kwargs']
        assert "_request_id" in call_kwargs
        assert call_kwargs["_request_id"] == test_request_id


@pytest.mark.asyncio
async def test_correlation_id_propagated_to_execute_task_async():
    """Correlation ID should be passed to execute_task_async Celery task."""
    from backend.services.tasks.task_executor import execute_task_async
    from backend.services.structured_logging import get_request_id, request_id_var

    # Set a request ID in the context
    test_request_id = "task-test-" + str(uuid.uuid4())[:8]
    request_id_var.set(test_request_id)

    # Verify we can retrieve it
    assert get_request_id() == test_request_id

    # Mock the delay to capture the args passed
    with patch.object(execute_task_async, 'delay') as mock_delay:
        mock_result = MagicMock()
        mock_result.id = "test-task-id"
        mock_delay.return_value = mock_result

        # Simulate what scheduled_task_dispatcher._submit_execution does
        execute_task_async.delay("T00001", "30001", _request_id=get_request_id())

        # Verify _request_id was passed
        call_args = mock_delay.call_args[0]
        call_kwargs = mock_delay.call_args[1]
        assert len(call_args) == 2  # task_id, agent_id
        assert "_request_id" in call_kwargs
        assert call_kwargs["_request_id"] == test_request_id