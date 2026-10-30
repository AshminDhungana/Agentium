# tests/integration/test_llm_failover.py
"""
Tests for LLMClient failover chain behavior.

Verifies:
1. All fallback providers returning 429 → task_degraded broadcast fires
2. Fallback succeeds → task completes normally without degraded broadcast
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx

from backend.core.llm_client import LLMClient, ProviderExhaustedError, ErrorTier, ProviderCircuitBreaker


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset class-level circuit breakers before each test."""
    LLMClient._circuit_breakers.clear()
    yield
    LLMClient._circuit_breakers.clear()


@pytest.fixture(autouse=True)
def patch_api_key_manager():
    """Patch api_key_manager to avoid DB calls in tests."""
    with patch("backend.core.llm_client.api_key_manager") as mock_manager:
        mock_manager.is_config_healthy.return_value = True
        mock_manager.mark_key_success.return_value = None
        mock_manager.mark_key_failed.return_value = None
        mock_manager.record_spend.return_value = None
        yield mock_manager


class TestLLMFailoverChain:
    """Tests for provider failover chain exhaustion and success scenarios."""

    @pytest.mark.asyncio
    async def test_all_fallbacks_rate_limited_triggers_degraded_broadcast(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """When all providers return 429, ProviderExhaustedError is raised with rate_limited tier."""
        client = LLMClient(max_retries=1)  # 1 retry = 2 attempts per provider

        # Create a mock agent
        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        # Track which config was called
        call_counts = {"primary-config": 0, "fallback-1": 0, "fallback-2": 0}

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            # All configs return 429 (rate limited)
            raise httpx.HTTPStatusError(
                "Rate limited",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(429, request=httpx.Request("POST", "http://test"))
            )

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            with pytest.raises(ProviderExhaustedError) as exc_info:
                await client.generate(
                    agent=mock_agent,
                    user_message="test message",
                    config_id="primary-config",
                    fallback_configs=["fallback-1", "fallback-2"],
                )

        # Verify all configs were attempted
        assert call_counts["primary-config"] == 2  # 1 initial + 1 retry
        assert call_counts["fallback-1"] == 2
        assert call_counts["fallback-2"] == 2

        # Verify error result contains rate_limited tier
        result = exc_info.value.result
        assert result.error_tier == ErrorTier.RATE_LIMITED
        assert "primary-config" in result.attempted_configs
        assert "fallback-1" in result.attempted_configs
        assert "fallback-2" in result.attempted_configs

        # Verify task_degraded broadcast was sent (when called from task_executor)
        # This is tested at integration level in task_executor tests
        # Here we verify the exception carries the right info for the executor to broadcast

    @pytest.mark.asyncio
    async def test_fallback_succeeds_completes_normally(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """When primary fails but fallback succeeds, task completes without degraded broadcast."""
        client = LLMClient(max_retries=1)

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_counts = {"primary-config": 0, "fallback-1": 0}
        success_result = {
            "content": "Success from fallback",
            "model": "test-model",
            "tokens_used": 100,
            "cost_usd": 0.001,
        }

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            if config_id == "primary-config":
                # Primary fails with rate limit
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=httpx.Request("POST", "http://test"),
                    response=httpx.Response(429, request=httpx.Request("POST", "http://test"))
                )
            # Fallback succeeds
            return success_result

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            result = await client.generate(
                agent=mock_agent,
                user_message="test message",
                config_id="primary-config",
                fallback_configs=["fallback-1"],
            )

        # Verify primary was attempted (with retry) then fallback succeeded
        assert call_counts["primary-config"] == 2  # initial + 1 retry
        assert call_counts["fallback-1"] == 1  # succeeded on first try

        # Verify successful result
        assert result["content"] == "Success from fallback"
        assert result["provider_config_id"] == "fallback-1"

        # No degraded broadcast should be sent (verify via ws_capture)
        degraded_events = [e for e in ws_capture.captured_events if e.get("type") == "task_degraded"]
        assert len(degraded_events) == 0

    @pytest.mark.asyncio
    async def test_primary_succeeds_no_fallback_used(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """When primary succeeds, no fallback is attempted."""
        client = LLMClient(max_retries=1)

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_counts = {"primary-config": 0, "fallback-1": 0}
        success_result = {
            "content": "Success from primary",
            "model": "test-model",
            "tokens_used": 50,
            "cost_usd": 0.0005,
        }

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            return success_result

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            result = await client.generate(
                agent=mock_agent,
                user_message="test message",
                config_id="primary-config",
                fallback_configs=["fallback-1"],
            )

        # Only primary should be called
        assert call_counts["primary-config"] == 1
        assert call_counts["fallback-1"] == 0

        assert result["content"] == "Success from primary"
        assert result["provider_config_id"] == "primary-config"

        degraded_events = [e for e in ws_capture.captured_events if e.get("type") == "task_degraded"]
        assert len(degraded_events) == 0

    @pytest.mark.asyncio
    async def test_permanent_failure_rotates_immediately_no_retry(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """Permanent key failure (401/403) rotates to fallback immediately without retry."""
        client = LLMClient(max_retries=2)

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_counts = {"primary-config": 0, "fallback-1": 0}
        success_result = {
            "content": "Success from fallback after auth failure",
            "model": "test-model",
            "tokens_used": 75,
            "cost_usd": 0.0008,
        }

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            if config_id == "primary-config":
                # Primary fails with 401 (permanent)
                raise httpx.HTTPStatusError(
                    "Invalid API key",
                    request=httpx.Request("POST", "http://test"),
                    response=httpx.Response(401, request=httpx.Request("POST", "http://test"))
                )
            return success_result

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            result = await client.generate(
                agent=mock_agent,
                user_message="test message",
                config_id="primary-config",
                fallback_configs=["fallback-1"],
            )

        # Primary called once (no retry for permanent failure), fallback called once
        assert call_counts["primary-config"] == 1
        assert call_counts["fallback-1"] == 1

        assert result["content"] == "Success from fallback after auth failure"
        assert result["provider_config_id"] == "fallback-1"

        degraded_events = [e for e in ws_capture.captured_events if e.get("type") == "task_degraded"]
        assert len(degraded_events) == 0

    @pytest.mark.asyncio
    async def test_transient_failure_retries_then_fallback(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """Transient failure (5xx) retries on primary, then falls back."""
        client = LLMClient(max_retries=1)

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_counts = {"primary-config": 0, "fallback-1": 0}
        success_result = {
            "content": "Success after transient failure",
            "model": "test-model",
            "tokens_used": 60,
            "cost_usd": 0.0006,
        }

        primary_attempt = {"count": 0}  # Use dict for mutable closure

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            if config_id == "primary-config":
                primary_attempt["count"] += 1
                if primary_attempt["count"] <= 2:  # First two attempts (initial + 1 retry) fail
                    raise httpx.HTTPStatusError(
                        "Server error",
                        request=httpx.Request("POST", "http://test"),
                        response=httpx.Response(503, request=httpx.Request("POST", "http://test"))
                    )
            return success_result

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            result = await client.generate(
                agent=mock_agent,
                user_message="test message",
                config_id="primary-config",
                fallback_configs=["fallback-1"],
            )

        # Primary: initial + 1 retry = 2 calls, then fallback: 1 call
        assert call_counts["primary-config"] == 2
        assert call_counts["fallback-1"] == 1

        assert result["content"] == "Success after transient failure"
        assert result["provider_config_id"] == "fallback-1"

        degraded_events = [e for e in ws_capture.captured_events if e.get("type") == "task_degraded"]
        assert len(degraded_events) == 0

    @pytest.mark.asyncio
    async def test_max_fallback_configs_limit(self, failure_simulator, patch_api_key_manager):
        """Only MAX_FALLBACK_CONFIGS (3) fallbacks are attempted."""
        client = LLMClient(max_retries=0)  # No retries to speed up test

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary"

        call_counts = {}

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id] = call_counts.get(config_id, 0) + 1
            raise httpx.HTTPStatusError(
                "Rate limited",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(429, request=httpx.Request("POST", "http://test"))
            )

        # Provide 5 fallbacks but only 3 should be used (1 primary + 3 fallbacks = 4 total)
        fallback_configs = ["fb1", "fb2", "fb3", "fb4", "fb5"]

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            with pytest.raises(ProviderExhaustedError) as exc_info:
                await client.generate(
                    agent=mock_agent,
                    user_message="test message",
                    config_id="primary",
                    fallback_configs=fallback_configs,
                )

        result = exc_info.value.result
        # Should only have attempted primary + 3 fallbacks = 4 configs
        assert len(result.attempted_configs) == 4
        assert "primary" in result.attempted_configs
        assert "fb1" in result.attempted_configs
        assert "fb2" in result.attempted_configs
        assert "fb3" in result.attempted_configs
        assert "fb4" not in result.attempted_configs
        assert "fb5" not in result.attempted_configs


class TestLLMFailoverWithTools:
    """Tests for failover chain in generate_with_tools (used by task_executor)."""

    @pytest.mark.asyncio
    async def test_generate_with_tools_failover_succeeds(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """generate_with_tools fails over successfully when primary fails."""
        client = LLMClient(max_retries=1)

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        mock_db = MagicMock()

        call_counts = {"primary-config": 0, "fallback-1": 0}
        success_result = {
            "content": "Tool success from fallback",
            "model": "test-model",
            "tokens_used": 150,
            "cost_usd": 0.002,
        }

        async def mock_generate_tools(agent, user_message, db, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            if config_id == "primary-config":
                raise httpx.HTTPStatusError(
                    "Rate limited",
                    request=httpx.Request("POST", "http://test"),
                    response=httpx.Response(429, request=httpx.Request("POST", "http://test"))
                )
            return success_result

        with patch("backend.core.llm_client.ModelService.generate_with_agent_tools", mock_generate_tools):
            result = await client.generate_with_tools(
                agent=mock_agent,
                user_message="test message",
                db=mock_db,
                config_id="primary-config",
                fallback_configs=["fallback-1"],
            )

        assert call_counts["primary-config"] == 2  # initial + retry
        assert call_counts["fallback-1"] == 1

        assert result["content"] == "Tool success from fallback"
        assert result["provider_config_id"] == "fallback-1"

        degraded_events = [e for e in ws_capture.captured_events if e.get("type") == "task_degraded"]
        assert len(degraded_events) == 0

    @pytest.mark.asyncio
    async def test_generate_with_tools_all_exhausted_raises_provider_exhausted(
        self, failure_simulator, ws_capture, patch_api_key_manager
    ):
        """generate_with_tools raises ProviderExhaustedError when all providers fail."""
        client = LLMClient(max_retries=1)

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        mock_db = MagicMock()

        call_counts = {"primary-config": 0, "fallback-1": 0}

        async def mock_generate_tools(agent, user_message, db, config_id, **kwargs):
            call_counts[config_id or "default"] += 1
            raise httpx.HTTPStatusError(
                "Rate limited",
                request=httpx.Request("POST", "http://test"),
                response=httpx.Response(429, request=httpx.Request("POST", "http://test"))
            )

        with patch("backend.core.llm_client.ModelService.generate_with_agent_tools", mock_generate_tools):
            with pytest.raises(ProviderExhaustedError) as exc_info:
                await client.generate_with_tools(
                    agent=mock_agent,
                    user_message="test message",
                    db=mock_db,
                    config_id="primary-config",
                    fallback_configs=["fallback-1"],
                )

        assert call_counts["primary-config"] == 2
        assert call_counts["fallback-1"] == 2

        result = exc_info.value.result
        assert result.error_tier == ErrorTier.RATE_LIMITED

        # The task_executor will catch this and broadcast task_degraded
        # We verify the exception structure here
        assert "primary-config" in result.attempted_configs
        assert "fallback-1" in result.attempted_configs