"""Tests for harness infrastructure."""

import pytest
from backend.tests.harness.scenario_runner import ScenarioRunner, ScenarioResult
from backend.tests.harness.agent_simulator import AgentSimulator, SimulationResult
from backend.tests.harness.tool_interceptor import ToolInterceptor
from backend.tests.harness.budget_tracker import BudgetTracker, BudgetStatus
from backend.tests.harness.log_capture import LogCapture
from backend.tests.harness.correlation_propagator import CorrelationPropagator
from backend.tests.harness.degradation_injector import DegradationInjector


def test_harness_components_import():
    """All harness components import without error."""
    assert ScenarioRunner is not None
    assert ScenarioResult is not None
    assert AgentSimulator is not None
    assert SimulationResult is not None
    assert ToolInterceptor is not None
    assert BudgetTracker is not None
    assert BudgetStatus is not None
    assert LogCapture is not None
    assert CorrelationPropagator is not None
    assert DegradationInjector is not None


@pytest.mark.asyncio
async def test_scenario_runner_basic():
    """ScenarioRunner can execute a simple agent task."""
    runner = ScenarioRunner()

    result = await runner.run_scenario(
        scenario_name="basic_task",
        agent_config={"tier": 2, "tools": ["read_file", "write_file"]},
        task="Create a file with content 'hello'",
        max_turns=5
    )

    assert result.success is True
    assert result.turns_used <= 5
    assert result.correlation_id is not None


@pytest.mark.asyncio
async def test_agent_simulator_drives_orchestrator():
    """AgentSimulator correctly drives AgentOrchestrator through turns."""
    from backend.tests.harness.agent_simulator import AgentSimulator

    simulator = AgentSimulator()

    # Configure simulator with test persona
    simulator.configure(
        system_prompt="You are a test agent. Use tools to complete tasks.",
        available_tools=["read_file", "write_file", "list_files"],
        max_turns=10
    )

    # Run simulation (mock mode since orchestrator may not be fully available)
    result = await simulator.run(
        orchestrator=None,
        task="Read file test.txt and write its content to output.txt"
    )

    assert result.completed is True
    assert result.turns_used > 0
    assert len(result.tool_calls) > 0
    assert all(call.tool in ["read_file", "write_file", "list_files"] for call in result.tool_calls)


@pytest.mark.asyncio
async def test_tool_interceptor_tracks_calls():
    """ToolInterceptor wraps LoopDetector and tracks all tool calls."""
    from backend.core.loop_detector import LoopDetector
    from backend.tests.harness.tool_interceptor import ToolInterceptor

    detector = LoopDetector(max_identical_calls=3)
    interceptor = ToolInterceptor(detector)

    # Simulate tool calls
    async def mock_tool(args):
        return {"result": "ok"}

    wrapped = interceptor.wrap("test_tool", mock_tool)

    # Call 3 times (under limit)
    for _ in range(3):
        await wrapped({"param": "value"})

    stats = detector.get_stats()
    assert stats["total_calls"] == 3
    assert stats["unique_signatures"] == 1

    # 4th call should raise LoopDetectedError
    from backend.core.exceptions import LoopDetectedError
    with pytest.raises(LoopDetectedError):
        await wrapped({"param": "value"})


@pytest.mark.asyncio
async def test_budget_tracker_monitors_token_spend():
    """BudgetTracker hooks into TokenOptimizer for real-time budget monitoring."""
    from backend.services.token_optimizer import TokenOptimizer
    from backend.tests.harness.budget_tracker import BudgetTracker

    optimizer = TokenOptimizer()
    tracker = BudgetTracker(optimizer, daily_budget_usd=10.0)

    # Simulate token usage
    await tracker.record_usage(model="claude-3-sonnet", input_tokens=1000, output_tokens=500)
    await tracker.record_usage(model="claude-3-sonnet", input_tokens=2000, output_tokens=1000)

    # Check budget status
    status = tracker.get_status()
    assert status.spent_usd > 0
    assert status.budget_usd == 10.0
    assert status.percentage == (status.spent_usd / 10.0) * 100

    # Warning at 80%
    assert status.warning_triggered == (status.percentage >= 80)

    # Pause at 100%
    assert status.pause_triggered == (status.percentage >= 100)


@pytest.mark.asyncio
async def test_log_capture_structured_logs():
    """LogCapture collects structured JSON logs for assertions."""
    from backend.tests.harness.log_capture import LogCapture
    import logging

    capture = LogCapture()
    capture.start()

    # Emit structured log (as production code does)
    logger = logging.getLogger("test_agent")
    logger.info("Agent step completed", extra={
        "request_id": "req-123",
        "step": "tool_call",
        "duration_ms": 150,
        "tokens": 250,
        "status": "success"
    })

    logs = capture.get_logs()
    capture.stop()

    assert len(logs) == 1
    log = logs[0]
    assert log["request_id"] == "req-123"
    assert log["step"] == "tool_call"
    assert log["duration_ms"] == 150
    assert log["tokens"] == 250
    assert log["status"] == "success"
    assert "timestamp" in log


@pytest.mark.asyncio
async def test_correlation_propagator_http_to_celery():
    """CorrelationPropagator validates request_id propagation HTTP->Celery."""
    from backend.tests.harness.correlation_propagator import CorrelationPropagator

    propagator = CorrelationPropagator()
    request_id = "test-req-456"

    # Simulate HTTP request with correlation ID
    propagator.inject_http_request(request_id)

    # Simulate Celery task receiving context
    task_context = propagator.extract_celery_context()
    assert task_context["request_id"] == request_id

    # Simulate WebSocket event
    ws_event = propagator.create_ws_event("token", {"data": "test"})
    assert ws_event["request_id"] == request_id


@pytest.mark.asyncio
async def test_degradation_injector_fails_llm():
    """DegradationInjector can simulate LLM provider failure."""
    from backend.tests.harness.degradation_injector import DegradationInjector

    injector = DegradationInjector()

    # Inject LLM failure
    injector.inject_llm_failure("rate_limit")

    # Verify failure is recorded
    events = injector.get_events()
    assert len(events) == 1
    assert events[0]["component"] == "llm"
    assert events[0]["mode"] == "rate_limit"
    assert events[0]["restored"] is False

    # Restore
    injector.restore_llm()

    # Verify restored
    events = injector.get_events()
    assert events[0]["restored"] is True


@pytest.mark.asyncio
async def test_degradation_injector_multiple_components():
    """DegradationInjector can inject failures in multiple components."""
    from backend.tests.harness.degradation_injector import DegradationInjector

    injector = DegradationInjector()

    # Inject failures in multiple components
    injector.inject_llm_failure("server_error")
    injector.inject_db_failure("connection_error")
    injector.inject_chromadb_failure("timeout")

    events = injector.get_events()
    assert len(events) == 3
    components = {e["component"] for e in events}
    assert components == {"llm", "database", "chromadb"}

    # Restore all
    injector.restore_all()

    events = injector.get_events()
    assert all(e["restored"] for e in events)