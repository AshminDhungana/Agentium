"""Tests for backend.core.llm_client.LLMClient."""
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

from backend.core.llm_client import LLMClient, ProviderCircuitBreaker, _CB_FAILURE_THRESHOLD, _CB_RECOVERY_SECONDS


class MockAgent:
    agentium_id = "00001"
    preferred_config_id = "test-config-id"


class TestProviderCircuitBreaker:
    def test_initial_state_closed(self):
        cb = ProviderCircuitBreaker()
        assert cb.state == "closed"
        assert cb.can_execute() is True

    def test_opens_after_threshold(self):
        cb = ProviderCircuitBreaker()
        for _ in range(_CB_FAILURE_THRESHOLD):
            cb.record_failure()
        assert cb.state == "open"
        assert cb.can_execute() is False

    def test_success_resets(self):
        cb = ProviderCircuitBreaker()
        for _ in range(_CB_FAILURE_THRESHOLD):
            cb.record_failure()
        cb.record_success()
        assert cb.state == "closed"
        assert cb.consecutive_failures == 0

    def test_half_open_after_recovery_time(self):
        cb = ProviderCircuitBreaker()
        for _ in range(_CB_FAILURE_THRESHOLD):
            cb.record_failure()
        cb.last_failure_at = datetime.utcnow() - timedelta(seconds=_CB_RECOVERY_SECONDS + 1)
        assert cb.can_execute() is True
        assert cb.state == "half_open"

    def test_metrics(self):
        cb = ProviderCircuitBreaker()
        cb.record_success()
        cb.record_failure()
        m = cb.get_metrics()
        assert m["state"] == "open"
        assert m["consecutive_failures"] == 1
        assert m["total_success"] == 1
        assert m["total_failure"] == 1


class TestLLMClientGenerate:
    @pytest.fixture
    def llm_client(self):
        return LLMClient(db=None, max_retries=2, base_retry_delay=0.01)

    @pytest.mark.asyncio
    async def test_success_no_retry(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_generate:
            mock_generate.return_value = {
                "content": "hello",
                "tokens_used": 10,
                "cost_usd": 0.001,
            }
            agent = MockAgent()
            result = await llm_client.generate(agent, "Say hi")
            assert result["content"] == "hello"
            assert result["provider_config_id"] == "test-config-id"
            mock_generate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_retries_on_rate_limit(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = [
                Exception("429 rate limit"),
                Exception("429 rate limit"),
                {"content": "ok", "tokens_used": 5, "cost_usd": 0.0001},
            ]
            agent = MockAgent()
            result = await llm_client.generate(agent, "test", max_retries=3)
            assert result["content"] == "ok"
            assert mock_generate.await_count == 3

    @pytest.mark.asyncio
    async def test_failover_to_second_config(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_generate:
            async def _side_effect(*, agent=None, user_message="", config_id=None, **kwargs):
                if config_id == "test-config-id":
                    raise Exception("Permanent failure")
                elif config_id == "fallback-config-id":
                    return {"content": "fallback", "tokens_used": 1, "cost_usd": 0.0}
                raise Exception("Unknown config")
            mock_generate.side_effect = _side_effect
            agent = MockAgent()
            result = await llm_client.generate(agent, "test", fallback_configs=["fallback-config-id"])
            assert result["content"] == "fallback"
            assert result["provider_config_id"] == "fallback-config-id"

    @pytest.mark.asyncio
    async def test_circuit_breaker_blocks_after_failures(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_generate:
            mock_generate.side_effect = Exception("always fails")
            agent = MockAgent()
            with pytest.raises(RuntimeError):
                await llm_client.generate(agent, "test", max_retries=0)
            for _ in range(4):
                try:
                    await llm_client.generate(agent, "test", max_retries=0)
                except RuntimeError:
                    pass
            cb = llm_client._get_cb("test-config-id")
            assert cb.state == "open"

    @pytest.mark.asyncio
    async def test_token_tracking_called(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent", new_callable=AsyncMock) as mock_generate, \
             patch("backend.core.llm_client.api_key_manager") as mock_akm, \
             patch("backend.core.llm_client.token_optimizer") as mock_topt:
            mock_generate.return_value = {
                "content": "tracked",
                "tokens_used": 42,
                "cost_usd": 0.0025,
            }
            agent = MockAgent()
            await llm_client.generate(agent, "test")
            assert mock_akm.record_spend.called or mock_akm.record_spend.call_count > 0


class TestLLMClientGenerateWithTools:
    @pytest.fixture
    def llm_client(self):
        return LLMClient(db=None, max_retries=1, base_retry_delay=0.01)

    @pytest.mark.asyncio
    async def test_success(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent_tools", new_callable=AsyncMock) as mock_gwat:
            mock_gwat.return_value = {
                "content": "tool result",
                "tokens_used": 20,
                "cost_usd": 0.005,
            }
            agent = MockAgent()
            result = await llm_client.generate_with_tools(
                agent, user_message="do something", db=MagicMock()
            )
            assert result["content"] == "tool result"
            mock_gwat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_failure_with_tools(self, llm_client):
        with patch("backend.core.llm_client.ModelService.generate_with_agent_tools", new_callable=AsyncMock) as mock_gwat:
            mock_gwat.side_effect = Exception("503 Service Unavailable")
            agent = MockAgent()
            with pytest.raises(RuntimeError) as exc_info:
                await llm_client.generate_with_tools(agent, user_message="do something", db=MagicMock(), max_retries=0)
            assert "exhausted" in str(exc_info.value)
