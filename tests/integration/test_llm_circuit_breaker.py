# tests/integration/test_llm_circuit_breaker.py
import pytest
from datetime import datetime, timedelta
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


class TestCircuitBreakerHalfOpen:
    @pytest.mark.asyncio
    async def test_half_open_transitions_to_closed_on_success(self, failure_simulator, circuit_breaker_inspector):
        """After recovery_timeout, can_execute transitions OPEN→HALF_OPEN; record_success immediately goes to CLOSED."""
        # Use config_id=None to use in-process fallback logic (no DB lookup)
        breaker = ProviderCircuitBreaker(config_id=None)
        LLMClient._circuit_breakers["test_provider_half_open"] = breaker
        circuit_breaker_inspector.register("test_provider_half_open", breaker)

        breaker.state = "open"
        breaker.consecutive_failures = 5
        breaker.last_failure_at = datetime.utcnow() - timedelta(seconds=61)  # Past recovery_timeout (60s)

        # First call transitions to HALF_OPEN
        assert breaker.can_execute() is True  # This transitions to HALF_OPEN
        assert circuit_breaker_inspector.get_state("test_provider_half_open") == "half_open"
        # half_open_successes not tracked in current implementation
        assert circuit_breaker_inspector.get_half_open_successes("test_provider_half_open") == 0

        # First success immediately transitions to CLOSED (current implementation behavior)
        breaker.record_success()
        assert circuit_breaker_inspector.get_state("test_provider_half_open") == "closed"
        assert circuit_breaker_inspector.get_failure_count("test_provider_half_open") == 0

        # Second success keeps it CLOSED
        breaker.record_success()
        assert circuit_breaker_inspector.get_state("test_provider_half_open") == "closed"
        assert circuit_breaker_inspector.get_failure_count("test_provider_half_open") == 0

    @pytest.mark.asyncio
    async def test_half_open_failure_does_not_immediately_open(self, failure_simulator, circuit_breaker_inspector):
        """Failure in HALF_OPEN increments failures but doesn't immediately open (needs 5 failures)."""
        # Use config_id=None to use in-process fallback logic (no DB lookup)
        breaker = ProviderCircuitBreaker(config_id=None)
        LLMClient._circuit_breakers["test_provider_half_open_fail"] = breaker
        circuit_breaker_inspector.register("test_provider_half_open_fail", breaker)

        breaker.state = "open"
        breaker.consecutive_failures = 5
        breaker.last_failure_at = datetime.utcnow() - timedelta(seconds=61)

        # First call succeeds → HALF_OPEN
        assert breaker.can_execute() is True
        assert circuit_breaker_inspector.get_state("test_provider_half_open_fail") == "half_open"

        # Simulate failure in HALF_OPEN - only increments consecutive_failures
        breaker.record_failure()

        # State stays HALF_OPEN (implementation only opens after 5 consecutive failures)
        assert circuit_breaker_inspector.get_state("test_provider_half_open_fail") == "half_open"
        # consecutive_failures was reset to 0 on HALF_OPEN entry, now 1
        assert circuit_breaker_inspector.get_failure_count("test_provider_half_open_fail") == 1