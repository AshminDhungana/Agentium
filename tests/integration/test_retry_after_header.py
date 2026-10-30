# tests/integration/test_retry_after_header.py
"""
Tests for LLMClient Retry-After header parsing and hybrid backoff behavior.

Verifies:
1. Retry-After header in seconds parsed and used as delay floor
2. Retry-After header as HTTP-date parsed correctly
3. Missing Retry-After falls back to exponential backoff
4. Retry-After respected across failover chain
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import asyncio
import time
from datetime import datetime, timezone, timedelta

from backend.core.llm_client import LLMClient, ProviderExhaustedError, ErrorTier, ProviderRetryHints
from backend.services.model_provider import OpenAICompatibleProvider, AnthropicProvider
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus


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


class TestRetryAfterHeaderParsing:
    """Tests for Retry-After header parsing in provider.get_retry_hints()."""

    def test_openai_provider_parses_retry_after_seconds(self):
        """OpenAI provider parses Retry-After header in seconds."""
        config = MagicMock(spec=UserModelConfig)
        config.id = "test-config"
        config.provider = ProviderType.OPENAI
        config.default_model = "gpt-4o"
        config.requires_api_key.return_value = True
        config.api_key_encrypted = "encrypted"
        config.get_effective_base_url.return_value = "https://api.openai.com/v1"
        config.timeout_seconds = 60
        config.max_concurrent_requests = 10
        config.requests_per_minute = 60
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 1.0
        config.effort = "none"

        provider = OpenAICompatibleProvider(config)

        # Create a mock RateLimitError with response headers
        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": "30"}
        mock_response.status_code = 429

        import openai
        exc = openai.RateLimitError("Rate limited", response=mock_response, body=None)

        hints = provider.get_retry_hints(exc)
        assert hints.retry_after == 30.0
        assert hints.should_retry is True
        assert hints.error_tier == ErrorTier.RATE_LIMITED

    def test_openai_provider_parses_retry_after_http_date(self):
        """OpenAI provider parses Retry-After header as HTTP-date."""
        config = MagicMock(spec=UserModelConfig)
        config.id = "test-config"
        config.provider = ProviderType.OPENAI
        config.default_model = "gpt-4o"
        config.requires_api_key.return_value = True
        config.api_key_encrypted = "encrypted"
        config.get_effective_base_url.return_value = "https://api.openai.com/v1"
        config.timeout_seconds = 60
        config.max_concurrent_requests = 10
        config.requests_per_minute = 60
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 1.0
        config.effort = "none"

        provider = OpenAICompatibleProvider(config)

        # Create a future HTTP-date (RFC 7231 format)
        future_time = datetime.now(timezone.utc) + timedelta(seconds=45)
        http_date = future_time.strftime("%a, %d %b %Y %H:%M:%S GMT")

        mock_response = MagicMock()
        mock_response.headers = {"Retry-After": http_date}
        mock_response.status_code = 429

        import openai
        exc = openai.RateLimitError("Rate limited", response=mock_response, body=None)

        hints = provider.get_retry_hints(exc)
        # Should parse to approximately 45 seconds (allow small margin)
        assert hints.retry_after is not None
        assert 40 <= hints.retry_after <= 50
        assert hints.should_retry is True

    def test_openai_provider_missing_retry_after_returns_none(self):
        """OpenAI provider returns None for retry_after when header missing."""
        config = MagicMock(spec=UserModelConfig)
        config.id = "test-config"
        config.provider = ProviderType.OPENAI
        config.default_model = "gpt-4o"
        config.requires_api_key.return_value = True
        config.api_key_encrypted = "encrypted"
        config.get_effective_base_url.return_value = "https://api.openai.com/v1"
        config.timeout_seconds = 60
        config.max_concurrent_requests = 10
        config.requests_per_minute = 60
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 1.0
        config.effort = "none"

        provider = OpenAICompatibleProvider(config)

        import openai
        import httpx
        # Create a response without Retry-After header
        mock_response = MagicMock()
        mock_response.headers = {}
        mock_response.status_code = 429
        mock_response.request = httpx.Request("POST", "http://test")
        exc = openai.RateLimitError("Rate limited", response=mock_response, body=None)

        hints = provider.get_retry_hints(exc)
        assert hints.retry_after is None
        assert hints.should_retry is True

    def test_anthropic_provider_uses_sdk_retry_after_priority(self):
        """Anthropic provider uses SDK-native retry_after when available."""
        config = MagicMock(spec=UserModelConfig)
        config.id = "test-config"
        config.provider = ProviderType.ANTHROPIC
        config.default_model = "claude-sonnet-4"
        config.requires_api_key.return_value = True
        config.api_key_encrypted = "encrypted"
        config.get_effective_base_url.return_value = "https://api.anthropic.com"
        config.timeout_seconds = 60
        config.max_concurrent_requests = 10
        config.requests_per_minute = 60
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 1.0
        config.effort = "none"

        provider = AnthropicProvider(config)

        import anthropic
        import httpx
        exc = anthropic.RateLimitError("Rate limited", response=httpx.Response(429, request=httpx.Request("POST", "http://test")), body=None)
        exc.retry_after = 25.5  # SDK-native attribute

        hints = provider.get_retry_hints(exc)
        assert hints.retry_after == 25.5
        assert hints.should_retry is True


class TestLLMClientHybridBackoff:
    """Tests for LLMClient._delay hybrid backoff strategy."""

    @pytest.mark.asyncio
    async def test_retry_after_used_as_delay_floor(self, patch_api_key_manager):
        """Retry-After value used as floor for exponential backoff (hybrid max strategy)."""
        client = LLMClient(max_retries=2, base_retry_delay=1.0, max_retry_delay=30.0)

        # Mock _delay to capture the retry_after value passed
        original_delay = client._delay
        captured_retry_after = []

        async def mock_delay(attempt, retry_after=None):
            captured_retry_after.append((attempt, retry_after))
            # Don't actually sleep
            pass

        client._delay = mock_delay

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_count = {"count": 0}

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_count["count"] += 1
            if call_count["count"] <= 2:  # Fail first 2 attempts
                # Raise error with Retry-After hint
                class MockException(Exception):
                    pass
                exc = MockException("Rate limited")
                exc.retry_after = 10.0  # Simulate provider hint
                raise exc
            return {"content": "Success", "model": "test", "tokens_used": 10, "cost_usd": 0.001}

        # We need to mock at the provider level to inject retry_after
        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            with patch("backend.core.llm_client.ModelService.get_provider") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.get_retry_hints.return_value = ProviderRetryHints(
                    should_retry=True,
                    retry_after=10.0,
                    error_tier=ErrorTier.RATE_LIMITED
                )
                mock_get_provider.return_value = mock_provider

                result = await client.generate(
                    agent=mock_agent,
                    user_message="test",
                    config_id="primary-config",
                    fallback_configs=["fallback-1"],
                )

        # Verify _delay was called with retry_after=10.0
        assert len(captured_retry_after) == 2  # 2 retries
        assert captured_retry_after[0][1] == 10.0
        assert captured_retry_after[1][1] == 10.0

    @pytest.mark.asyncio
    async def test_missing_retry_after_falls_back_to_exponential(self, patch_api_key_manager):
        """When Retry-After missing, exponential backoff is used."""
        client = LLMClient(max_retries=2, base_retry_delay=1.0, max_retry_delay=30.0)

        captured_delays = []

        async def mock_delay(attempt, retry_after=None):
            captured_delays.append((attempt, retry_after))
            pass

        client._delay = mock_delay

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_count = {"count": 0}

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_count["count"] += 1
            if call_count["count"] <= 2:
                class MockException(Exception):
                    pass
                exc = MockException("Rate limited")
                # No retry_after attribute
                raise exc
            return {"content": "Success", "model": "test", "tokens_used": 10, "cost_usd": 0.001}

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            with patch("backend.core.llm_client.ModelService.get_provider") as mock_get_provider:
                mock_provider = MagicMock()
                mock_provider.get_retry_hints.return_value = ProviderRetryHints(
                    should_retry=True,
                    retry_after=None,  # No retry_after
                    error_tier=ErrorTier.RATE_LIMITED
                )
                mock_get_provider.return_value = mock_provider

                result = await client.generate(
                    agent=mock_agent,
                    user_message="test",
                    config_id="primary-config",
                    fallback_configs=["fallback-1"],
                )

        # Verify _delay was called with retry_after=None (falls back to exponential)
        assert len(captured_delays) == 2
        assert captured_delays[0][1] is None
        assert captured_delays[1][1] is None

    @pytest.mark.asyncio
    async def test_retry_after_respected_across_failover_chain(self, patch_api_key_manager):
        """Retry-After from each provider respected during failover."""
        client = LLMClient(max_retries=1, base_retry_delay=1.0, max_retry_delay=30.0)

        captured_delays = []

        async def mock_delay(attempt, retry_after=None):
            captured_delays.append((attempt, retry_after))
            pass

        client._delay = mock_delay

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_counts = {"primary-config": 0, "fallback-1": 0}

        async def mock_generate(agent, user_message, user_id, config_id, **kwargs):
            call_counts[config_id] += 1
            # All configs fail
            class MockException(Exception):
                pass
            exc = MockException("Rate limited")
            exc.retry_after = 5.0 if config_id == "primary-config" else 15.0
            raise exc

        with patch("backend.core.llm_client.ModelService.generate_with_agent", mock_generate):
            with patch("backend.core.llm_client.ModelService.get_provider") as mock_get_provider:
                def get_provider_side_effect(user_id, config_id):
                    mock_provider = MagicMock()
                    retry_after = 5.0 if config_id == "primary-config" else 15.0
                    mock_provider.get_retry_hints.return_value = ProviderRetryHints(
                        should_retry=True,
                        retry_after=retry_after,
                        error_tier=ErrorTier.RATE_LIMITED
                    )
                    return mock_provider
                mock_get_provider.side_effect = get_provider_side_effect

                with pytest.raises(ProviderExhaustedError):
                    await client.generate(
                        agent=mock_agent,
                        user_message="test",
                        config_id="primary-config",
                        fallback_configs=["fallback-1"],
                    )

        # Should have delays for both primary (1 retry) and fallback (1 retry)
        # Each config gets max_retries+1 attempts, so 2 attempts = 1 retry each
        assert len(captured_delays) == 2
        # First delay from primary config
        assert captured_delays[0][1] == 5.0
        # Second delay from fallback config
        assert captured_delays[1][1] == 15.0


class TestRetryAfterWithActualProviders:
    """Integration tests using actual provider classes with mocked HTTP responses."""

    @pytest.mark.asyncio
    async def test_openai_429_with_retry_after_seconds_triggers_delay(self, patch_api_key_manager):
        """OpenAI 429 with Retry-After: 20 causes client to wait ~20s (floor)."""
        client = LLMClient(max_retries=1, base_retry_delay=1.0, max_retry_delay=30.0)

        delay_calls = []

        async def mock_delay(attempt, retry_after=None):
            delay_calls.append({"attempt": attempt, "retry_after": retry_after})
            pass

        client._delay = mock_delay

        mock_agent = MagicMock()
        mock_agent.agentium_id = "test-agent"
        mock_agent.preferred_config_id = "primary-config"

        call_count = {"count": 0}

        # Create a real provider instance to test get_retry_hints
        config = MagicMock(spec=UserModelConfig)
        config.id = "primary-config"
        config.provider = ProviderType.OPENAI
        config.default_model = "gpt-4o"
        config.requires_api_key.return_value = True
        config.api_key_encrypted = "encrypted"
        config.get_effective_base_url.return_value = "https://api.openai.com/v1"
        config.timeout_seconds = 60
        config.max_concurrent_requests = 10
        config.requests_per_minute = 60
        config.max_tokens = 4096
        config.temperature = 0.7
        config.top_p = 1.0
        config.effort = "none"

        real_provider = OpenAICompatibleProvider(config)

        async def mock_get_provider(user_id, config_id):
            return real_provider

        with patch("backend.core.llm_client.ModelService.get_provider", mock_get_provider):
            with patch("backend.core.llm_client.ModelService.generate_with_agent") as mock_generate_agent:
                # First call raises, second succeeds
                async def gen_side_effect(**kwargs):
                    call_count["count"] += 1
                    if call_count["count"] == 1:
                        import httpx
                        import openai
                        mock_response = MagicMock()
                        mock_response.headers = {"Retry-After": "20"}
                        mock_response.status_code = 429
                        mock_response.request = httpx.Request("POST", "http://test")
                        raise openai.RateLimitError("Rate limited", response=mock_response, body=None)
                    return {"content": "Success", "model": "test", "tokens_used": 10, "cost_usd": 0.001}
                mock_generate_agent.side_effect = gen_side_effect

                result = await client.generate(
                    agent=mock_agent,
                    user_message="test",
                    config_id="primary-config",
                    fallback_configs=[],
                )

        # Verify the retry_after was passed to _delay
        assert len(delay_calls) == 1
        assert delay_calls[0]["retry_after"] == 20.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])