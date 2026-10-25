"""Pytest configuration for harness tests."""

import pytest
import asyncio
from typing import AsyncGenerator


@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def scenario_runner() -> AsyncGenerator:
    """Create a ScenarioRunner instance for testing."""
    from backend.tests.harness.scenario_runner import ScenarioRunner
    runner = ScenarioRunner()
    yield runner
    await runner.cleanup()


@pytest.fixture
async def agent_simulator() -> AsyncGenerator:
    """Create an AgentSimulator instance for testing."""
    from backend.tests.harness.agent_simulator import AgentSimulator
    simulator = AgentSimulator()
    yield simulator
    await simulator.cleanup()


@pytest.fixture
def tool_interceptor():
    """Create a ToolInterceptor instance for testing."""
    from backend.tests.harness.tool_interceptor import ToolInterceptor
    from backend.core.loop_detector import LoopDetector
    detector = LoopDetector(max_identical_calls=3)
    return ToolInterceptor(detector)


@pytest.fixture
def budget_tracker():
    """Create a BudgetTracker instance for testing."""
    from backend.tests.harness.budget_tracker import BudgetTracker
    from backend.services.token_optimizer import TokenOptimizer
    optimizer = TokenOptimizer()
    return BudgetTracker(optimizer, daily_budget_usd=10.0)


@pytest.fixture
def log_capture():
    """Create a LogCapture instance for testing."""
    from backend.tests.harness.log_capture import LogCapture
    capture = LogCapture()
    capture.start()
    yield capture
    capture.stop()


@pytest.fixture
def correlation_propagator():
    """Create a CorrelationPropagator instance for testing."""
    from backend.tests.harness.correlation_propagator import CorrelationPropagator
    return CorrelationPropagator()


@pytest.fixture
def degradation_injector():
    """Create a DegradationInjector instance for testing."""
    from backend.tests.harness.degradation_injector import DegradationInjector
    injector = DegradationInjector()
    yield injector
    injector.restore_all()