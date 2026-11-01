# tests/integration/test_structured_logging_21_4.py
import pytest
import logging
from unittest.mock import AsyncMock, patch, MagicMock
from backend.services.structured_logging import get_structured_logger
from backend.services.structured_logging import set_request_id, request_id_var, timed_step


@pytest.mark.asyncio
async def test_agent_orchestrator_execute_task_emits_structured_logs():
    """execute_task should emit logs with all 6 required fields via timed_step."""
    from backend.services.agent_orchestrator import AgentOrchestrator

    # Set a request ID
    set_request_id("test-req-123")

    logger = get_structured_logger("backend.services.agent_orchestrator")

    log_output = []
    class CaptureHandler(logging.Handler):
        def emit(self, record):
            log_output.append(record)

    handler = CaptureHandler()
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)

    # Create mock DB session
    mock_db = MagicMock()

    # Create mock task and agent
    mock_task = MagicMock()
    mock_task.agentium_id = "T00001"
    mock_task.description = "Test task"
    mock_task.execution_context = "{}"

    mock_agent = MagicMock()
    mock_agent.agentium_id = "30001"
    mock_agent.ethos = "Test ethos"
    mock_agent.preferred_config_id = "config-1"
    mock_agent.preferred_config = MagicMock()
    mock_agent.preferred_config.provider = "openai"
    mock_agent.preferred_config.default_model = "gpt-4"
    mock_agent.compress_ethos = MagicMock()

    # Create orchestrator
    orchestrator = AgentOrchestrator(db=mock_db)

    # Mock the inner method to avoid complex dependencies
    with patch.object(orchestrator, '_execute_task_inner', new_callable=AsyncMock) as mock_inner:
        mock_inner.return_value = {"completed_steps": [], "content": "Result"}

        # Execute
        await orchestrator.execute_task(mock_task, mock_agent, mock_db)

    # Verify structured logs - the execute_task method should be wrapped with timed_step
    step_records = [r for r in log_output if getattr(r, "step", None) == "execute_task"]
    assert len(step_records) >= 2, f"Missing logs for execute_task step (got {len(step_records)})"  # started + completed

    # Check completed log has all 6 fields (extra fields on LogRecord)
    completed = [r for r in step_records if getattr(r, "status", None) == "completed"]
    assert len(completed) == 1, f"Missing completed log for execute_task"
    record = completed[0]
    # These fields are added as extra attributes on the LogRecord
    assert hasattr(record, "request_id"), "Missing request_id"
    assert record.step == "execute_task", "Step mismatch"
    assert hasattr(record, "duration_ms") and record.duration_ms >= 0, "Missing duration_ms"
    assert hasattr(record, "status") and record.status == "completed", "Status not completed"
    assert hasattr(record, "agent_id"), "Missing agent_id"
    assert hasattr(record, "task_id"), "Missing task_id"
    # Note: timestamp is added by StructuredFormatter.format(), not on the raw LogRecord


@pytest.mark.asyncio
async def test_agent_orchestrator_process_intent_emits_structured_logs():
    """process_intent should emit logs with all 6 required fields via timed_step."""
    from backend.services.agent_orchestrator import AgentOrchestrator

    # Set a request ID
    set_request_id("test-req-456")

    logger = get_structured_logger("backend.services.agent_orchestrator")

    log_output = []
    class CaptureHandler(logging.Handler):
        def emit(self, record):
            log_output.append(record)

    handler = CaptureHandler()
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)

    # Create mock DB session
    mock_db = MagicMock()

    # Create orchestrator with mocked dependencies
    orchestrator = AgentOrchestrator(db=mock_db)
    orchestrator._get_agent = MagicMock(return_value=MagicMock(agentium_id="20001", parent=None))
    orchestrator._get_parent_id = MagicMock(return_value="10001")
    orchestrator._check_circuit_breaker = MagicMock(return_value=None)
    orchestrator._get_direction = MagicMock(return_value="up")
    orchestrator._record_metric = MagicMock()
    orchestrator._update_circuit_breaker = MagicMock()
    orchestrator._broadcast_orchestration_event = AsyncMock()
    orchestrator.guard.check_action = AsyncMock(return_value=MagicMock(verdict="allow"))
    orchestrator.message_bus = AsyncMock()
    orchestrator.message_bus.publish = AsyncMock(return_value=MagicMock(success=True, message_id="msg-1", latency_ms=10))
    orchestrator.enrich_with_context = AsyncMock(side_effect=lambda msg: msg)

    # Mock _route_up_with_tools and _route_down_with_tools to avoid message bus complexity
    orchestrator._route_up_with_tools = AsyncMock(return_value=MagicMock(success=True, message_id="msg-1", latency_ms=10))

    # Execute
    result = await orchestrator.process_intent("test intent", "20001", "10001")

    # Verify structured logs for process_intent
    step_records = [r for r in log_output if getattr(r, "step", None) == "process_intent"]
    assert len(step_records) >= 2, f"Missing logs for process_intent step (got {len(step_records)})"

    completed = [r for r in step_records if getattr(r, "status", None) == "completed"]
    assert len(completed) == 1, "Missing completed log for process_intent"
    record = completed[0]
    assert hasattr(record, "request_id"), "Missing request_id"
    assert record.step == "process_intent", "Step mismatch"
    assert hasattr(record, "duration_ms") and record.duration_ms >= 0, "Missing duration_ms"
    assert hasattr(record, "status") and record.status == "completed", "Status not completed"


@pytest.mark.asyncio
async def test_agent_orchestrator_delegate_to_task_emits_structured_logs():
    """delegate_to_task should emit logs with all 6 required fields via timed_step."""
    from backend.services.agent_orchestrator import AgentOrchestrator

    # Set a request ID
    set_request_id("test-req-789")

    logger = get_structured_logger("backend.services.agent_orchestrator")

    log_output = []
    class CaptureHandler(logging.Handler):
        def emit(self, record):
            log_output.append(record)

    handler = CaptureHandler()
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)

    # Create mock DB session
    mock_db = MagicMock()

    # Create orchestrator
    orchestrator = AgentOrchestrator(db=mock_db)
    orchestrator._find_available_task = AsyncMock(return_value="30001")
    orchestrator._ensure_task_agent = AsyncMock(return_value="30001")
    orchestrator.vector_store = None
    orchestrator._log = AsyncMock()

    # Mock critic_service
    with patch('backend.services.agent_orchestrator.critic_service') as mock_critic_service:
        mock_critic_service.spawn_critics_for_task = AsyncMock(return_value=["critic-1"])
        mock_critic_service.review_with_all_task_critics = AsyncMock(return_value={"verdict": "pass", "blocking_critic_type": "output"})
        mock_critic_service.terminate_critics_for_task = AsyncMock()
        mock_critic_service.DEFAULT_MAX_RETRIES = 3

        # Mock message bus
        mock_msg_bus = AsyncMock()
        mock_msg_bus.route_down = AsyncMock(return_value=MagicMock(success=True, metadata={"output": "Done"}))
        orchestrator.message_bus = mock_msg_bus

        # Execute
        task = {"id": "T00001", "description": "Test task", "task_type": "general", "allowed_tools": []}
        result = await orchestrator.delegate_to_task(task, "20001")

    # Verify structured logs for delegate_to_task
    step_records = [r for r in log_output if getattr(r, "step", None) == "delegate_to_task"]
    assert len(step_records) >= 2, f"Missing logs for delegate_to_task step (got {len(step_records)})"

    completed = [r for r in step_records if getattr(r, "status", None) == "completed"]
    assert len(completed) == 1, "Missing completed log for delegate_to_task"
    record = completed[0]
    assert hasattr(record, "request_id"), "Missing request_id"
    assert record.step == "delegate_to_task", "Step mismatch"
    assert hasattr(record, "duration_ms") and record.duration_ms >= 0, "Missing duration_ms"
    assert hasattr(record, "status") and record.status == "completed", "Status not completed"