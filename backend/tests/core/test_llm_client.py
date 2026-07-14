"""Tests for backend.core.llm_client.LLMClient."""
import pytest
import random
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta

import openai
import anthropic
from backend.services.api_key_manager import api_key_manager
from backend.core.llm_client import (
    LLMClient,
    ProviderCircuitBreaker,
    ErrorTier,
    _CB_FAILURE_THRESHOLD,
    _CB_RECOVERY_SECONDS,
)


class MockAgent:
    agentium_id = "00001"
    preferred_config_id = "test-config-id"


@pytest.fixture(autouse=True)
def reset_circuit_breakers():
    """Reset shared circuit breaker state between tests.

    Phase 19.3 (Task 16) made ``ProviderCircuitBreaker.can_execute()`` delegate
    to ``api_key_manager.is_config_healthy()`` as the single source of truth.
    That query hits the DB and returns False for any config id that isn't a
    real, healthy row — which the mock config ids used here ("test-config-id",
    "cfg-A", …) never are. For these unit tests we only want to exercise the
    LLMClient retry/failover logic, so we stub the health check to report every
    config as healthy and keep the in-process breaker driving ``can_execute``.
    Tests that specifically assert the delegation (``test_cb_delegates_to_keymanager``)
    override this locally via ``monkeypatch``.
    """
    from backend.core.llm_client import LLMClient
    from backend.services.api_key_manager import api_key_manager
    LLMClient._circuit_breakers.clear()
    with patch.object(api_key_manager, "is_config_healthy", return_value=True):
        yield
    LLMClient._circuit_breakers.clear()


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
        # 1 failure is below threshold; state remains closed
        assert m["state"] == "closed"
        assert m["consecutive_failures"] == 1
        assert m["total_success"] == 1
        assert m["total_failure"] == 1


class TestClassifyError:
    """3-tier error classification via typed SDK exceptions.

    NOTE: openai/anthropic APIStatusError subclasses require response= and
    body= kwargs (2.24.0), so we build a minimal mock response rather than the
    positional construction the plan brief assumed.
    """

    @staticmethod
    def _status_err(sdk, name, status, message):
        resp = MagicMock()
        resp.status_code = status
        return getattr(sdk, name)(message, response=resp, body=None)

    def test_classify_tiers(self):
        client = LLMClient()
        assert client.classify_error(
            self._status_err(openai, "RateLimitError", 429, "429")
        ) is ErrorTier.RATE_LIMITED
        assert client.classify_error(
            self._status_err(openai, "AuthenticationError", 401, "401")
        ) is ErrorTier.PERMANENT_KEY_FAILURE
        assert client.classify_error(
            self._status_err(anthropic, "RateLimitError", 429, "429")
        ) is ErrorTier.RATE_LIMITED
        assert client.classify_error(
            self._status_err(anthropic, "AuthenticationError", 401, "401")
        ) is ErrorTier.PERMANENT_KEY_FAILURE
        assert client.classify_error(openai.APITimeoutError("timeout")) is ErrorTier.TRANSIENT
        assert client.classify_error(
            self._status_err(openai, "InternalServerError", 503, "503")
        ) is ErrorTier.TRANSIENT
        assert client.classify_error(RuntimeError("invalid api key")) is ErrorTier.PERMANENT_KEY_FAILURE
        assert client.classify_error(RuntimeError("random boom")) is ErrorTier.UNKNOWN


def test_fallback_list_is_capped():
    client = LLMClient()
    big = ["c%d" % i for i in range(20)]
    # Replicate the truncation the generate() loop applies.
    truncated = (["primary"] + big)[:1 + LLMClient.MAX_FALLBACK_CONFIGS]
    assert len(truncated) == 4


def test_cb_delegates_to_keymanager(monkeypatch):
    """Task 16: ProviderCircuitBreaker.can_execute() is now a thin delegate over
    api_key_manager.is_config_healthy (the single source of truth). When the
    manager reports a config unhealthy, can_execute() must return False; when
    healthy, True. Patched here so no DB session is required."""
    client = LLMClient()
    cb = client._get_cb("cfg-delegate")

    monkeypatch.setattr(api_key_manager, "is_config_healthy", lambda cfg_id: False)
    assert cb.can_execute() is False

    monkeypatch.setattr(api_key_manager, "is_config_healthy", lambda cfg_id: True)
    assert cb.can_execute() is True


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
    async def test_permanent_failure_rotates_immediately(self, llm_client):
        calls = []
        auth_resp = MagicMock()
        auth_resp.status_code = 401

        async def fake_generate(agent, user_message, **kwargs):
            cfg = kwargs.get("config_id")
            calls.append(cfg)
            if cfg == "cfg-A":
                # openai 2.24.0 requires response=/body= on APIStatusError subclasses
                raise openai.AuthenticationError(
                    "401 invalid key", response=auth_resp, body=None)
            return {"content": "ok", "tokens_used": 1, "model": "m"}

        with patch("backend.core.llm_client.ModelService.generate_with_agent", fake_generate):
            result = await llm_client.generate(
                agent=object(), user_message="hi",
                config_id="cfg-A", fallback_configs=["cfg-B"])
        assert result["content"] == "ok"
        # cfg-A must NOT be retried (only 1 call), then cfg-B called once
        assert calls == ["cfg-A", "cfg-B"], calls

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
             patch("backend.core.llm_client.api_key_manager") as mock_akm:
            mock_generate.return_value = {
                "content": "tracked",
                "tokens_used": 42,
                "cost_usd": 0.0025,
            }
            agent = MockAgent()
            await llm_client.generate(agent, "test")
            assert mock_akm.record_spend.called or mock_akm.record_spend.call_count > 0


class TestLLMClientDelayJitter:
    """Tests for LLMClient._delay full-jitter exponential backoff."""

    @pytest.fixture
    def llm_client(self):
        return LLMClient(db=None, max_retries=5, base_retry_delay=0.1, max_retry_delay=1.0)

    @pytest.mark.asyncio
    @patch("backend.core.llm_client.random.uniform")
    async def test_delay_calls_uniform_with_full_jitter_range(self, mock_uniform, llm_client):
        """_delay calls random.uniform(0, min(max_retry_delay, base_retry_delay * 2**attempt))."""
        mock_uniform.return_value = 0.0  # return fixed value to make sleep instant
        await llm_client._delay(0)
        mock_uniform.assert_called_once_with(0, 0.1)  # 0.1 * 2**0 = 0.1, min(1.0, 0.1) = 0.1

        mock_uniform.reset_mock()
        await llm_client._delay(1)
        mock_uniform.assert_called_once_with(0, 0.2)  # 0.1 * 2**1 = 0.2

        mock_uniform.reset_mock()
        await llm_client._delay(2)
        mock_uniform.assert_called_once_with(0, 0.4)  # 0.1 * 2**2 = 0.4

        mock_uniform.reset_mock()
        await llm_client._delay(10)  # large attempt -> capped at max_retry_delay
        mock_uniform.assert_called_once_with(0, 1.0)  # capped at max_retry_delay=1.0

    @pytest.mark.asyncio
    @patch("backend.core.llm_client.random.uniform")
    @patch("backend.core.llm_client.asyncio.sleep", new_callable=AsyncMock)
    async def test_delay_jitter_produces_varied_delays(self, mock_sleep, mock_uniform, llm_client):
        """Repeated _delay calls with same attempt produce varied delays (jitter works)."""
        # Make random.uniform return different values each call
        call_count = 0
        def varied_uniform(a, b):
            nonlocal call_count
            call_count += 1
            return call_count * 0.01  # deterministic but varying
        mock_uniform.side_effect = varied_uniform

        delays = []
        for _ in range(5):
            await llm_client._delay(1)
            # capture the delay passed to asyncio.sleep
            _, kwargs = mock_sleep.call_args
            delays.append(kwargs.get('delay', mock_sleep.call_args[0][0]))

        # All delays should be different (jitter working)
        assert len(set(delays)) == len(delays), "Jitter should produce varied delays"
        # All delays should be within [0, 0.2] for attempt=1 (base=0.1 * 2**1 = 0.2)
        assert all(0 <= d <= 0.2 for d in delays), "All delays within full-jitter bounds"


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


class TestCallSitesPassFallback:
    """Task 14: every LLMClient call site must pass a real fallback_configs list.

    The Path A chokepoint (skill_rag.execute_with_skills) is covered by the
    integration test test_provider_resilience.py. Here we assert the Path B
    orchestrator builds the chain via api_key_manager.get_fallback_config_ids
    and forwards it to LLMClient.generate_with_tools.
    """

    @pytest.mark.asyncio
    async def test_orchestrator_passes_fallback(self):
        from backend.services import agent_orchestrator
        import backend.services.token_optimizer as token_optimizer_mod
        from backend.services.api_key_manager import api_key_manager
        from backend.services.prompt_template_manager import prompt_template_manager

        captured = {}
        fb_list = ["fb-config-1", "fb-config-2", "fb-config-3"]
        config_id = "primary-config-id"

        # api_manager is None outside the app lifespan; substitute a mock so the
        # unrelated model-lookup line (api_manager.models.get(...)) is a no-op.
        mock_api_manager = MagicMock()
        mock_api_manager.models.get.return_value = None

        class FakePreferredConfig:
            provider = "openai"
            default_model = "gpt-4o"

        class FakeAgent:
            agentium_id = "30001"
            preferred_config_id = config_id
            preferred_config = FakePreferredConfig()
            ethos = {}
            def compress_ethos(self, *a, **k):
                pass

        class FakeTask:
            agentium_id = "T30001"
            description = "do the thing"

        db = MagicMock()
        agent = FakeAgent()
        task = FakeTask()

        with patch.object(
            token_optimizer_mod.token_optimizer,
            "allocate_model_for_agent",
            new=AsyncMock(return_value=config_id),
        ), patch.object(
            api_key_manager,
            "get_fallback_config_ids",
            return_value=fb_list,
        ) as mock_get_fb, patch.object(
            prompt_template_manager,
            "build_system_prompt",
            return_value=("sys", 1, False),
        ), patch.object(
            agent_orchestrator,
            "api_manager",
            mock_api_manager,
        ), patch.object(
            LLMClient,
            "generate_with_tools",
            new=AsyncMock(return_value={"content": "x", "completed_steps": [], "tokens_used": 1}),
        ) as mock_gen:
            orchestrator = agent_orchestrator.AgentOrchestrator(db)
            await orchestrator._execute_task_inner(task, agent, db)

        # The orchestrator must build the failover chain from the allocated
        # config and forward it to LLMClient (we observe the value it passes by
        # having get_fallback_config_ids return a sentinel list).
        mock_get_fb.assert_called_once_with(config_id)
        captured.update(mock_gen.call_args.kwargs)
        assert captured.get("fallback_configs") == fb_list, "no fallback_configs forwarded to generate_with_tools"
        assert captured.get("config_id") == config_id
