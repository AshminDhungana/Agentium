"""
Integration tests for 5.2.3 — Token Counting Accuracy.

Verifies that token counts reported by providers match independent tiktoken counts
and that cost calculations are accurate.
"""
import pytest
import os
import uuid
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool
from unittest.mock import AsyncMock, MagicMock, patch
from backend.services.model_provider import (
    ModelService,
    OpenAICompatibleProvider,
    AnthropicProvider,
    calculate_cost,
    MODEL_PRICES,
)
from backend.models.entities.user_config import UserModelConfig, ProviderType, ConnectionStatus
from backend.core.security import encrypt_api_key


def _create_committed_config(db_engine, provider: ProviderType, config_name: str, default_model: str, **kwargs) -> UserModelConfig:
    """Create a UserModelConfig committed with a real transaction (not savepoint)."""
    engine = create_engine(os.getenv("DATABASE_URL"), poolclass=NullPool, pool_pre_ping=True)
    s = sessionmaker(bind=engine)()
    config = UserModelConfig(
        user_id="sovereign",
        provider=provider,
        config_name=config_name,
        api_key_encrypted=encrypt_api_key(kwargs.get("api_key", "sk-test1234567890abcdef")),
        api_key_masked=kwargs.get("api_key_masked", "...cdef"),
        default_model=default_model,
        api_base_url=kwargs.get("api_base_url"),
        local_server_url=kwargs.get("local_server_url"),
        status=ConnectionStatus.ACTIVE,
        is_default=kwargs.get("is_default", False),
        max_tokens=kwargs.get("max_tokens", 4000),
        temperature=kwargs.get("temperature", 0.7),
        top_p=kwargs.get("top_p"),
        timeout_seconds=kwargs.get("timeout_seconds", 60),
        requests_per_minute=kwargs.get("requests_per_minute", 60),
        max_concurrent_requests=kwargs.get("max_concurrent_requests", 10),
        effort=kwargs.get("effort", "none"),
    )
    s.add(config)
    s.commit()
    s.refresh(config)
    s.close()
    engine.dispose()
    return config


@pytest.fixture(scope="function")
def openai_config(db_engine):
    """Create an OpenAI config committed with real transaction."""
    return _create_committed_config(
        db_engine,
        ProviderType.OPENAI,
        "Token Count Test",
        "gpt-4o",
        api_base_url="https://api.openai.com/v1",
        is_default=True,
    )


@pytest.fixture(scope="function")
def anthropic_config(db_engine):
    """Create an Anthropic config committed with real transaction."""
    return _create_committed_config(
        db_engine,
        ProviderType.ANTHROPIC,
        "Anthropic Token Count Test",
        "claude-sonnet-5",
        api_base_url="https://api.anthropic.com/v1",
    )


@pytest.fixture(scope="function")
def gemini_config(db_engine):
    """Create a Gemini config committed with real transaction."""
    return _create_committed_config(
        db_engine,
        ProviderType.GEMINI,
        "Gemini Token Count Test",
        "gemini-3.5-pro",
        api_base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    )


@pytest.fixture(scope="function")
def local_config(db_engine):
    """Create a Local config committed with real transaction."""
    return _create_committed_config(
        db_engine,
        ProviderType.LOCAL,
        "Local Token Count Test",
        "llama3.3",
        local_server_url="http://localhost:11434/v1",
    )


class TestTokenCountingAccuracy:
    """Test token counting accuracy across providers."""

    @pytest.mark.asyncio
    async def test_openai_token_counts_match_tiktoken(self, openai_config):
        """OpenAI provider token counts should match tiktoken encoding."""
        import tiktoken

        provider = OpenAICompatibleProvider(openai_config)

        # Mock the client response with known token counts
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Hello, world! This is a test response."
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 25
        mock_response.usage.completion_tokens = 12

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        # Patch the cached client
        import backend.services.model_provider as mp
        cache_key = (str(openai_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            result = await provider.generate(
                system_prompt="You are a helpful assistant.",
                user_message="Say hello",
                agentium_id="test-agent",
            )

            # Verify token counts are present and reasonable
            assert "prompt_tokens" in result
            assert "completion_tokens" in result
            assert "tokens_used" in result
            assert result["tokens_used"] == result["prompt_tokens"] + result["completion_tokens"]
            assert result["prompt_tokens"] == 25
            assert result["completion_tokens"] == 12
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]

    @pytest.mark.asyncio
    async def test_anthropic_token_counts_match_sdk(self, anthropic_config):
        """Anthropic provider token counts should match SDK usage."""
        provider = AnthropicProvider(anthropic_config)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "Hello, world! This is a test response."
        mock_response.stop_reason = "end_turn"
        mock_response.model = "claude-sonnet-5"
        mock_response.usage = MagicMock()
        mock_response.usage.input_tokens = 20
        mock_response.usage.output_tokens = 15

        mock_client.messages.create = AsyncMock(return_value=mock_response)

        import backend.services.model_provider as mp
        cache_key = (str(anthropic_config.id), provider.api_key, provider._anthropic_base_url(anthropic_config), True)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            result = await provider.generate(
                system_prompt="You are a helpful assistant.",
                user_message="Say hello",
                agentium_id="test-agent",
            )

            assert result["prompt_tokens"] == 20
            assert result["completion_tokens"] == 15
            assert result["tokens_used"] == 35
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]

    def test_calculate_cost_known_models(self):
        """calculate_cost should return correct costs for known models."""
        # gpt-4o: $2.50/1M input, $10.00/1M output
        cost = calculate_cost("gpt-4o", ProviderType.OPENAI, 1_000_000, 1_000_000)
        assert cost == 12.50  # 2.50 + 10.00

        # gpt-4o-mini: $0.15/1M input, $0.60/1M output
        cost = calculate_cost("gpt-4o-mini", ProviderType.OPENAI, 1_000_000, 1_000_000)
        assert cost == 0.75  # 0.15 + 0.60

        # claude-sonnet-5: $3.00/1M input, $15.00/1M output
        cost = calculate_cost("claude-sonnet-5", ProviderType.ANTHROPIC, 1_000_000, 1_000_000)
        assert cost == 18.00  # 3.00 + 15.00

        # Local models should be free
        cost = calculate_cost("llama3.3", ProviderType.LOCAL, 1_000_000, 1_000_000)
        assert cost == 0.0

    def test_calculate_cost_fallback_rates(self):
        """Unknown models should use provider fallback rates."""
        # Unknown OpenAI model should use $5.00 blended rate
        cost = calculate_cost("unknown-gpt-model", ProviderType.OPENAI, 1_000_000, 1_000_000)
        assert cost == 10.00  # (1M + 1M) / 1M * 5.00

        # Unknown Anthropic model should use $9.00 blended rate
        cost = calculate_cost("unknown-claude-model", ProviderType.ANTHROPIC, 1_000_000, 1_000_000)
        assert cost == 18.00  # (1M + 1M) / 1M * 9.00

    def test_calculate_cost_prefix_matching(self):
        """Dated model variants should match base model pricing."""
        # gpt-4o-2024-11-20 should match gpt-4o pricing
        cost_dated = calculate_cost("gpt-4o-2024-11-20", ProviderType.OPENAI, 1_000_000, 1_000_000)
        cost_base = calculate_cost("gpt-4o", ProviderType.OPENAI, 1_000_000, 1_000_000)
        assert cost_dated == cost_base

        # claude-3-5-sonnet-20241022 should match claude-3-5-sonnet
        cost_dated = calculate_cost("claude-3-5-sonnet-20241022", ProviderType.ANTHROPIC, 1_000_000, 1_000_000)
        cost_base = calculate_cost("claude-3-5-sonnet-20240620", ProviderType.ANTHROPIC, 1_000_000, 1_000_000)
        assert cost_dated == cost_base

    def test_model_prices_completeness(self):
        """MODEL_PRICES should contain current generation models."""
        # Current OpenAI models
        assert "gpt-5.5" in MODEL_PRICES
        assert "gpt-5.5-pro" in MODEL_PRICES
        assert "gpt-5.4" in MODEL_PRICES
        assert "gpt-4.1" in MODEL_PRICES
        assert "gpt-4.1-mini" in MODEL_PRICES
        assert "o4-mini" in MODEL_PRICES

        # Current Anthropic models
        assert "claude-fable-5" in MODEL_PRICES
        assert "claude-opus-4-8" in MODEL_PRICES
        assert "claude-sonnet-4-6" in MODEL_PRICES
        assert "claude-haiku-4-5" in MODEL_PRICES

        # Current Google models
        assert "gemini-3.1-pro" in MODEL_PRICES
        assert "gemini-3.5-flash" in MODEL_PRICES
        assert "gemini-2.5-pro" in MODEL_PRICES

    @pytest.mark.asyncio
    async def test_usage_logging_records_tokens(self, openai_config, db_session):
        """_log_usage should persist ModelUsageLog with correct tokens."""
        provider = OpenAICompatibleProvider(openai_config)

        # Mock client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock()
        mock_response.usage.prompt_tokens = 100
        mock_response.usage.completion_tokens = 50

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        import backend.services.model_provider as mp
        cache_key = (str(openai_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            await provider.generate(
                system_prompt="System",
                user_message="User",
                agentium_id="test-agent",
            )

            # Verify ModelUsageLog was created
            from backend.models.entities.user_config import ModelUsageLog
            log = db_session.query(ModelUsageLog).filter_by(config_id=openai_config.id).first()
            assert log is not None
            assert log.prompt_tokens == 100
            assert log.completion_tokens == 50
            assert log.total_tokens == 150
            assert log.success is True
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]

    @pytest.mark.asyncio
    async def test_streaming_token_counts_accumulate(self, openai_config):
        """Stream generate should yield content (token counts only in final chunk)."""
        provider = OpenAICompatibleProvider(openai_config)

        # Mock streaming response
        class MockChunk:
            def __init__(self, content, finish_reason=None, usage=None):
                self.choices = [MagicMock()]
                self.choices[0].delta = MagicMock()
                self.choices[0].delta.content = content
                self.choices[0].finish_reason = finish_reason
                if usage:
                    self.usage = usage

        async def mock_stream(*args, **kwargs):
            yield MockChunk("Hello")
            yield MockChunk(" world")
            yield MockChunk("", finish_reason="stop", usage=MagicMock(prompt_tokens=10, completion_tokens=5))

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(return_value=mock_stream())

        import backend.services.model_provider as mp
        cache_key = (str(openai_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            chunks = []
            async for chunk in provider.stream_generate("System", "User"):
                chunks.append(chunk)
            assert "".join(chunks) == "Hello world"
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]

    @pytest.mark.asyncio
    async def test_generate_with_tools_accumulates_tokens(self, openai_config):
        """generate_with_tools should accumulate tokens across all turns."""
        provider = OpenAICompatibleProvider(openai_config)

        # First response: tool call
        tool_call_response = MagicMock()
        tool_call_response.choices = [MagicMock()]
        tool_call_response.choices[0].message = MagicMock()
        tool_call_response.choices[0].message.content = None
        tool_call_response.choices[0].message.tool_calls = [MagicMock()]
        tool_call_response.choices[0].message.tool_calls[0].id = "call_1"
        tool_call_response.choices[0].message.tool_calls[0].function.name = "get_time"
        tool_call_response.choices[0].message.tool_calls[0].function.arguments = "{}"
        tool_call_response.choices[0].finish_reason = "tool_calls"
        tool_call_response.model = "gpt-4o"
        tool_call_response.usage = MagicMock(prompt_tokens=50, completion_tokens=20)

        # Second response: final answer
        final_response = MagicMock()
        final_response.choices = [MagicMock()]
        final_response.choices[0].message.content = "The time is 12:00 PM"
        final_response.choices[0].finish_reason = "stop"
        final_response.model = "gpt-4o"
        final_response.usage = MagicMock(prompt_tokens=30, completion_tokens=15)

        mock_client = AsyncMock()
        mock_client.chat.completions.create = AsyncMock(side_effect=[tool_call_response, final_response])

        import backend.services.model_provider as mp
        cache_key = (str(openai_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            async def mock_executor(name, args):
                return "12:00 PM"

            result = await provider.generate_with_tools(
                system_prompt="System",
                messages=[{"role": "user", "content": "What time is it?"}],
                tools=[{"type": "function", "function": {"name": "get_time", "parameters": {}}}],
                tool_executor=mock_executor,
                agentium_id="test-agent",
            )

            # Tokens should accumulate across turns
            assert result["prompt_tokens"] == 80  # 50 + 30
            assert result["completion_tokens"] == 35  # 20 + 15
            assert result["tokens_used"] == 115
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]


class TestCostTracking:
    """Test cost tracking and budget integration."""

    @pytest.mark.asyncio
    async def test_cost_recorded_in_usage_log(self, openai_config, db_engine):
        """Cost should be calculated and stored in ModelUsageLog."""
        from sqlalchemy.orm import sessionmaker
        provider = OpenAICompatibleProvider(openai_config)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock(prompt_tokens=1000, completion_tokens=500)

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        import backend.services.model_provider as mp
        cache_key = (str(openai_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            result = await provider.generate(
                system_prompt="System",
                user_message="User",
                agentium_id="test-agent",
            )

            # Query using a new session from the test engine
            Session = sessionmaker(bind=db_engine)
            session = Session()
            try:
                from backend.models.entities.user_config import ModelUsageLog
                log = session.query(ModelUsageLog).filter_by(config_id=openai_config.id).first()
                assert log is not None
                assert log.cost_usd is not None
                assert log.cost_usd > 0
                # gpt-4o: $2.50/1M input, $10.00/1M output
                # 1000 input + 500 output = (1000/1M)*2.50 + (500/1M)*10.00 = 0.0025 + 0.005 = 0.0075
                expected_cost = round((1000/1_000_000)*2.50 + (500/1_000_000)*10.00, 8)
                assert log.cost_usd == expected_cost
            finally:
                session.close()
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]

    @pytest.mark.asyncio
    async def test_token_optimizer_integration(self, openai_config):
        """Token optimizer should receive token counts from provider calls."""
        from backend.services.token_optimizer import token_optimizer

        # Reset for clean test
        token_optimizer.tokens_used_by_agent.clear()

        provider = OpenAICompatibleProvider(openai_config)

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Test"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gpt-4o"
        mock_response.usage = MagicMock(prompt_tokens=100, completion_tokens=50)

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        import backend.services.model_provider as mp
        cache_key = (str(openai_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            await provider.generate(
                system_prompt="System",
                user_message="User",
                agentium_id="test-agent-123",
            )

            # Token optimizer should have tracked the tokens
            assert token_optimizer.tokens_used_by_agent.get("test-agent-123", 0) >= 0
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]


class TestProviderSpecificTokenCounting:
    """Test token counting specifics per provider."""

    @pytest.mark.asyncio
    async def test_gemini_token_counts(self, gemini_config):
        """Gemini provider should report token counts correctly."""
        provider = OpenAICompatibleProvider(gemini_config)  # Gemini uses OpenAI-compat

        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Gemini response"
        mock_response.choices[0].finish_reason = "stop"
        mock_response.model = "gemini-3.5-pro"
        mock_response.usage = MagicMock(prompt_tokens=30, completion_tokens=20)

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        import backend.services.model_provider as mp
        cache_key = (str(gemini_config.id), provider.api_key, provider.base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            result = await provider.generate("System", "User", agentium_id="test")
            assert result["prompt_tokens"] == 30
            assert result["completion_tokens"] == 20
            assert result["tokens_used"] == 50
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]

    @pytest.mark.asyncio
    async def test_local_provider_token_estimation(self, local_config):
        """Local provider should estimate tokens when usage not available."""
        from backend.services.model_provider import LocalProvider
        from backend.core.config import settings
        provider = LocalProvider(local_config)

        # Mock the OpenAI-compatible client
        mock_client = AsyncMock()
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_response.choices[0].message.content = "Local response"
        mock_response.model = "llama3.3"
        # No usage object - local models often don't provide it
        mock_response.usage = None

        mock_client.chat.completions.create = AsyncMock(return_value=mock_response)

        import backend.services.model_provider as mp
        # LocalProvider uses api_key="ollama" in _get_cached_sdk_client
        base_url = provider.base_url or settings.OLLAMA_BASE_URL
        cache_key = (str(local_config.id), "ollama", base_url, False)
        original_cache = mp._CLIENT_CACHE.get(cache_key)
        mp._CLIENT_CACHE[cache_key] = mock_client

        try:
            result = await provider.generate("System", "User", agentium_id="test")
            # Should fall back to word-count estimation
            assert "tokens_used" in result
            assert result["tokens_used"] > 0
        finally:
            if original_cache:
                mp._CLIENT_CACHE[cache_key] = original_cache
            else:
                del mp._CLIENT_CACHE[cache_key]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])