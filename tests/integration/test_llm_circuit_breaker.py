# tests/integration/test_llm_circuit_breaker.py
import pytest
import httpx
from backend.core.llm_client import ProviderCircuitBreaker, ProviderExhaustedError, LLMClient


class TestCircuitBreakerClosedToOpen:
    @pytest.mark.asyncio
    async def test_circuit_opens_after_5_failures(self, failure_simulator, circuit_breaker_inspector):
        """After 5 consecutive failures, circuit should transition to OPEN."""
        # Create a test breaker with known threshold
        breaker = ProviderCircuitBreaker(config_id="test_provider")
        LLMClient._circuit_breakers["test_provider"] = breaker
        circuit_breaker_inspector.register("test_provider", breaker)

        # Reset to known state
        breaker.state = "closed"
        breaker.consecutive_failures = 0

        # Record 5 failures directly on the breaker
        for i in range(5):
            breaker.record_failure()

        # Assert circuit is OPEN
        assert circuit_breaker_inspector.get_state("test_provider") == "open"
        assert circuit_breaker_inspector.get_failure_count("test_provider") == 5

        # Next call to can_execute should return False (circuit OPEN)
        assert breaker.can_execute() is False

    @pytest.mark.asyncio
    async def test_circuit_rejects_fast_when_open(self, failure_simulator, circuit_breaker_inspector):
        """When OPEN, can_execute should return False immediately without HTTP request."""
        breaker = ProviderCircuitBreaker(config_id="test_provider")
        LLMClient._circuit_breakers["test_provider"] = breaker
        circuit_breaker_inspector.register("test_provider", breaker)

        breaker.state = "open"
        breaker.consecutive_failures = 5
        breaker.last_failure_at = None  # No recent failure to allow recovery check

        # can_execute should return False when circuit is OPEN
        assert breaker.can_execute() is False

        # Verify state via inspector
        assert circuit_breaker_inspector.get_state("test_provider") == "open"