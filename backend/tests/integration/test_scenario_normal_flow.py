"""
Task 7 — Scenario: Normal Task Flow (All P2 Subsystems)

Verifies end-to-end normal agent task execution exercises all P2 subsystems:
- Cost controls: budget tracked, no loops detected
- Observability: structured logs with correlation ID
- No degradation triggered
"""
import pytest
import asyncio
from backend.tests.harness.scenario_runner import ScenarioRunner


@pytest.mark.asyncio
async def test_normal_task_flow_all_p2_subsystems():
    """Normal agent task exercises all P2 subsystems correctly."""
    runner = ScenarioRunner()

    result = await runner.run_scenario(
        scenario_name="normal_task_flow",
        agent_config={"tier": 2, "tools": ["read_file", "write_file", "search"]},
        task="Research a topic and write a summary to file",
        max_turns=10
    )

    # Verify all subsystems engaged
    assert result.success is True, f"Scenario failed: {result.failure_reason}"
    assert result.correlation_id is not None

    # Cost controls: budget tracked, no loop detected
    assert result.budget_status["percentage"] < 100
    assert result.loop_stats["total_calls"] > 0
    assert result.loop_stats.get("loops_detected", 0) == 0

    # Observability: structured logs, correlation ID propagated
    assert len(result.structured_logs) > 0
    for log in result.structured_logs:
        assert "request_id" in log
        assert log["request_id"] == result.correlation_id
        assert all(k in log for k in ["timestamp", "step", "duration_ms", "tokens", "status"])

    # No degradation triggered
    assert result.degradation_events == []