"""Scenario runner for orchestrating test scenarios."""

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from datetime import datetime


@dataclass
class ScenarioResult:
    """Result of a scenario execution."""
    success: bool
    correlation_id: str
    turns_used: int = 0
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    structured_logs: List[Dict[str, Any]] = field(default_factory=list)
    budget_status: Dict[str, Any] = field(default_factory=dict)
    loop_stats: Dict[str, Any] = field(default_factory=dict)
    degradation_events: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Exception] = field(default_factory=list)
    failure_reason: Optional[str] = None
    circuit_breaker_state: Optional[str] = None
    fallback_attempts: int = 0
    pause_reason: Optional[str] = None

    # For backward compatibility
    @property
    def completed(self) -> bool:
        return self.success


class ScenarioRunner:
    """Orchestrates scenario execution across all P2 subsystems."""

    def __init__(self):
        self._agent_simulator = None
        self._tool_interceptor = None
        self._budget_tracker = None
        self._log_capture = None
        self._correlation_propagator = None
        self._degradation_injector = None
        self._initialized = False

    async def _initialize_components(self, agent_config: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None):
        """Initialize all harness components."""
        if self._initialized:
            return

        from backend.tests.harness.agent_simulator import AgentSimulator
        from backend.tests.harness.tool_interceptor import ToolInterceptor
        from backend.tests.harness.budget_tracker import BudgetTracker
        from backend.tests.harness.log_capture import LogCapture
        from backend.tests.harness.correlation_propagator import CorrelationPropagator
        from backend.tests.harness.degradation_injector import DegradationInjector
        from backend.core.loop_detector import LoopDetector
        from backend.services.token_optimizer import TokenOptimizer

        self._correlation_propagator = CorrelationPropagator()
        correlation_id = str(uuid.uuid4())
        self._correlation_propagator.inject_http_request(correlation_id)

        self._agent_simulator = AgentSimulator()
        self._agent_simulator.configure(
            system_prompt=agent_config.get("system_prompt", "You are a test agent."),
            available_tools=agent_config.get("tools", ["read_file", "write_file"]),
            max_turns=agent_config.get("max_turns", 10),
            user_id=agent_config.get("user_id"),
            tier=agent_config.get("tier", 2)
        )

        detector = LoopDetector(max_identical_calls=3)
        self._tool_interceptor = ToolInterceptor(detector)

        # Connect the tool interceptor to the agent simulator so tool calls are tracked
        self._agent_simulator.set_tool_interceptor(self._tool_interceptor)

        optimizer = TokenOptimizer()
        daily_budget = overrides.get("daily_budget_usd", 10.0) if overrides else 10.0
        self._budget_tracker = BudgetTracker(optimizer, daily_budget_usd=daily_budget)

        self._log_capture = LogCapture()
        self._log_capture.start()

        self._degradation_injector = DegradationInjector()

        self._initialized = True

    async def run_scenario(
        self,
        scenario_name: str,
        agent_config: Dict[str, Any],
        task: str,
        max_turns: int = 10,
        overrides: Optional[Dict[str, Any]] = None
    ) -> ScenarioResult:
        """Run a complete scenario with all harness components."""
        correlation_id = str(uuid.uuid4())

        await self._initialize_components(agent_config, overrides)

        result = ScenarioResult(
            success=False,
            correlation_id=correlation_id
        )

        try:
            # Run the agent simulation
            simulation_result = await self._agent_simulator.run(
                orchestrator=None,  # Will use internal orchestrator
                task=task,
                correlation_id=correlation_id
            )

            result.success = simulation_result.completed
            result.turns_used = simulation_result.turns_used
            result.tool_calls = simulation_result.tool_calls
            result.failure_reason = simulation_result.failure_reason

            # Get stats from components
            if self._tool_interceptor:
                result.loop_stats = self._tool_interceptor.get_detector_stats()

            if self._budget_tracker:
                result.budget_status = self._budget_tracker.get_status_dict()

            if self._log_capture:
                result.structured_logs = self._log_capture.get_logs()

            if self._degradation_injector:
                result.degradation_events = self._degradation_injector.get_events()

        except Exception as e:
            result.errors.append(e)
            result.failure_reason = str(e)
            result.success = False

        return result

    async def cleanup(self):
        """Clean up all harness components."""
        if self._log_capture:
            self._log_capture.stop()
        if self._degradation_injector:
            self._degradation_injector.restore_all()
        if self._agent_simulator:
            await self._agent_simulator.cleanup()
        self._initialized = False